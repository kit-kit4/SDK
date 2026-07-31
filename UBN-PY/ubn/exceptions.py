class UBNError(Exception):
    """Базовий виняток SDK."""

class UBNAuthError(UBNError):
    """Помилка авторизації (401)."""

class UBNRateLimitError(UBNError):
    """Перевищено ліміт (429)."""

class UBNValidationError(UBNError):
    """Помилка валідації даних."""

class UBNConfigError(UBNError):
    """Помилка конфігурації."""