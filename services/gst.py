"""
GST computation service.

Rules:
- Intrastate (customer.state_code == FACTORY_STATE_CODE='TN'): CGST + SGST (half each).
- Interstate: IGST = full GST.
- Computed PER LINE (not on total) to avoid rounding drift across lines.
- Rounding: each line's GST rounded half-up to nearest paise.
- CGST/SGST split: total_gst // 2 each; odd paise goes to CGST (documented choice).
  Rationale: when total GST for a line is odd paise (e.g. 375p → 187+188),
  CGST gets the higher paise. This is consistent and auditable.
- This matches GSTR-1 B2C reporting where line-level breakup is required.
"""
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import List
from django.conf import settings


@dataclass
class GSTLineResult:
    item_name: str
    hsn_code: str
    qty: Decimal
    unit_price_paise: int
    gst_rate: Decimal
    taxable_value_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int

    @property
    def total_paise(self):
        return self.taxable_value_paise + self.cgst_paise + self.sgst_paise + self.igst_paise


@dataclass
class InvoiceGSTResult:
    supply_type: str
    lines: List[GSTLineResult] = field(default_factory=list)

    @property
    def total_taxable_paise(self): return sum(l.taxable_value_paise for l in self.lines)
    @property
    def total_cgst_paise(self): return sum(l.cgst_paise for l in self.lines)
    @property
    def total_sgst_paise(self): return sum(l.sgst_paise for l in self.lines)
    @property
    def total_igst_paise(self): return sum(l.igst_paise for l in self.lines)
    @property
    def grand_total_paise(self):
        return self.total_taxable_paise + self.total_cgst_paise + self.total_sgst_paise + self.total_igst_paise


def compute_invoice_gst(customer, lines: list) -> InvoiceGSTResult:
    """
    Compute GST for an invoice.
    lines: list of dicts with keys: item (Item), qty (Decimal), unit_price_paise (int)

    Benchmark check:
      Retailer A (TN, intrastate): 150 packets × ₹50 = ₹7500 taxable
        GST 5% = 375p per line... wait, paise: 150 × 5000p = 750000p taxable
        GST = 750000 × 5/100 = 37500p total → CGST=18750p, SGST=18750p
        That's ₹187.50 each. ✓
      Distributor B (KA, interstate): 120 × 5000p = 600000p taxable
        GST = 30000p → IGST = ₹300. ✓
    """
    factory_state = getattr(settings, "FACTORY_STATE_CODE", "TN")
    is_intrastate = customer.state_code == factory_state
    result = InvoiceGSTResult(supply_type="intrastate" if is_intrastate else "interstate")

    for line_data in lines:
        item = line_data["item"]
        qty = Decimal(str(line_data["qty"]))
        unit_price_paise = int(line_data["unit_price_paise"])
        gst_rate = item.gst_rate  # Decimal e.g. Decimal('5.00')

        # taxable value: qty × unit_price (integer paise, no float)
        taxable_paise = int(qty * unit_price_paise)

        # GST amount per line, rounded half-up to nearest paise
        gst_decimal = Decimal(taxable_paise) * gst_rate / Decimal("100")
        gst_paise = int(gst_decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        if is_intrastate:
            # Split: odd paise → CGST
            sgst_paise = gst_paise // 2
            cgst_paise = gst_paise - sgst_paise  # handles odd: e.g. 375 → cgst=188, sgst=187
            igst_paise = 0
        else:
            cgst_paise = 0
            sgst_paise = 0
            igst_paise = gst_paise

        result.lines.append(GSTLineResult(
            item_name=item.name,
            hsn_code=item.hsn_code or "",
            qty=qty,
            unit_price_paise=unit_price_paise,
            gst_rate=gst_rate,
            taxable_value_paise=taxable_paise,
            cgst_paise=cgst_paise,
            sgst_paise=sgst_paise,
            igst_paise=igst_paise,
        ))

    return result
