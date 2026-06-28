from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from kenpro_store.enums import ErrorCode, SuccessMessage
from kenpro_store.responses import ErrorResponse, SuccessResponse

from .models import Membership, PinScope, Plan, Role, ServiceFlag, Subscription, Tenant, User
from .serializers import (
    ActivateSerializer,
    ExtendTrialSerializer,
    MembershipSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PinResetConfirmSerializer,
    PinResetRequestSerializer,
    PinScopeSerializer,
    PlanSerializer,
    RegisterSerializer,
    RoleSerializer,
    ServiceFlagInputSerializer,
    ServiceFlagSerializer,
    SetPinSerializer,
    StartTrialSerializer,
    SubscriptionSerializer,
    TenantSerializer,
    UserCreateSerializer,
    UserSerializer,
    VerifyPinSerializer,
)
from .services import (
    MembershipService,
    PasswordChangeService,
    PasswordResetService,
    PinResetService,
    ServiceFlagService,
    SubscriptionService,
)


# ---------------------------------------------------------------------------
# Réponse générique réutilisable (doit être définie avant les vues qui l'utilisent)
# ---------------------------------------------------------------------------
_detail_response = OpenApiResponse(
    description="Message de confirmation.",
    examples=[OpenApiExample("ok", value={"detail": "…"})],
)

# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------

@extend_schema(
    summary="Créer un compte",
    description=(
        "Inscrit un nouvel utilisateur identifié par son numéro de téléphone (format E.164, ex : `+237600000001`). "
        "Le mot de passe est optionnel — l'authentification principale se fait par OTP SMS. "
        "Retourne les informations du compte créé (sans le mot de passe)."
    ),
    request=RegisterSerializer,
    responses={
        201: UserSerializer,
        400: OpenApiResponse(description="Numéro déjà utilisé ou données invalides."),
    },
    tags=["Inscription"],
    examples=[
        OpenApiExample(
            "Inscription minimale",
            request_only=True,
            value={"phone": "+237600000001"},
        ),
        OpenApiExample(
            "Inscription complète",
            request_only=True,
            value={
                "phone": "+237600000001",
                "full_name": "Alice Mbida",
                "email": "alice@example.com",
                "password": "motdepasse123",
            },
        ),
    ],
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Demander la réinitialisation du mot de passe",
        description=(
            "Envoie un code de réinitialisation par email. "
            "L'email doit correspondre à un compte existant."
        ),
        request=PasswordResetRequestSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="Aucun compte associé à cet email."),
        },
        tags=["Mot de passe"],
        examples=[OpenApiExample("Exemple", request_only=True, value={"email": "alice@example.com"})],
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            PasswordResetService.request_reset(serializer.validated_data["email"])
        except ValueError:
            # Don't reveal whether the email is registered.
            pass
        except Exception:
            return ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Impossible d'envoyer l'email. Vérifiez la configuration SMTP.",
                status_code=500,
            )
        return SuccessResponse(message="Si un compte est associé à cet email, un code a été envoyé.")


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Confirmer la réinitialisation du mot de passe",
        description="Valide le code reçu par email et applique le nouveau mot de passe (min 8 caractères).",
        request=PasswordResetConfirmSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="Code invalide, expiré ou mot de passe trop court."),
        },
        tags=["Mot de passe"],
        examples=[
            OpenApiExample(
                "Exemple",
                request_only=True,
                value={"token": "le-code-recu-par-email", "new_password": "nouveauMotDePasse123"},
            )
        ],
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            PasswordResetService.confirm_reset(
                token_value=serializer.validated_data["token"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc), status_code=400)
        return SuccessResponse(message="Mot de passe réinitialisé avec succès.")


class PasswordChangeView(APIView):

    @extend_schema(
        summary="Changer le mot de passe",
        description=(
            "Permet à un utilisateur de changer son mot de passe en fournissant "
            "son numéro de téléphone et son mot de passe actuel. "
            "Les comptes OTP sans mot de passe doivent d'abord passer par la réinitialisation."
        ),
        request=PasswordChangeSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="Mot de passe actuel incorrect ou compte OTP."),
            404: OpenApiResponse(description="Utilisateur introuvable."),
        },
        tags=["Mot de passe"],
        examples=[
            OpenApiExample(
                "Exemple",
                request_only=True,
                value={
                    "phone": "+237600000001",
                    "current_password": "ancienMotDePasse",
                    "new_password": "nouveauMotDePasse123",
                },
            )
        ],
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            PasswordChangeService.change(
                user=request.user,
                current_password=serializer.validated_data["current_password"],
                new_password=serializer.validated_data["new_password"],
            )
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc), status_code=400)
        return SuccessResponse(message="Mot de passe modifié avec succès.")


class PinResetRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Demander la réinitialisation du PIN",
        description=(
            "Envoie un code de réinitialisation par email à l'utilisateur lié au membership. "
            "L'utilisateur doit avoir une adresse email enregistrée sur son compte. "
            "Tout jeton précédent non utilisé est invalidé. "
            "Le code expire après `PIN_RESET_TOKEN_TTL_MINUTES` minutes (défaut : 15)."
        ),
        request=PinResetRequestSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="Membership introuvable ou utilisateur sans email."),
        },
        tags=["Appartenances — PIN"],
        examples=[
            OpenApiExample("Exemple", request_only=True, value={"membership_id": "uuid-du-membership"}),
        ],
    )
    def post(self, request):
        serializer = PinResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = Membership.objects.select_related("user", "tenant").get(
                pk=serializer.validated_data["membership_id"]
            )
        except Membership.DoesNotExist:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message="Membership introuvable.", status_code=400)

        if membership.user != request.user and not request.user.is_staff:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Action non autorisée.", status_code=403)

        try:
            PinResetService.request_reset(membership)
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc), status_code=400)
        except Exception:
            return ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Impossible d'envoyer l'email. Vérifiez la configuration SMTP.",
                status_code=500,
            )

        return SuccessResponse(message="Un code de réinitialisation a été envoyé par email.")


class PinResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Confirmer la réinitialisation du PIN",
        description=(
            "Valide le code reçu par email et applique le nouveau PIN sur le membership. "
            "Le code est à usage unique et expiré après utilisation."
        ),
        request=PinResetConfirmSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="Code invalide, expiré ou PIN trop court."),
        },
        tags=["Appartenances — PIN"],
        examples=[
            OpenApiExample(
                "Exemple",
                request_only=True,
                value={"token": "le-code-recu-par-email", "new_pin": "9182"},
            ),
        ],
    )
    def post(self, request):
        serializer = PinResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            PinResetService.confirm_reset(
                token_value=serializer.validated_data["token"],
                new_pin=serializer.validated_data["new_pin"],
            )
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc), status_code=400)

        return SuccessResponse(message="PIN réinitialisé avec succès.")


