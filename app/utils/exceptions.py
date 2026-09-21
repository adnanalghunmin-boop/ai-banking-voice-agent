class DatabaseUnavailableError(Exception):
    """Raised when the database cannot be reached or a query fails.

    The original exception is intentionally not attached to the message so
    that raw Oracle errors never leak to API clients. Full details are logged
    server-side instead.
    """


class NotFoundError(Exception):
    """Raised when a referenced resource does not exist, or does not belong
    to the customer/account context supplied in the request. Maps to HTTP 404.
    """

    def __init__(self, message: str = "Resource not found."):
        self.message = message
        super().__init__(message)


class BusinessRuleError(Exception):
    """Raised when a request is well-formed but violates a business rule
    (missing confirmation, invalid state transition, invalid limit, etc).
    Maps to HTTP 400. The message is always safe to return to the client.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidSessionError(Exception):
    """Raised when a verification token is missing, malformed, unknown,
    expired, or deactivated. Always maps to HTTP 401 with the exact same
    generic message regardless of which of those it was - the caller must
    never be able to tell a token apart by why it was rejected.
    """

    def __init__(self, message: str = "Invalid or expired verification session"):
        self.message = message
        super().__init__(message)
