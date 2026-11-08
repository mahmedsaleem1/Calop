"""Errors raised by services and integrations, free of any web-framework dependency.
`app.main` turns each one into {"error": {"code", "message", "request_id"}}."""


class ApplicationError(Exception):
    default_status_code = 500
    default_code = "internal_error"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code if status_code is not None else self.default_status_code
        self.code = code or self.default_code


class AuthError(ApplicationError):
    default_status_code = 401
    default_code = "unauthorized"


class NotFoundError(ApplicationError):
    default_status_code = 404
    default_code = "not_found"


class ConflictError(ApplicationError):
    default_status_code = 409
    default_code = "conflict"


class PayloadTooLargeError(ApplicationError):
    default_status_code = 413
    default_code = "payload_too_large"


class UnsupportedMediaTypeError(ApplicationError):
    default_status_code = 415
    default_code = "unsupported_media_type"


class UnprocessableInputError(ApplicationError):
    default_status_code = 422
    default_code = "invalid_input"


class BadGatewayError(ApplicationError):
    default_status_code = 502
    default_code = "bad_gateway"
