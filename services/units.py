"""
Unit conversion service.

All quantities are stored in an item's BASE unit (kg, L, piece).
Conversion priority: item-specific DB row → global DB row → hardcoded STANDARD_CONVERSIONS.
Bidirectional: if A→B is known, B→A = 1/factor.
Multi-hop not supported; define all needed pairs directly.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


class ConversionError(Exception):
    pass


UNIT_ALIASES: dict = {
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg",
    "gram": "g", "grams": "g", "gm": "g", "gms": "g",
    "litre": "L", "litres": "L", "liter": "L", "liters": "L", "lt": "L",
    "millilitre": "mL", "millilitres": "mL", "milliliter": "mL", "ml": "mL",
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece",
    "packet": "packet", "packets": "packet", "pkt": "packet",
    "carton": "carton", "cartons": "carton", "ctn": "carton",
}

# Hardcoded standard conversions: 1 from_unit = factor to_units
STANDARD_CONVERSIONS: dict = {
    ("kg", "g"): Decimal("1000"),
    ("g", "kg"): Decimal("0.001"),
    ("L", "mL"): Decimal("1000"),
    ("mL", "L"): Decimal("0.001"),
}


def normalize_unit(unit: str) -> str:
    u = unit.strip()
    return UNIT_ALIASES.get(u.lower(), u)


def convert(qty: Decimal, from_unit: str, to_unit: str, item_id: Optional[int] = None) -> Decimal:
    """
    Convert qty from from_unit to to_unit.
    Raises ConversionError if no path found.
    """
    from_unit = normalize_unit(from_unit)
    to_unit = normalize_unit(to_unit)
    if from_unit == to_unit:
        return qty

    factor = _db_factor(from_unit, to_unit, item_id)
    if factor is not None:
        return (qty * factor).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    key = (from_unit, to_unit)
    if key in STANDARD_CONVERSIONS:
        return (qty * STANDARD_CONVERSIONS[key]).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    rev = (to_unit, from_unit)
    if rev in STANDARD_CONVERSIONS:
        return (qty / STANDARD_CONVERSIONS[rev]).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    raise ConversionError(
        f"No conversion: '{from_unit}' → '{to_unit}'"
        + (f" (item_id={item_id})" if item_id else "")
    )


def _db_factor(from_unit: str, to_unit: str, item_id: Optional[int]) -> Optional[Decimal]:
    try:
        from apps.inventory.models import UnitConversion
    except Exception:
        return None
    for item_filter in ([item_id] if item_id else []) + [None]:
        try:
            uc = UnitConversion.objects.get(from_unit=from_unit, to_unit=to_unit, item_id=item_filter)
            return uc.factor
        except Exception:
            pass
        try:
            uc = UnitConversion.objects.get(from_unit=to_unit, to_unit=from_unit, item_id=item_filter)
            return Decimal(1) / uc.factor
        except Exception:
            pass
    return None


def to_base_unit(qty: Decimal, unit: str, item) -> tuple:
    """Convert qty in given unit to item's base_unit. Returns (qty_in_base, base_unit)."""
    unit = normalize_unit(unit)
    base = normalize_unit(item.base_unit)
    if unit == base:
        return qty, base
    return convert(qty, unit, base, item_id=item.id), base
