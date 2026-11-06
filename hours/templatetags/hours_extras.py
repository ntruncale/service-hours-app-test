from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def hrs(value) -> str:
    """1.50 -> '1.5', 2.00 -> '2'."""
    if value is None:
        return "0"
    value = Decimal(value).normalize()
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@register.filter
def pct(part, whole) -> int:
    try:
        return max(0, min(100, int(Decimal(part) / Decimal(whole) * 100)))
    except Exception:
        return 0
