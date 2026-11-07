"""Errors raised by services and integrations, free of any web-framework dependency.
`app.main` turns each one into an HTTP response of the form {"detail": message}."""


class ApplicationError(Exception):
    default_status_code = 500

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code if status_code is not None else self.default_status_code


class AuthError(ApplicationError):
    default_status_code = 401


class NotFoundError(ApplicationError):
    default_status_code = 404


class ConflictError(ApplicationError):
    default_status_code = 409


class PayloadTooLargeError(ApplicationError):
    default_status_code = 413


class UnsupportedMediaTypeError(ApplicationError):
    default_status_code = 415


class UnprocessableInputError(ApplicationError):
    default_status_code = 422


class BadGatewayError(ApplicationError):
    default_status_code = 502