class RegisterView(CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return SuccessResponse(
            data=UserSerializer(user).data,
            message=SuccessMessage.CREATED,
            status_code=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(
        summary="Lister les utilisateurs",
        description="Retourne tous les utilisateurs de la plateforme, triés par numéro de téléphone.",
        tags=["Utilisateurs"],
    ),
    retrieve=extend_schema(
        summary="Détail d'un utilisateur",
        tags=["Utilisateurs"],
    ),
    create=extend_schema(
        summary="Créer un utilisateur",
        description=(
            "Crée un utilisateur identifié par son téléphone (format E.164). "
            "Le mot de passe est optionnel — l'auth principale se fait par OTP."
        ),
        tags=["Utilisateurs"],
    ),
    update=extend_schema(
        summary="Modifier un utilisateur (remplacement complet)",
        tags=["Utilisateurs"],
    ),
    partial_update=extend_schema(
        summary="Modifier un utilisateur (partiel)",
        tags=["Utilisateurs"],
    ),
    destroy=extend_schema(
        summary="Supprimer un utilisateur",
        tags=["Utilisateurs"],
    ),
)
class _SuccessModelViewSet(viewsets.ModelViewSet):
    """Mixin interne — surcharge les méthodes DRF pour retourner SuccessResponse."""

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return SuccessResponse(data=self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return SuccessResponse(data=serializer.data, message=SuccessMessage.CREATED, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return SuccessResponse(data=serializer.data, message=SuccessMessage.UPDATED)

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return SuccessResponse(message=SuccessMessage.DELETED, status_code=status.HTTP_204_NO_CONTENT)


class UserViewSet(_SuccessModelViewSet):
    queryset = User.objects.all().order_by("phone")
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return SuccessResponse(
            data=UserSerializer(serializer.instance).data,
            message=SuccessMessage.CREATED,
            status_code=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(
        summary="Lister les tenants",
        description="Retourne tous les espaces marchands (boutiques / sociétés).",
        tags=["Tenants"],
    ),
    retrieve=extend_schema(
        summary="Détail d'un tenant",
        tags=["Tenants"],
    ),
    create=extend_schema(
        summary="Créer un tenant",
        description=(
            "Crée un espace marchand. `country` = code ISO 3166-1 alpha-2 (ex: `CM`). "
            "`currency` = code ISO 4217 (ex: `XAF`)."
        ),
        tags=["Tenants"],
    ),
    update=extend_schema(
        summary="Modifier un tenant (remplacement complet)",
        tags=["Tenants"],
    ),
    partial_update=extend_schema(
        summary="Modifier un tenant (partiel)",
        tags=["Tenants"],
    ),
    destroy=extend_schema(
        summary="Supprimer un tenant",
        tags=["Tenants"],
    ),
)
class TenantViewSet(_SuccessModelViewSet):
    queryset = Tenant.objects.all().order_by("name")
    serializer_class = TenantSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(
        summary="Lister les rôles",
        description=(
            "Retourne tous les rôles avec leurs permissions associées. "
            "`tenant = null` indique un rôle système global (ex : SuperAdmin plateforme)."
        ),
        tags=["Rôles"],
    ),
    retrieve=extend_schema(
        summary="Détail d'un rôle",
        tags=["Rôles"],
    ),
    create=extend_schema(
        summary="Créer un rôle",
        description=(
            "Crée un rôle. Laisser `tenant` vide pour un rôle système global. "
            "`expires_at` optionnel pour les rôles temporaires (ex : rôle promotionnel)."
        ),
        tags=["Rôles"],
    ),
    update=extend_schema(
        summary="Modifier un rôle (remplacement complet)",
        tags=["Rôles"],
    ),
    partial_update=extend_schema(
        summary="Modifier un rôle (partiel)",
        tags=["Rôles"],
    ),
    destroy=extend_schema(
        summary="Supprimer un rôle",
        tags=["Rôles"],
    ),
)
class RoleViewSet(_SuccessModelViewSet):
    queryset = Role.objects.select_related("tenant").prefetch_related(
        "role_permissions__permission"
    ).order_by("name")
    serializer_class = RoleSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(
        summary="Lister les appartenances",
        description=(
            "Retourne toutes les appartenances (user × tenant × rôle). "
            "`tenant = null` désigne un rôle plateforme global (ex : staff Kenpro)."
        ),
        tags=["Appartenances"],
    ),
    retrieve=extend_schema(
        summary="Détail d'une appartenance",
        tags=["Appartenances"],
    ),
    create=extend_schema(
        summary="Créer une appartenance",
        description="Affecte un rôle à un utilisateur dans un tenant.",
        tags=["Appartenances"],
    ),
    update=extend_schema(
        summary="Modifier une appartenance (remplacement complet)",
        tags=["Appartenances"],
    ),
    partial_update=extend_schema(
        summary="Modifier une appartenance (partiel)",
        tags=["Appartenances"],
    ),
    destroy=extend_schema(
        summary="Supprimer une appartenance",
        tags=["Appartenances"],
    ),
)
class MembershipViewSet(_SuccessModelViewSet):
    queryset = Membership.objects.select_related("user", "tenant", "role").order_by("created_at")
    serializer_class = MembershipSerializer

    def get_permissions(self):
        # PIN actions are available to authenticated users (own membership only).
        # All CRUD operations require staff.
        if self.action in ("set_pin", "clear_pin", "verify_pin"):
            return [IsAuthenticated()]
        return [IsAdminUser()]

    @extend_schema(
        summary="Définir ou changer le PIN",
        description=(
            "Hache et enregistre un nouveau PIN sur ce membership. "
            "Le PIN doit comporter entre 4 et 16 caractères. "
            "Il sera demandé à chaque action sur un PinScope protégé du tenant."
        ),
        request=SetPinSerializer,
        responses={
            200: _detail_response,
            400: OpenApiResponse(description="PIN trop court ou invalide."),
            404: OpenApiResponse(description="Membership introuvable."),
        },
        tags=["Appartenances — PIN"],
        examples=[
            OpenApiExample("Exemple", request_only=True, value={"pin": "4829"}),
        ],
    )
    @action(detail=True, methods=["post"], url_path="set-pin")
    def set_pin(self, request, pk=None):
        membership = self.get_object()
        if membership.user != request.user and not request.user.is_staff:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Action non autorisée.", status_code=403)
        serializer = SetPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        MembershipService.set_pin(membership, serializer.validated_data["pin"])
        return SuccessResponse(message="PIN défini.")

    @extend_schema(
        summary="Supprimer le PIN",
        description="Efface le PIN de ce membership. L'accès aux ressources PIN-protégées sera bloqué jusqu'à redéfinition.",
        request=None,
        responses={
            200: _detail_response,
            404: OpenApiResponse(description="Membership introuvable."),
        },
        tags=["Appartenances — PIN"],
    )
    @action(detail=True, methods=["post"], url_path="clear-pin")
    def clear_pin(self, request, pk=None):
        membership = self.get_object()
        if membership.user != request.user and not request.user.is_staff:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Action non autorisée.", status_code=403)
        MembershipService.clear_pin(membership)
        return SuccessResponse(message="PIN supprimé.")

    @extend_schema(
        summary="Vérifier le PIN",
        description=(
            "Vérifie que le PIN fourni correspond au PIN stocké sur ce membership. "
            "À appeler avant toute action sur un objet PinScope-protégé. "
            "Retourne `200` si correct, `403` si incorrect ou PIN non défini."
        ),
        request=VerifyPinSerializer,
        responses={
            200: _detail_response,
            403: OpenApiResponse(description="PIN incorrect ou non défini."),
            404: OpenApiResponse(description="Membership introuvable."),
        },
        tags=["Appartenances — PIN"],
        examples=[
            OpenApiExample("Exemple", request_only=True, value={"pin": "4829"}),
        ],
    )
    @action(detail=True, methods=["post"], url_path="verify-pin")
    def verify_pin(self, request, pk=None):
        membership = self.get_object()
        if membership.user != request.user and not request.user.is_staff:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Action non autorisée.", status_code=403)
        serializer = VerifyPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ok, locked = MembershipService.verify_pin(membership, serializer.validated_data["pin"])
        if locked:
            return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="Trop de tentatives. PIN verrouillé.", status_code=403)
        if ok:
            return SuccessResponse(message="PIN valide.")
        return ErrorResponse(error_code=ErrorCode.FORBIDDEN, message="PIN incorrect.", status_code=403)


