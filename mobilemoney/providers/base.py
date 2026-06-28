"""
Contrat abstrait que chaque provider Mobile Money doit implémenter.

Deux opérations fondamentales :
  - initiate()   : envoie la demande de paiement à l'opérateur.
  - check_status(): interroge l'opérateur pour connaître l'état courant.

Les providers concrets (MTN, Orange) s'enregistrent dans le registre via
@register_provider et sont sélectionnés à l'exécution par get_provider().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PaymentRequest:
    """Paramètres d'une demande de paiement Mobile Money."""
    payer_phone: str       # E.164, ex : "+237600000001"
    amount: Decimal
    currency: str          # ISO 4217, ex : "XAF"
    reference: str         # Référence interne (N° vente)
    description: str = ""


@dataclass
class PaymentResult:
    """Résultat retourné par le provider après une opération."""
    success: bool
    external_id: str = ""           # ID transaction côté opérateur
    status: str = "pending"         # "pending" | "confirmed" | "failed"
    failure_reason: str = ""
    raw: dict = field(default_factory=dict)  # Payload brut opérateur


class MobileMoneyProvider(ABC):
    """
    Interface commune à tous les opérateurs Mobile Money.
    Chaque opérateur hérite de cette classe et implémente les deux méthodes.
    """

    @property
    @abstractmethod
    def operator_code(self) -> str:
        """Code court de l'opérateur — doit correspondre à Operator.choices."""

    @abstractmethod
    def initiate(self, request: PaymentRequest) -> PaymentResult:
        """
        Envoie la demande de débit vers l'opérateur.
        Retourne un PaymentResult avec status='pending' si la demande est
        acceptée (le client doit encore valider sur son téléphone).
        """

    @abstractmethod
    def check_status(self, external_id: str) -> PaymentResult:
        """
        Interroge l'opérateur sur l'état d'une transaction existante.
        Utilisé pour le polling (F-19) ou les webhooks.
        """
