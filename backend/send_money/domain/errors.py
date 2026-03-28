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


class TransferNotFoundError(DomainError):
    """Raised when a transfer record cannot be found."""

    def __init__(self, transfer_id: str) -> None:
        self.transfer_id = transfer_id
        super().__init__(f"Transfer '{transfer_id}' not found.")
