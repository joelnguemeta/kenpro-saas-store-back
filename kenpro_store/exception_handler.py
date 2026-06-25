from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler

from .enums import ErrorCode
from .responses import ErrorResponse


def custom_exception_handler(exc, context):
    # Convertit les exceptions Django non-DRF avant de passer au handler de base,
    # afin qu'elles soient loguées proprement et traitées comme des APIException.
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        # ValidationError Django (levée dans model.save()) → 422
        messages = list(exc.messages) if hasattr(exc, "messages") else [str(exc)]
        return ErrorResponse(
            error_code=ErrorCode.VALIDATION_ERROR,
            details={"non_field_errors": messages},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    elif isinstance(exc, ProtectedError):
        # Suppression bloquée par une FK PROTECT — message métier sans fuite interne
        protected_models = {obj.__class__.__name__ for obj in exc.protected_objects}
        names = ", ".join(sorted(protected_models))
        return ErrorResponse(
            error_code=ErrorCode.CONFLICT,
            message=f"Suppression impossible : cet objet est référencé par {names}.",
            status_code=status.HTTP_409_CONFLICT,
        )
    elif isinstance(exc, IntegrityError):
        return ErrorResponse(
            error_code=ErrorCode.CONFLICT,
            message="Violation de contrainte d'unicité.",
            status_code=status.HTTP_409_CONFLICT,
        )

    response = exception_handler(exc, context)

    if response is None:
        return None

    if isinstance(exc, ValidationError):
        return ErrorResponse(
            error_code=ErrorCode.VALIDATION_ERROR,
            details=response.data,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if isinstance(exc, NotAuthenticated | AuthenticationFailed):
        return ErrorResponse(
            error_code=ErrorCode.UNAUTHORIZED,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, PermissionDenied):
        return ErrorResponse(
            error_code=ErrorCode.FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, NotFound):
        return ErrorResponse(
            error_code=ErrorCode.NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, Throttled):
        return ErrorResponse(
            error_code=ErrorCode.THROTTLED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Toute autre APIException (ex. MethodNotAllowed, UnsupportedMediaType…) :
    # on retourne le code HTTP que DRF a déjà calculé, sans écraser en 500.
    if isinstance(exc, APIException):
        return ErrorResponse(
            error_code=ErrorCode.BAD_REQUEST,
            message=str(exc.detail) if hasattr(exc, "detail") else str(exc),
            status_code=response.status_code,
        )

    return ErrorResponse(
        error_code=ErrorCode.INTERNAL_ERROR,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
