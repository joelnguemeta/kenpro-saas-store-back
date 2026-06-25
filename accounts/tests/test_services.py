"""
Tests unitaires de la couche service (accounts/services.py).
Aucun appel HTTP — on teste la logique métier pure.
"""
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.utils import timezone

from accounts.models import Membership, PasswordResetToken, PinResetToken, PinScope, Role, RolePermission
from accounts.services import (
    MembershipService,
    PasswordChangeService,
    PasswordResetService,
    PinResetService,
    PinScopeService,
    RoleService,
    TenantService,
    UserService,
)

from .factories import (
    get_any_permission,
    get_content_type_for,
    make_membership,
    make_role,
    make_tenant,
    make_user,
)


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------

class UserServiceCreateTest(TestCase):

    def test_creer_utilisateur_sans_mot_de_passe(self):
        user = UserService.create(phone="+237600000001")
        self.assertEqual(user.phone, "+237600000001")
        self.assertFalse(user.has_usable_password())

    def test_creer_utilisateur_avec_mot_de_passe(self):
        user = UserService.create(phone="+237600000002", password="secret123")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("secret123"))

    def test_phone_unique(self):
        UserService.create(phone="+237600000003")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            UserService.create(phone="+237600000003")

    def test_champs_optionnels(self):
        user = UserService.create(phone="+237600000004", email="a@b.com", full_name="Alice")
        self.assertEqual(user.email, "a@b.com")
        self.assertEqual(user.full_name, "Alice")

    def test_is_active_par_defaut(self):
        user = UserService.create(phone="+237600000005")
        self.assertTrue(user.is_active)


class UserServiceGetTest(TestCase):

    def test_get_by_phone_existant(self):
        make_user(phone="+237600000010")
        user = UserService.get_by_phone("+237600000010")
        self.assertEqual(user.phone, "+237600000010")

    def test_get_by_phone_introuvable(self):
        from accounts.models import User
        with self.assertRaises(User.DoesNotExist):
            UserService.get_by_phone("+237699999999")


# ---------------------------------------------------------------------------
# TenantService
# ---------------------------------------------------------------------------

class TenantServiceTest(TestCase):

    def test_creer_tenant(self):
        t = TenantService.create(name="Kenpro Shop", slug="kenpro-shop", country="CM", currency="XAF")
        self.assertEqual(t.slug, "kenpro-shop")
        self.assertEqual(t.country, "CM")
        self.assertTrue(t.is_active)

    def test_slug_unique(self):
        TenantService.create(name="A", slug="same-slug", country="SN", currency="XOF")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TenantService.create(name="B", slug="same-slug", country="CI", currency="XOF")


# ---------------------------------------------------------------------------
# RoleService
# ---------------------------------------------------------------------------

class RoleServiceCreateTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant()

    def test_creer_role_tenant(self):
        role = RoleService.create("Caissier", self.tenant)
        self.assertEqual(role.name, "Caissier")
        self.assertEqual(role.tenant, self.tenant)
        self.assertFalse(role.is_system)

    def test_creer_role_systeme_global(self):
        role = RoleService.create("SuperAdmin", is_system=True)
        self.assertIsNone(role.tenant)
        self.assertTrue(role.is_system)

    def test_unicite_nom_par_tenant(self):
        RoleService.create("Vendeur", self.tenant)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            RoleService.create("Vendeur", self.tenant)

    def test_role_avec_expiration(self):
        expires = timezone.now() + timedelta(days=30)
        role = RoleService.create("Promo", self.tenant, expires_at=expires)
        self.assertIsNotNone(role.expires_at)
        self.assertFalse(RoleService.is_expired(role))

    def test_role_expire(self):
        past = timezone.now() - timedelta(seconds=1)
        role = RoleService.create("Ancien", self.tenant, expires_at=past)
        self.assertTrue(RoleService.is_expired(role))

    def test_role_permanent_non_expire(self):
        role = RoleService.create("Permanent", self.tenant)
        self.assertFalse(RoleService.is_expired(role))


class RoleServicePermissionTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant()
        self.role = make_role(tenant=self.tenant)
        self.perm = get_any_permission()

    def test_assigner_permission(self):
        rp = RoleService.assign_permission(self.role, self.perm)
        self.assertIsInstance(rp, RolePermission)
        self.assertEqual(rp.role, self.role)

    def test_assigner_permission_idempotent(self):
        RoleService.assign_permission(self.role, self.perm)
        RoleService.assign_permission(self.role, self.perm)
        self.assertEqual(RolePermission.objects.filter(role=self.role).count(), 1)

    def test_assigner_permission_avec_contraintes_abac(self):
        rp = RoleService.assign_permission(self.role, self.perm, constraints={"max_discount_percent": 10})
        self.assertEqual(rp.constraints["max_discount_percent"], 10)

    def test_retirer_permission(self):
        RoleService.assign_permission(self.role, self.perm)
        RoleService.remove_permission(self.role, self.perm)
        self.assertFalse(RolePermission.objects.filter(role=self.role, permission=self.perm).exists())

    def test_retirer_permission_inexistante_sans_erreur(self):
        RoleService.remove_permission(self.role, self.perm)  # ne lève pas d'exception


# ---------------------------------------------------------------------------
# MembershipService
# ---------------------------------------------------------------------------

class MembershipServiceCreateTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.tenant = make_tenant()
        self.role = make_role(tenant=self.tenant)

    def test_creer_membership(self):
        m = MembershipService.create(self.user, self.role, self.tenant)
        self.assertEqual(m.user, self.user)
        self.assertEqual(m.tenant, self.tenant)
        self.assertTrue(m.is_active)

    def test_membership_global_sans_tenant(self):
        role_global = make_role(name="PlatformAdmin", tenant=None)
        m = MembershipService.create(self.user, role_global, tenant=None)
        self.assertIsNone(m.tenant)

    def test_unicite_user_tenant_role(self):
        MembershipService.create(self.user, self.role, self.tenant)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            MembershipService.create(self.user, self.role, self.tenant)

    def test_membership_expire(self):
        past = timezone.now() - timedelta(seconds=1)
        m = MembershipService.create(self.user, self.role, self.tenant, expires_at=past)
        self.assertTrue(MembershipService.is_expired(m))

    def test_membership_non_expire(self):
        future = timezone.now() + timedelta(days=1)
        m = MembershipService.create(self.user, self.role, self.tenant, expires_at=future)
        self.assertFalse(MembershipService.is_expired(m))

    def test_membership_permanent(self):
        m = MembershipService.create(self.user, self.role, self.tenant)
        self.assertFalse(MembershipService.is_expired(m))


class MembershipServicePinTest(TestCase):

    def setUp(self):
        self.membership = make_membership()

    def test_set_pin_hash_le_pin(self):
        MembershipService.set_pin(self.membership, "1234")
        self.membership.refresh_from_db()
        self.assertNotEqual(self.membership.pin, "1234")
        self.assertTrue(check_password("1234", self.membership.pin))

    def test_set_pin_trop_court_leve_erreur(self):
        with self.assertRaises(ValueError):
            MembershipService.set_pin(self.membership, "123")

    def test_set_pin_vide_leve_erreur(self):
        with self.assertRaises(ValueError):
            MembershipService.set_pin(self.membership, "")

    def test_verify_pin_correct(self):
        MembershipService.set_pin(self.membership, "9876")
        self.membership.refresh_from_db()
        self.assertTrue(MembershipService.verify_pin(self.membership, "9876"))

    def test_verify_pin_incorrect(self):
        MembershipService.set_pin(self.membership, "9876")
        self.membership.refresh_from_db()
        self.assertFalse(MembershipService.verify_pin(self.membership, "0000"))

    def test_verify_pin_sans_pin_defini(self):
        self.assertFalse(MembershipService.verify_pin(self.membership, "1234"))

    def test_clear_pin(self):
        MembershipService.set_pin(self.membership, "5555")
        MembershipService.clear_pin(self.membership)
        self.membership.refresh_from_db()
        self.assertIsNone(self.membership.pin)
        self.assertFalse(self.membership.has_pin)

    def test_has_pin_property(self):
        self.assertFalse(self.membership.has_pin)
        MembershipService.set_pin(self.membership, "4321")
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.has_pin)

    def test_check_pin_required_avec_scope(self):
        PinScopeService.protect(self.membership.tenant, Role)
        self.assertTrue(MembershipService.check_pin_required(self.membership, Role))

    def test_check_pin_required_sans_scope(self):
        self.assertFalse(MembershipService.check_pin_required(self.membership, Role))

    def test_check_pin_required_membership_global(self):
        """Un membership sans tenant ne nécessite jamais de PIN (pas de PinScope applicable)."""
        role = make_role(name="Global")
        user = make_user(phone="+237600000098")
        m = Membership.objects.create(user=user, tenant=None, role=role)
        self.assertFalse(MembershipService.check_pin_required(m, Role))


