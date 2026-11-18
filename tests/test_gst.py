"""
Unit tests for services/gst.py — GST computation.

Benchmark checks:
  Retailer A (TN, intrastate): 150 × ₹50 = ₹7500 taxable
    5% GST = ₹375 → CGST ₹187.50, SGST ₹187.50
    In paise: taxable=750000, cgst=18750, sgst=18750, total=787500 (₹7875)

  Distributor B (KA, interstate): 120 × ₹50 = ₹6000 taxable
    5% GST = ₹300 → IGST ₹300
    In paise: taxable=600000, igst=30000, total=630000 (₹6300)
"""
import pytest
from decimal import Decimal
from services.gst import compute_invoice_gst, InvoiceGSTResult


@pytest.mark.django_db
def test_intrastate_retailer_a(fg_item, tn_customer):
    """150 packets × ₹50 → ₹7500 taxable, CGST ₹187.50, SGST ₹187.50, Total ₹7875."""
    lines = [{"item": fg_item, "qty": Decimal("150"), "unit_price_paise": 5000}]
    result = compute_invoice_gst(tn_customer, lines)

    assert result.supply_type == "intrastate"
    assert result.total_taxable_paise == 750000       # ₹7500
    assert result.total_cgst_paise == 18750           # ₹187.50
    assert result.total_sgst_paise == 18750           # ₹187.50
    assert result.total_igst_paise == 0
    assert result.grand_total_paise == 787500         # ₹7875


@pytest.mark.django_db
def test_interstate_distributor_b(fg_item, ka_customer):
    """120 packets × ₹50 → ₹6000 taxable, IGST ₹300, Total ₹6300."""
    lines = [{"item": fg_item, "qty": Decimal("120"), "unit_price_paise": 5000}]
    result = compute_invoice_gst(ka_customer, lines)

    assert result.supply_type == "interstate"
    assert result.total_taxable_paise == 600000       # ₹6000
    assert result.total_cgst_paise == 0
    assert result.total_sgst_paise == 0
    assert result.total_igst_paise == 30000           # ₹300
    assert result.grand_total_paise == 630000         # ₹6300


@pytest.mark.django_db
def test_gst_odd_paise_to_cgst(db, fg_item, tn_customer):
    """
    When GST amount is odd paise, CGST gets the extra paise.
    1 packet × ₹1 (100p) → taxable=100p, GST=5p (odd? no, 5 is odd).
    5p → cgst=3, sgst=2? No: cgst = 5 - 5//2 = 5-2=3, sgst=2.
    Wait: gst=5; sgst=5//2=2; cgst=5-2=3.
    """
    from apps.inventory.models import Item
    test_item, _ = Item.objects.get_or_create(
        name="Odd Paise Test Item",
        defaults={"category": "fg", "base_unit": "packet", "hsn_code": "2106",
                  "gst_rate": Decimal("5.00")},
    )
    # 1 packet × ₹1 = ₹1 taxable = 100p; GST 5% = 5p (odd)
    lines = [{"item": test_item, "qty": Decimal("1"), "unit_price_paise": 100}]
    result = compute_invoice_gst(tn_customer, lines)
    gst_total = result.total_cgst_paise + result.total_sgst_paise
    assert gst_total == 5                             # 5p total GST
    assert result.total_cgst_paise >= result.total_sgst_paise  # CGST >= SGST (odd paise → CGST)


@pytest.mark.django_db
def test_zero_gst_rate(db, tn_customer):
    """Item with 0% GST → no tax on any supply type."""
    from apps.inventory.models import Item
    zero_item, _ = Item.objects.get_or_create(
        name="Zero GST Item",
        defaults={"category": "fg", "base_unit": "packet",
                  "gst_rate": Decimal("0.00")},
    )
    lines = [{"item": zero_item, "qty": Decimal("10"), "unit_price_paise": 1000}]
    result = compute_invoice_gst(tn_customer, lines)
    assert result.total_cgst_paise == 0
    assert result.total_sgst_paise == 0
    assert result.grand_total_paise == result.total_taxable_paise
