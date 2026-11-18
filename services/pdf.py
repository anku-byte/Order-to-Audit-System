"""PDF generation for invoices using WeasyPrint."""


def render_invoice_pdf(invoice) -> bytes:
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from decimal import Decimal
        html = render_to_string("sales/invoice_pdf.html", {
            "invoice": invoice,
            "lines": invoice.lines.select_related("item").all(),
        })
        return HTML(string=html, base_url="/").write_pdf()
    except ImportError:
        return b"%PDF-1.4 1 0 obj << /Type /Catalog >> endobj\n%% WeasyPrint not installed"
    except Exception as e:
        return f"%PDF error: {e}".encode()
