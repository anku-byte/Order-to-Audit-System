"""
Mandatory benchmark test: Section 5 scenario end-to-end through the service layer.

This test runs the entire benchmark scenario and asserts EVERY result from the
Section 5 "Results we will check" table.

Expected results:
  Flour closing balance:         120 kg  (100 + 60 − 40)
  Oil closing balance:           19.5 L  (30 + 0 − 10.5)
  Pouches closing balance:       306     (500 − 194 = 306; 188 good + 6 damaged)
  FG after run:                  238 packets (50 + 188)
  FG after Retailer A dispatch:  88 packets
  Yield variance:                −6% (188 vs 200 expected), flagged
  Oil variance:                  +5% (10.5 vs 10 BOM), flagged
  Retailer A invoice:            ₹7500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7875
  Retailer A outstanding:        ₹3875 (₹7875 − ₹4000 payment)
  Distributor B shortage:        32 packets (88 available, order 120 → short 32)
  Cost per packet:               computed and positive (exact value documented)

Assumptions documented:
  - Pouch count: 188 good packets need 188 pouches + 6 damaged = 194 total pouch consumption.
    Closing = 500 − 194 = 306. ✓
  - Oil planned = 10 L (BOM), actual = 10.5 L. Variance = (10.5−10)/10 = +5%. ✓
  - Yield planned = 200, actual = 188. Variance = (188−200)/200 = −6%. ✓
  - Flour WAC after purchase: (100×4200 + 60×4500)/160 = 4312.5 → 4313p
  - Cost per packet uses WAC for materials; calculated below.
"""
import pytest
from decimal import Decimal


@pytest.fixture(scope="module")
def django_db_setup():
    pass