# ---------------------------------------------------------------------------
# PinScopeService
# ---------------------------------------------------------------------------

class PasswordResetServiceTest(TestCase):

    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    def setUp(self):
        self.user = make_user(phone="+237600000050")
        self.user.email = "bob@example.com"
        self.user.set_password("ancienMotDePasse")
        self.user.save()

    def test_request_reset_cree_token(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            PasswordResetService.request_reset("bob@example.com")
        self.assertEqual(PasswordResetToken.objects.filter(user=self.user).count(), 1)

    def test_request_reset_envoie_email(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            PasswordResetService.request_reset("bob@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("bob@example.com", mail.outbox[0].to)

    def test_request_reset_email_inconnu_leve_erreur(self):
        with self.assertRaises(ValueError):
            PasswordResetService.request_reset("inconnu@example.com")

    def test_request_reset_invalide_anciens_jetons(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            PasswordResetService.request_reset("bob@example.com")
            PasswordResetService.request_reset("bob@example.com")
        valides = PasswordResetToken.objects.filter(user=self.user, used=False)
        self.assertEqual(valides.count(), 1)

    def test_confirm_reset_applique_nouveau_mot_de_passe(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            token = PasswordResetService.request_reset("bob@example.com")
        PasswordResetService.confirm_reset(token.token, "nouveauMotDePasse123")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nouveauMotDePasse123"))

    def test_confirm_reset_invalide_le_jeton(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            token = PasswordResetService.request_reset("bob@example.com")
        PasswordResetService.confirm_reset(token.token, "nouveauMotDePasse123")
        token.refresh_from_db()
        self.assertTrue(token.used)

    def test_confirm_reset_jeton_inconnu_leve_erreur(self):
        with self.assertRaises(ValueError):
            PasswordResetService.confirm_reset("jeton-inexistant", "motdepasse123")

    def test_confirm_reset_jeton_expire_leve_erreur(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            token = PasswordResetService.request_reset("bob@example.com")
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        with self.assertRaises(ValueError):
            PasswordResetService.confirm_reset(token.token, "motdepasse123")

    def test_confirm_reset_jeton_deja_utilise_leve_erreur(self):
        with self.settings(EMAIL_BACKEND=self.EMAIL_BACKEND):
            token = PasswordResetService.request_reset("bob@example.com")
        PasswordResetService.confirm_reset(token.token, "motdepasse123")
        with self.assertRaises(ValueError):
            PasswordResetService.confirm_reset(token.token, "autreMotDePasse")


class PasswordChangeServiceTest(TestCase):

    def setUp(self):
        self.user = make_user(phone="+237600000060")
        self.user.set_password("ancienMotDePasse")
        self.user.save()

    def test_changer_mot_de_passe(self):
        PasswordChangeService.change(self.user, "ancienMotDePasse", "nouveauMotDePasse123")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nouveauMotDePasse123"))

    def test_mot_de_passe_actuel_incorrect_leve_erreur(self):
        with self.assertRaises(ValueError):
            PasswordChangeService.change(self.user, "mauvaisMotDePasse", "nouveauMotDePasse123")

    def test_compte_otp_sans_mot_de_passe_leve_erreur(self):
        user_otp = make_user(phone="+237600000061")  # sans password → unusable
        with self.assertRaises(ValueError):
            PasswordChangeService.change(user_otp, "", "nouveauMotDePasse123")


class PinResetServiceTest(TestCase):

    def setUp(self):
        self.membership = make_membership()
        self.membership.user.email = "alice@example.com"
        self.membership.user.save()

    def test_request_reset_cree_token(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            PinResetService.request_reset(self.membership)
        self.assertEqual(PinResetToken.objects.filter(membership=self.membership).count(), 1)

    def test_request_reset_envoie_email(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            PinResetService.request_reset(self.membership)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alice@example.com", mail.outbox[0].to)

    def test_request_reset_sans_email_leve_erreur(self):
        self.membership.user.email = None
        self.membership.user.save()
        with self.assertRaises(ValueError):
            PinResetService.request_reset(self.membership)

    def test_request_reset_invalide_anciens_jetons(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            PinResetService.request_reset(self.membership)
            PinResetService.request_reset(self.membership)
        # Seul le dernier est valide
        tokens = PinResetToken.objects.filter(membership=self.membership, used=False)
        self.assertEqual(tokens.count(), 1)

    def test_confirm_reset_applique_nouveau_pin(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            token = PinResetService.request_reset(self.membership)
        PinResetService.confirm_reset(token.token, "9876")
        self.membership.refresh_from_db()
        self.assertTrue(MembershipService.verify_pin(self.membership, "9876"))

    def test_confirm_reset_invalide_le_jeton(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            token = PinResetService.request_reset(self.membership)
        PinResetService.confirm_reset(token.token, "9876")
        token.refresh_from_db()
        self.assertTrue(token.used)

    def test_confirm_reset_jeton_inconnu_leve_erreur(self):
        with self.assertRaises(ValueError, msg="Jeton invalide."):
            PinResetService.confirm_reset("jeton-qui-nexiste-pas", "1234")

    def test_confirm_reset_jeton_deja_utilise_leve_erreur(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            token = PinResetService.request_reset(self.membership)
        PinResetService.confirm_reset(token.token, "1234")
        with self.assertRaises(ValueError):
            PinResetService.confirm_reset(token.token, "5678")

    def test_confirm_reset_jeton_expire_leve_erreur(self):
        from datetime import timedelta
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            token = PinResetService.request_reset(self.membership)
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        with self.assertRaises(ValueError):
            PinResetService.confirm_reset(token.token, "4321")

    def test_token_is_valid_property(self):
        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            token = PinResetService.request_reset(self.membership)
        self.assertTrue(token.is_valid)
        token.used = True
        token.save()
        self.assertFalse(token.is_valid)


class PinScopeServiceTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant()

    def test_proteger_un_modele(self):
        scope = PinScopeService.protect(self.tenant, Role, label="Gestion des rôles")
        self.assertIsInstance(scope, PinScope)
        self.assertEqual(scope.label, "Gestion des rôles")

    def test_protect_idempotent(self):
        PinScopeService.protect(self.tenant, Role)
        PinScopeService.protect(self.tenant, Role)
        self.assertEqual(PinScope.objects.filter(tenant=self.tenant).count(), 1)

    def test_is_protected_vrai(self):
        PinScopeService.protect(self.tenant, Role)
        self.assertTrue(PinScopeService.is_protected(self.tenant, Role))

    def test_is_protected_faux(self):
        self.assertFalse(PinScopeService.is_protected(self.tenant, Role))

    def test_unprotect(self):
        PinScopeService.protect(self.tenant, Role)
        PinScopeService.unprotect(self.tenant, Role)
        self.assertFalse(PinScopeService.is_protected(self.tenant, Role))

    def test_unprotect_inexistant_sans_erreur(self):
        PinScopeService.unprotect(self.tenant, Role)  # ne lève pas d'exception

    def test_scopes_independants_par_tenant(self):
        tenant2 = make_tenant(name="Autre", slug="autre")
        PinScopeService.protect(self.tenant, Role)
        self.assertFalse(PinScopeService.is_protected(tenant2, Role))
