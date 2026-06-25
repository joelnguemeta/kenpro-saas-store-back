from enum import StrEnum


class SuccessMessage(StrEnum):
    OPERATION_SUCCESSFUL = "Opération effectuée avec succès."
    CREATED = "Ressource créée avec succès."
    UPDATED = "Ressource mise à jour avec succès."
    DELETED = "Ressource supprimée avec succès."


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNPROCESSABLE = "UNPROCESSABLE_ENTITY"
    INTERNAL_ERROR = "INTERNAL_SERVER_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    THROTTLED = "THROTTLED"

    @property
    def default_message(self) -> str:
        _messages: dict[str, str] = {
            "BAD_REQUEST": "Requête invalide.",
            "UNAUTHORIZED": "Authentification requise.",
            "FORBIDDEN": "Vous n'avez pas la permission d'effectuer cette action.",
            "NOT_FOUND": "La ressource demandée est introuvable.",
            "CONFLICT": "Conflit avec l'état actuel de la ressource.",
            "UNPROCESSABLE_ENTITY": "La requête n'a pas pu être traitée.",
            "INTERNAL_SERVER_ERROR": "Une erreur interne est survenue.",
            "VALIDATION_ERROR": "Données invalides.",
            "THROTTLED": "Trop de requêtes. Veuillez réessayer plus tard.",
        }
        return _messages.get(self.value, "Une erreur est survenue.")