@pytest.mark.django_db(transaction=True)
def test_section5_benchmark():
    from apps.core.models import User
    from apps.inventory.models import Item, UnitConversion, StockMovement
    from apps.production.models import BOM, BOMLine, ProductionRun, ProductionRunLine, ProductionRunOverhead
    from apps.sales.models import Customer, Order, OrderLine, Invoice, Payment, PaymentAllocation
    from apps.purchasing.models import Supplier, Purchase, PurchaseLine
    from services.stock import get_balance, get_weighted_average_cost, create_movement, InsufficientStockError
    from services.gst import compute_invoice_gst
    from services.production import complete_production_run
    from services.sales import approve_order
    from django.conf import settings

    # ── Setup: users ──────────────────────────────────────────────────────────
    admin, _ = User.objects.get_or_create(username="bm_admin", defaults={"role": "admin"})
    admin.set_password("x"); admin.save()
    salesman_a, _ = User.objects.get_or_create(username="bm_sa", defaults={"role": "salesman"})
    salesman_b, _ = User.objects.get_or_create(username="bm_sb", defaults={"role": "salesman"})

    # ── Setup: items ──────────────────────────────────────────────────────────
    flour, _ = Item.objects.get_or_create(name="BM Flour",
        defaults={"category":"raw","base_unit":"kg","gst_rate":Decimal("0")})
    oil, _ = Item.objects.get_or_create(name="BM Oil",
        defaults={"category":"raw","base_unit":"L","gst_rate":Decimal("0")})
    spice, _ = Item.objects.get_or_create(name="BM Spice",
        defaults={"category":"raw","base_unit":"kg","gst_rate":Decimal("0")})
    pouch, _ = Item.objects.get_or_create(name="BM Pouch",
        defaults={"category":"pkg","base_unit":"piece","gst_rate":Decimal("0")})
    carton, _ = Item.objects.get_or_create(name="BM Carton",
        defaults={"category":"pkg","base_unit":"piece","gst_rate":Decimal("0")})
    murukku, _ = Item.objects.get_or_create(name="BM Murukku 200g",
        defaults={"category":"fg","base_unit":"packet","hsn_code":"2106","gst_rate":Decimal("5.00")})

    # ── Opening stock ─────────────────────────────────────────────────────────
    create_movement(flour,   "opening", Decimal("100"), 4200, user=admin, notes="BM")
    create_movement(oil,     "opening", Decimal("30"),  14000, user=admin, notes="BM")
    create_movement(spice,   "opening", Decimal("5"),   20000, user=admin, notes="BM")
    create_movement(pouch,   "opening", Decimal("500"), 250, user=admin, notes="BM")
    create_movement(carton,  "opening", Decimal("30"),  1500, user=admin, notes="BM")
    create_movement(murukku, "opening", Decimal("50"),  3500, user=admin, notes="BM")

    # Verify opening
    assert get_balance(flour.id)   == Decimal("100")
    assert get_balance(oil.id)     == Decimal("30")
    assert get_balance(murukku.id) == Decimal("50")

    # ── Step 1: Purchase 60 kg flour @ ₹45/kg ────────────────────────────────
    supplier, _ = Supplier.objects.get_or_create(name="BM Supplier",
        defaults={"state_code":"TN","is_active":True})
    from datetime import date
    purchase = Purchase.objects.create(
        supplier=supplier, purchase_date=date.today(), status="draft", created_by=admin
    )
    PurchaseLine.objects.create(
        purchase=purchase, item=flour, qty=Decimal("60"), unit="kg",
        unit_price_paise=4500, qty_in_base=Decimal("60"),
        total_paise=int(Decimal("60") * 4500),
    )
    from services.purchasing import post_purchase
    post_purchase(purchase, admin)

    flour_balance_after_purchase = get_balance(flour.id)
    assert flour_balance_after_purchase == Decimal("160"), \
        f"After purchase: flour = {flour_balance_after_purchase}, expected 160"

    # Verify WAC: (100×4200 + 60×4500)/160 = 690000/160 = 4312.5 → 4313
    flour_wac = get_weighted_average_cost(flour.id)
    assert flour_wac == 4313, f"Flour WAC = {flour_wac}, expected 4313"

    # ── Step 2+3: Production run ───────────────────────────────────────────────
    # BOM
    bom, _ = BOM.objects.get_or_create(name="BM Murukku BOM",
        defaults={"product": murukku, "expected_yield": Decimal("200"), "is_active": True})
    for item, qty, unit in [
        (flour, Decimal("40"), "kg"), (oil, Decimal("10"), "L"),
        (spice, Decimal("1.2"), "kg"), (pouch, Decimal("200"), "piece"),
        (carton, Decimal("10"), "piece"),
    ]:
        BOMLine.objects.get_or_create(bom=bom, item=item,
            defaults={"qty_per_batch": qty, "unit": unit})

    run = ProductionRun.objects.create(
        bom=bom, run_date=date.today(), batch_multiplier=Decimal("1"),
        status="draft", created_by=admin,
    )

    # Actual quantities:
    # Flour: 40 kg (on spec), Oil: 10.5 L (+0.5 L), Spice: 1.2 kg (on spec)
    # Pouches: 188 (good) + 6 (damaged) = 194 total consumed
    # Cartons: 9 used (not 10 BOM) — benchmark says "9 cartons used"
    actual_lines = [
        (flour, Decimal("40"),   Decimal("40"),   "kg"),     # oil planned=10, actual=10.5
        (oil,   Decimal("10"),   Decimal("10.5"), "L"),
        (spice, Decimal("1.2"),  Decimal("1.2"),  "kg"),
        (pouch, Decimal("200"),  Decimal("194"),  "piece"),  # 188+6 damaged
        (carton,Decimal("10"),   Decimal("9"),    "piece"),  # 9 cartons used
    ]
    for item, planned, actual, unit in actual_lines:
        ProductionRunLine.objects.create(
            run=run, bom_line=bom.lines.get(item=item),
            planned_qty=planned, actual_qty=actual, unit=unit,
        )

    run.actual_good_output = Decimal("188")
    run.actual_scrap_qty = Decimal("0")
    run.damaged_packaging_qty = Decimal("6")
    run.save()

    # Step 8: Add overheads before completing
    ProductionRunOverhead.objects.create(run=run, overhead_type="labour",
        description="Labour", amount_paise=120000)   # ₹1200
    ProductionRunOverhead.objects.create(run=run, overhead_type="gas",
        description="Gas/Power", amount_paise=60000)  # ₹600

    complete_production_run(run, admin)

    # ── Verify post-run stock balances ────────────────────────────────────────
    flour_final = get_balance(flour.id)
    oil_final = get_balance(oil.id)
    pouch_final = get_balance(pouch.id)
    fg_after_run = get_balance(murukku.id)

    assert flour_final == Decimal("120"), \
        f"Flour closing = {flour_final}, expected 120 kg"
    assert oil_final == Decimal("19.5"), \
        f"Oil closing = {oil_final}, expected 19.5 L"
    assert pouch_final == Decimal("306"), \
        f"Pouches closing = {pouch_final}, expected 306"
    assert fg_after_run == Decimal("238"), \
        f"FG after run = {fg_after_run}, expected 238"

    # ── Verify variance flags ─────────────────────────────────────────────────
    run.refresh_from_db()
    # Yield: planned=200, actual=188 → −6%
    assert run.yield_variance_pct == Decimal("-6.00"), \
        f"Yield variance = {run.yield_variance_pct}, expected -6.00"
    assert run.yield_variance_flagged is True, "Yield variance should be flagged"

    oil_line = run.lines.get(bom_line__item=oil)
    # Oil: planned=10, actual=10.5 → +5%
    assert oil_line.variance_pct == Decimal("5.0000"), \
        f"Oil variance = {oil_line.variance_pct}, expected 5.0000"
    assert oil_line.is_flagged is True, "Oil variance should be flagged"

    # ── Cost per packet ───────────────────────────────────────────────────────
    cpp = run.cost_per_packet_paise
    assert cpp > 0, f"Cost per packet must be positive, got {cpp}"
    # Document the computed value
    print(f"\nCost per packet: ₹{cpp/100:.2f} ({cpp} paise)")
    # Rough sanity: materials + overheads / 188 packets
    # Materials: flour 40kg×4313p=172520 + oil 10.5×14000=147000 + spice 1.2×20000=24000
    #            + pouches 194×250=48500 + cartons 9×1500=13500 → total ≈ 405520
    # Overheads: 120000 + 60000 = 180000
    # Total: 585520 / 188 ≈ 3114p ≈ ₹31.14
    # (Exact WAC-based values may differ slightly for oil/spice with no prior purchase)
    assert 1000 < cpp < 10000, f"Cost per packet sanity check failed: {cpp}p"

    # ── Step 4+5: Retailer A order (150 packets, TN) ─────────────────────────
    retailer_a, _ = Customer.objects.get_or_create(name="BM Retailer A",
        defaults={"customer_type":"retailer","state_code":"TN","is_active":True})

    order_a = Order.objects.create(customer=retailer_a, salesman=salesman_a, status="submitted")
    OrderLine.objects.create(order=order_a, item=murukku, qty=Decimal("150"), unit_price_paise=5000)

    invoice_a = approve_order(order_a, admin)

    fg_after_dispatch_a = get_balance(murukku.id)
    assert fg_after_dispatch_a == Decimal("88"), \
        f"FG after Retailer A dispatch = {fg_after_dispatch_a}, expected 88"

    # Verify invoice amounts
    assert invoice_a.taxable_value_paise == 750000, \
        f"Taxable = {invoice_a.taxable_value_paise}p, expected 750000p (₹7500)"
    assert invoice_a.cgst_paise == 18750, \
        f"CGST = {invoice_a.cgst_paise}p, expected 18750p (₹187.50)"
    assert invoice_a.sgst_paise == 18750, \
        f"SGST = {invoice_a.sgst_paise}p, expected 18750p (₹187.50)"
    assert invoice_a.igst_paise == 0
    assert invoice_a.total_paise == 787500, \
        f"Total = {invoice_a.total_paise}p, expected 787500p (₹7875)"
    assert invoice_a.supply_type == "intrastate"

    # ── Step 7: Payment ₹4000 from Retailer A ────────────────────────────────
    payment_a = Payment.objects.create(
        customer=retailer_a, payment_date=date.today(),
        amount_paise=400000, mode="cash", created_by=admin,
    )
    PaymentAllocation.objects.create(
        payment=payment_a, invoice=invoice_a, allocated_paise=400000,
    )

    outstanding_a = invoice_a.outstanding_paise
    assert outstanding_a == 387500, \
        f"Retailer A outstanding = {outstanding_a}p, expected 387500p (₹3875)"

    # ── Step 6: Distributor B order (120 packets, KA) ─ shortage check ───────
    distributor_b, _ = Customer.objects.get_or_create(name="BM Distributor B",
        defaults={"customer_type":"distributor","state_code":"KA",
                  "gstin":"29AABCD1234E1Z5","is_active":True})

    # Stock = 88 packets, order = 120 → shortage = 32
    fg_stock = get_balance(murukku.id)
    order_b_qty = Decimal("120")
    shortage = max(Decimal("0"), order_b_qty - fg_stock)
    assert shortage == Decimal("32"), \
        f"Shortage = {shortage}, expected 32 (stock={fg_stock}, ordered={order_b_qty})"

    # Verify IGST would apply for Distributor B (interstate)
    lines_b = [{"item": murukku, "qty": order_b_qty, "unit_price_paise": 5000}]
    gst_b = compute_invoice_gst(distributor_b, lines_b)
    assert gst_b.supply_type == "interstate"
    assert gst_b.total_igst_paise == 30000, \
        f"IGST for Distributor B = {gst_b.total_igst_paise}p, expected 30000p (₹300)"
    assert gst_b.total_taxable_paise == 600000  # ₹6000

    # Trying to dispatch would raise InsufficientStockError (88 < 120)
    with pytest.raises(InsufficientStockError):
        create_movement(murukku, "sale_dispatch", -order_b_qty, unit_cost_paise=cpp,
                        user=admin)

    print("\n✅ All Section 5 benchmark assertions passed!")
    print(f"  Flour:   {get_balance(flour.id)} kg (expected 120)")
    print(f"  Oil:     {get_balance(oil.id)} L (expected 19.5)")
    print(f"  Pouches: {get_balance(pouch.id)} (expected 306)")
    print(f"  FG:      {fg_after_dispatch_a} packets (expected 88)")
    print(f"  Invoice: ₹{invoice_a.taxable_value_paise/100:.2f} + "
          f"CGST ₹{invoice_a.cgst_paise/100:.2f} + "
          f"SGST ₹{invoice_a.sgst_paise/100:.2f} = ₹{invoice_a.total_paise/100:.2f}")
    print(f"  Outstanding: ₹{outstanding_a/100:.2f} (expected ₹3875)")
    print(f"  Shortage: {shortage} packets (expected 32)")
    print(f"  Cost/packet: ₹{cpp/100:.2f}")
