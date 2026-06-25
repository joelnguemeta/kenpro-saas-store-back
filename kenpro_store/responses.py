from typing import Any

from rest_framework import status
from rest_framework.response import Response

from .enums import ErrorCode, SuccessMessage


class SuccessResponse(Response):
    """
    Réponse unifiée pour les opérations réussies.

    {
        "success": true,
        "message": "...",
        "data": { ... }
    }
    """

    def __init__(
        self,
        data: Any = None,
        message: str = SuccessMessage.OPERATION_SUCCESSFUL.value,
        status_code: int = status.HTTP_200_OK,
        **kwargs,
    ) -> None:
        body: dict[str, Any] = {
            "success": True,
            "message": message,
        }
        if data is not None:
            body["data"] = data
        super().__init__(data=body, status=status_code, **kwargs)


class ErrorResponse(Response):
    """
    Réponse unifiée pour les opérations en erreur.

    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "...",
            "details": { ... }
        }
    }
    """

    def __init__(
        self,
        error_code: ErrorCode,
        message: str | None = None,
        details: dict | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        **kwargs,
    ) -> None:
        error_content: dict[str, Any] = {
            "code": error_code.value,
            "message": message or error_code.default_message,
        }
        if details:
            error_content["details"] = details
        body = {
            "success": False,
            "error": error_content,
        }
        super().__init__(data=body, status=status_code, **kwargs)
