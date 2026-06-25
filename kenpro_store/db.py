"""
Bases de modèles partagées par toutes les apps métier (inventory, sales,
promotions). Abstraites → aucune table propre, aucune migration.

Conventions transversales (cf. plan des modèles) :
  - UUID en clé primaire partout.
  - Multi-tenant : chaque modèle métier porte un `tenant`.
  - Timestamps d'audit (`created_at`, `updated_at`).
"""
import uuid

from django.conf import settings
from django.db import models


class UUIDModel(models.Model):
    """Clé primaire UUID, non éditable."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Horodatage de création et de dernière modification."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantOwnedModel(UUIDModel, TimeStampedModel):
    """
    Modèle métier appartenant à un tenant. Toutes les requêtes en aval
    doivent être filtrées par le tenant actif (request.tenant) — rien ne
    fuit d'une boutique à l'autre.
    """
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        abstract = True


class AuthoredModel(models.Model):
    """Trace l'utilisateur à l'origine de l'enregistrement (audit)."""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True
