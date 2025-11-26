"""Custom exceptions."""


class BaseAppException(Exception):
    """Base exception for application."""
    pass


class ValidationError(BaseAppException):
    """Validation error."""
    pass


class NotFoundError(BaseAppException):
    """Resource not found."""
    pass
