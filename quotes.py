"""
quotes.py
----------
إنشاء عروض أسعار (Quotes) وربطها بعميل ومنتجات، مع تصدير PDF أنيق وتصدير Excel.
"""

import os
from datetime import datetime
from fpdf import FPDF
import pandas as pd
from database import get_session, Client, Product, Quote, QuoteItem

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)


# ---------------------------------------------------------------
# إنشاء عرض سعر جديد في قاعدة البيانات
# ---------------------------------------------------------------
def create_quote(client_id: int, items: list) -> int:
    """
    items: قائمة قواميس [{"product_id": 1, "quantity": 3}, ...]
    يُرجع quote_id الخاص بالعرض الذي تم إنشاؤه.
    """
    session = get_session()
    quote_number = f"Q-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    quote = Quote(client_id=client_id, quote_number=quote_number, status="مسودة")
    session.add(quote)
    session.flush()  # للحصول على quote.id قبل الـ commit

    total = 0.0
    for item in items:
        product = session.query(Product).get(item["product_id"])
        if not product:
            continue
        qty = item["quantity"]
        line_total = product.price * qty
        total += line_total

        session.add(QuoteItem(
            quote_id=quote.id,
            product_id=product.id,
            quantity=qty,
            unit_price=product.price,
        ))

    quote.total_amount = total
    session.commit()
    quote_id = quote.id
    session.close()
    return quote_id


# ---------------------------------------------------------------
# تصدير عرض سعر واحد إلى PDF
# ---------------------------------------------------------------
def export_quote_pdf(quote_id: int, company_name: str = "شركتي") -> str:
    session = get_session()
    quote = session.query(Quote).get(quote_id)
    if not quote:
        session.close()
        raise ValueError("عرض السعر غير موجود")

    client = quote.client

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, company_name, ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"Devis / Quote: {quote.quote_number}", ln=True, align="C")
    pdf.cell(0, 8, f"Date: {quote.created_at.strftime('%Y-%m-%d')}", ln=True, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, f"Client: {client.name}", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Adresse: {client.address or '-'}", ln=True)
    pdf.cell(0, 7, f"Telephone: {client.phone or '-'}", ln=True)
    pdf.ln(6)

    # جدول المنتجات
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(80, 8, "Produit", border=1)
    pdf.cell(30, 8, "Qte", border=1, align="C")
    pdf.cell(35, 8, "Prix unitaire", border=1, align="C")
    pdf.cell(35, 8, "Total", border=1, align="C", ln=True)

    pdf.set_font("Helvetica", "", 11)
    for item in quote.items:
        line_total = item.unit_price * item.quantity
        pdf.cell(80, 8, item.product.name[:35], border=1)
        pdf.cell(30, 8, str(item.quantity), border=1, align="C")
        pdf.cell(35, 8, f"{item.unit_price:.2f}", border=1, align="C")
        pdf.cell(35, 8, f"{line_total:.2f}", border=1, align="C", ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, f"Total General: {quote.total_amount:.2f}", ln=True, align="R")

    output_path = os.path.join(EXPORTS_DIR, f"{quote.quote_number}.pdf")
    pdf.output(output_path)
    session.close()
    return output_path


# ---------------------------------------------------------------
# تصدير قائمة عملاء مختارين إلى Excel
# ---------------------------------------------------------------
def export_clients_excel(client_ids: list) -> str:
    session = get_session()
    clients = session.query(Client).filter(Client.id.in_(client_ids)).all()

    rows = [{
        "الاسم": c.name,
        "الهاتف": c.phone,
        "العنوان": c.address,
        "الفئة": c.category,
        "الحالة": c.status,
        "المصدر": c.source,
        "التقييم": c.rating,
        "الموقع الإلكتروني": c.website,
        "ملاحظات": c.notes,
    } for c in clients]

    df = pd.DataFrame(rows)
    output_path = os.path.join(EXPORTS_DIR, f"clients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    df.to_excel(output_path, index=False)
    session.close()
    return output_path
