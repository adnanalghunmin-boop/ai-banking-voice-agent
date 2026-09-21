def mask(value: str | None, keep_last: int = 4) -> str:
    """Mask a sensitive string, keeping only the last `keep_last` characters."""
    if not value:
        return "***"
    if len(value) <= keep_last:
        return "*" * len(value)
    return "*" * (len(value) - keep_last) + value[-keep_last:]


def mask_card_number(card_number: str) -> str:
    """Mask a card number for API responses: a fixed 4-asterisk prefix plus
    the last 4 digits (e.g. "****5678"), never the full number."""
    return "****" + card_number[-4:]
