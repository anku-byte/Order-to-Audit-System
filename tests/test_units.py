"""
Unit tests for services/units.py — unit conversion service.
"""
import pytest
from decimal import Decimal
from services.units import convert, to_base_unit, ConversionError, normalize_unit


def test_normalize_aliases():
    assert normalize_unit("kilogram") == "kg"
    assert normalize_unit("litre") == "L"
    assert normalize_unit("ml") == "mL"
    assert normalize_unit("pieces") == "piece"
    assert normalize_unit("packets") == "packet"


def test_kg_to_g():
    result = convert(Decimal("1.5"), "kg", "g")
    assert result == Decimal("1500.000000")


def test_g_to_kg():
    result = convert(Decimal("500"), "g", "kg")
    assert result == Decimal("0.500000")


def test_L_to_mL():
    result = convert(Decimal("10.5"), "L", "mL")
    assert result == Decimal("10500.000000")


def test_mL_to_L():
    result = convert(Decimal("250"), "mL", "L")
    assert result == Decimal("0.250000")


def test_same_unit():
    result = convert(Decimal("5"), "kg", "kg")
    assert result == Decimal("5")


def test_unknown_unit_raises():
    with pytest.raises(ConversionError):
        convert(Decimal("1"), "furlong", "kg")


def test_alias_normalize_converts():
    # 'kilogram' should normalize to 'kg' and convert to 'g'
    result = convert(Decimal("2"), "kilogram", "gram")
    assert result == Decimal("2000.000000")


@pytest.mark.django_db
def test_to_base_unit_same(flour_item):
    qty, unit = to_base_unit(Decimal("5"), "kg", flour_item)
    assert qty == Decimal("5")
    assert unit == "kg"


@pytest.mark.django_db
def test_to_base_unit_converts(flour_item):
    # flour base_unit = kg; convert from g
    qty, unit = to_base_unit(Decimal("500"), "g", flour_item)
    assert unit == "kg"
    assert qty == Decimal("0.500000")


@pytest.mark.django_db
def test_carton_to_packet_via_db(db):
    """Item-specific conversion: 1 carton = 20 packets for Carton item."""
    from apps.inventory.models import Item, UnitConversion
    carton_item, _ = Item.objects.get_or_create(
        name="Test Carton",
        defaults={"category": "pkg", "base_unit": "piece", "gst_rate": Decimal("0")},
    )
    UnitConversion.objects.get_or_create(
        from_unit="carton", to_unit="piece", item=carton_item,
        defaults={"factor": Decimal("20")},
    )
    result = convert(Decimal("5"), "carton", "piece", item_id=carton_item.id)
    assert result == Decimal("100.000000")