# ---------------------------------------------------------------------------
# PinScopes
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(
        summary="Lister les périmètres PIN",
        description=(
            "Retourne les types de modèles protégés par PIN dans chaque tenant. "
            "Toute action sur un objet de ce type exige la vérification préalable du PIN admin."
        ),
        tags=["PIN — Périmètres"],
    ),
    retrieve=extend_schema(
        summary="Détail d'un périmètre PIN",
        tags=["PIN — Périmètres"],
    ),
    create=extend_schema(
        summary="Protéger un type de modèle par PIN",
        description=(
            "Marque un type de modèle Django (via son `content_type`) comme protégé par PIN "
            "dans ce tenant. L'admin choisit librement quels types il veut sécuriser. "
            "`label` est une description libre affichée dans l'UI (ex: `Suppression de remise`)."
        ),
        tags=["PIN — Périmètres"],
        examples=[
            OpenApiExample(
                "Protéger les remises",
                request_only=True,
                value={"tenant": "uuid-tenant", "content_type": 12, "label": "Suppression de remise"},
            ),
        ],
    ),
    update=extend_schema(
        summary="Modifier un périmètre PIN (remplacement complet)",
        tags=["PIN — Périmètres"],
    ),
    partial_update=extend_schema(
        summary="Modifier un périmètre PIN (partiel)",
        tags=["PIN — Périmètres"],
    ),
    destroy=extend_schema(
        summary="Retirer la protection PIN d'un type de modèle",
        tags=["PIN — Périmètres"],
    ),
)
class PinScopeViewSet(_SuccessModelViewSet):
    queryset = PinScope.objects.select_related("tenant", "content_type").order_by("tenant__name")
    serializer_class = PinScopeSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Back-office Super Admin — Plans
# ---------------------------------------------------------------------------

_TAG_ADMIN = "Super Admin"


