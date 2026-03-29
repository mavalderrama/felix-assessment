class DomainError(Exception):
    """Base class for domain errors."""


class InvalidFieldError(DomainError):
    """Raised when a transfer field value is invalid."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"Invalid value for '{field}': {reason}")


class UnsupportedCorridorError(DomainError):
    """Raised when a country/delivery-method combination is not supported."""

    def __init__(self, country: str, delivery_method: str) -> None:
        self.country = country
        self.delivery_method = delivery_method
        super().__init__(
            f"Corridor '{country}/{delivery_method}' is not supported."
        )


class AuthenticationError(DomainError):
    """Raised when login credentials are invalid."""

    def __init__(self, message: str = "Invalid username or password.") -> None:
        super().__init__(message)


class UsernameAlreadyExistsError(DomainError):
    """Raised when trying to create an account with a username already taken."""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"Username '{username}' is already taken.")


class InsufficientFundsError(DomainError):
    """Raised when the account balance is too low to cover a transfer."""

    def __init__(self, required: str, available: str) -> None:
        self.required = required
        self.available = available
        super().__init__(f"Insufficient funds: need {required}, have {available}.")


class TransferNotFoundError(DomainError):
    """Raised when a transfer record cannot be found."""

    def __init__(self, transfer_id: str) -> None:
        self.transfer_id = transfer_id
        super().__init__(f"Transfer '{transfer_id}' not found.")
