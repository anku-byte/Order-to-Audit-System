"""
Unit tests for services/stock.py — ledger balance and WAC costing.
"""
import pytest
from decimal import Decimal
from services.stock import (
    get_balance, get_weighted_average_cost, create_movement, InsufficientStockError
)


@pytest.mark.django_db
def test_opening_balance(flour_item, admin_user):
    """Opening movement of 100 kg → balance = 100."""
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    assert get_balance(flour_item.id) == Decimal("100")


@pytest.mark.django_db
def test_issue_reduces_balance(flour_item, admin_user):
    """100 kg opening, issue 40 kg → balance = 60."""
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    create_movement(flour_item, "production_issue", Decimal("-40"), 4200, user=admin_user)
    assert get_balance(flour_item.id) == Decimal("60")


@pytest.mark.django_db
def test_balance_never_negative(flour_item, admin_user):
    """Issuing more than available raises InsufficientStockError."""
    create_movement(flour_item, "opening", Decimal("30"), 4200, user=admin_user)
    with pytest.raises(InsufficientStockError):
        create_movement(flour_item, "production_issue", Decimal("-50"), 4200, user=admin_user)


@pytest.mark.django_db
def test_zero_balance_raises(flour_item, admin_user):
    """No stock at all → any outgoing movement raises InsufficientStockError."""
    with pytest.raises(InsufficientStockError):
        create_movement(flour_item, "sale_dispatch", Decimal("-1"), 4200, user=admin_user)


@pytest.mark.django_db
def test_weighted_average_cost_simple(flour_item, admin_user):
    """
    Open 100 kg @ 4200p, receive 60 kg @ 4500p.
    WAC = (100×4200 + 60×4500) / (100+60) = (420000 + 270000) / 160 = 690000/160 = 4312.5 → 4313p
    """
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    create_movement(flour_item, "purchase", Decimal("60"), 4500, user=admin_user)
    wac = get_weighted_average_cost(flour_item.id)
    # 690000 / 160 = 4312.5 → rounds to 4313
    assert wac == 4313


@pytest.mark.django_db
def test_weighted_average_cost_single(flour_item, admin_user):
    """Single opening movement: WAC = opening unit_cost."""
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    assert get_weighted_average_cost(flour_item.id) == 4200


@pytest.mark.django_db
def test_ledger_multiple_movements(flour_item, admin_user):
    """Multiple movements; balance reconciles correctly."""
    from services.stock import get_ledger
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    create_movement(flour_item, "purchase", Decimal("60"), 4500, user=admin_user)
    create_movement(flour_item, "production_issue", Decimal("-40"), 4200, user=admin_user)

    final = get_balance(flour_item.id)
    assert final == Decimal("120")  # 100 + 60 - 40

    # Ledger reconciliation
    rows = list(get_ledger(flour_item.id))
    assert len(rows) == 3
    running = sum(r.qty_delta for r in rows)
    assert running == Decimal("120")


@pytest.mark.django_db
def test_movement_value_is_signed(flour_item, admin_user):
    """value field on issue movement is negative (outgoing)."""
    create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    m = create_movement(flour_item, "production_issue", Decimal("-40"), 4200, user=admin_user, notes="test")
    assert m.value < 0


@pytest.mark.django_db
def test_movement_value_signed_full(flour_item, admin_user):
    """value field: inward positive, outward negative."""
    m_in = create_movement(flour_item, "opening", Decimal("100"), 4200, user=admin_user)
    assert m_in.value == int(Decimal("100") * 4200)   # +420000

    m_out = create_movement(flour_item, "production_issue", Decimal("-40"), 4200, user=admin_user)
    assert m_out.value == int(Decimal("-40") * 4200)  # -168000