@extend_schema_view(
    list=extend_schema(summary="Lister les plans", tags=[_TAG_ADMIN]),
    retrieve=extend_schema(summary="Détail d'un plan", tags=[_TAG_ADMIN]),
    create=extend_schema(summary="Créer un plan", tags=[_TAG_ADMIN]),
    update=extend_schema(summary="Modifier un plan", tags=[_TAG_ADMIN]),
    partial_update=extend_schema(summary="Modifier un plan (partiel)", tags=[_TAG_ADMIN]),
    destroy=extend_schema(summary="Supprimer un plan", tags=[_TAG_ADMIN]),
)
class PlanViewSet(_SuccessModelViewSet):
    queryset = Plan.objects.order_by("monthly_price")
    serializer_class = PlanSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Back-office Super Admin — Abonnements
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les abonnements", tags=[_TAG_ADMIN]),
    retrieve=extend_schema(summary="Détail d'un abonnement", tags=[_TAG_ADMIN]),
)
class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subscription.objects.select_related("tenant", "plan").order_by("-created_at")
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAdminUser]

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        # Filtres query params
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(SubscriptionSerializer(page, many=True).data)
        return SuccessResponse(data=SubscriptionSerializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=SubscriptionSerializer(self.get_object()).data)

    @extend_schema(
        summary="Démarrer la période d'essai d'un tenant",
        request=StartTrialSerializer,
        tags=[_TAG_ADMIN],
    )
    @action(detail=False, methods=["post"], url_path="start-trial")
    def start_trial(self, request):
        s = StartTrialSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            tenant = Tenant.objects.get(pk=d["tenant"])
            plan = Plan.objects.get(pk=d["plan"])
            sub = SubscriptionService.start_trial(tenant, plan, d.get("trial_days"))
        except (Tenant.DoesNotExist, Plan.DoesNotExist) as exc:
            return ErrorResponse(error_code=ErrorCode.NOT_FOUND, message=str(exc))
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.CONFLICT, message=str(exc))
        return SuccessResponse(
            data=SubscriptionSerializer(sub).data,
            message=SuccessMessage.CREATED,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Activer / convertir un abonnement",
        request=ActivateSerializer,
        tags=[_TAG_ADMIN],
    )
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        sub = self.get_object()
        s = ActivateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        plan = None
        if plan_id := s.validated_data.get("plan"):
            try:
                plan = Plan.objects.get(pk=plan_id)
            except Plan.DoesNotExist:
                return ErrorResponse(error_code=ErrorCode.NOT_FOUND, message="Plan introuvable.")
        try:
            sub = SubscriptionService.activate(sub, plan)
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc))
        return SuccessResponse(data=SubscriptionSerializer(sub).data, message="Abonnement activé.")

    @extend_schema(
        summary="Suspendre un abonnement",
        tags=[_TAG_ADMIN],
    )
    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, pk=None):
        sub = self.get_object()
        try:
            sub = SubscriptionService.suspend(sub)
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc))
        return SuccessResponse(data=SubscriptionSerializer(sub).data, message="Abonnement suspendu.")

    @extend_schema(
        summary="Prolonger la période d'essai",
        request=ExtendTrialSerializer,
        tags=[_TAG_ADMIN],
    )
    @action(detail=True, methods=["post"], url_path="extend-trial")
    def extend_trial(self, request, pk=None):
        sub = self.get_object()
        s = ExtendTrialSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            sub = SubscriptionService.extend_trial(sub, s.validated_data["extra_days"])
        except ValueError as exc:
            return ErrorResponse(error_code=ErrorCode.BAD_REQUEST, message=str(exc))
        return SuccessResponse(data=SubscriptionSerializer(sub).data, message="Essai prolongé.")


# ---------------------------------------------------------------------------
# Back-office Super Admin — Flags de services métier
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="Lister les flags de services", tags=[_TAG_ADMIN]),
    retrieve=extend_schema(summary="Détail d'un flag", tags=[_TAG_ADMIN]),
)
class ServiceFlagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceFlag.objects.select_related("tenant").order_by("tenant__name", "service")
    serializer_class = ServiceFlagSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        if tenant_id := self.request.query_params.get("tenant"):
            qs = qs.filter(tenant=tenant_id)
        if service := self.request.query_params.get("service"):
            qs = qs.filter(service=service)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ServiceFlagSerializer(page, many=True).data)
        return SuccessResponse(data=ServiceFlagSerializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return SuccessResponse(data=ServiceFlagSerializer(self.get_object()).data)

    @extend_schema(
        summary="Activer un service métier pour un tenant",
        request=ServiceFlagInputSerializer,
        tags=[_TAG_ADMIN],
    )
    @action(detail=False, methods=["post"], url_path="enable")
    def enable(self, request):
        s = ServiceFlagInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            tenant = Tenant.objects.get(pk=s.validated_data["tenant"])
        except Tenant.DoesNotExist:
            return ErrorResponse(error_code=ErrorCode.NOT_FOUND, message="Tenant introuvable.")
        flag = ServiceFlagService.enable(tenant, s.validated_data["service"])
        return SuccessResponse(data=ServiceFlagSerializer(flag).data, message="Service activé.")

    @extend_schema(
        summary="Désactiver un service métier pour un tenant",
        request=ServiceFlagInputSerializer,
        tags=[_TAG_ADMIN],
    )
    @action(detail=False, methods=["post"], url_path="disable")
    def disable(self, request):
        s = ServiceFlagInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            tenant = Tenant.objects.get(pk=s.validated_data["tenant"])
        except Tenant.DoesNotExist:
            return ErrorResponse(error_code=ErrorCode.NOT_FOUND, message="Tenant introuvable.")
        flag = ServiceFlagService.disable(tenant, s.validated_data["service"])
        return SuccessResponse(data=ServiceFlagSerializer(flag).data, message="Service désactivé.")