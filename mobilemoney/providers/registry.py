"""
Registre des providers Mobile Money.

Usage :
    @register_provider
    class MTNProvider(MobileMoneyProvider): ...

    provider = get_provider("mtn")   # → instance MTNProvider
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import MobileMoneyProvider

_registry: dict[str, type["MobileMoneyProvider"]] = {}


def register_provider(cls: type["MobileMoneyProvider"]) -> type["MobileMoneyProvider"]:
    """Décorateur : enregistre le provider dans le registre global."""
    _registry[cls.operator_code.fget(cls)] = cls  # type: ignore[attr-defined]
    return cls


def get_provider(operator_code: str) -> "MobileMoneyProvider":
    """
    Retourne une instance du provider correspondant à l'opérateur.
    Lève ValueError si l'opérateur n'est pas enregistré.
    """
    # Import ici pour forcer l'enregistrement des providers concrets.
    from . import mtn, orange  # noqa: F401

    cls = _registry.get(operator_code)
    if cls is None:
        available = ", ".join(_registry.keys()) or "aucun"
        raise ValueError(
            f"Provider Mobile Money inconnu : '{operator_code}'. "
            f"Disponibles : {available}."
        )
    return cls()
