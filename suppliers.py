"""
suppliers.py
-------------
إدارة الموردين وعمليات الشراء منهم. كل عملية شراء:
- تزيد كمية المخزون تلقائيًا للمنتجات المشتراة
- تُحدّث تكلفة المنتج (cost_price) بآخر سعر شراء
- تُسجَّل في جدول حركة المخزون (StockMovement) للتتبع والتدقيق
"""

from datetime import datetime
from database import get_session, Supplier, Purchase, PurchaseItem, Product, StockMovement


def create_supplier(name: str, phone: str = None, address: str = None, notes: str = None) -> int:
    session = get_session()
    supplier = Supplier(name=name, phone=phone, address=address, notes=notes)
    session.add(supplier)
    session.commit()
    supplier_id = supplier.id
    session.close()
    return supplier_id


def list_suppliers():
    session = get_session()
    suppliers = session.query(Supplier).order_by(Supplier.name).all()
    session.close()
    return suppliers


def create_purchase(supplier_id: int, items: list) -> int:
    """
    items: قائمة قواميس [{"product_id": 1, "quantity": 10, "unit_cost": 25.0}, ...]
    عند التنفيذ: يزيد المخزون، يحدّث تكلفة المنتج، ويسجّل حركة المخزون.
    """
    session = get_session()
    purchase_number = f"P-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    purchase = Purchase(supplier_id=supplier_id, purchase_number=purchase_number)
    session.add(purchase)
    session.flush()

    total_cost = 0.0
    for item in items:
        product = session.query(Product).get(item["product_id"])
        if not product:
            continue
        qty = item["quantity"]
        unit_cost = item["unit_cost"]
        total_cost += qty * unit_cost

        session.add(PurchaseItem(
            purchase_id=purchase.id,
            product_id=product.id,
            quantity=qty,
            unit_cost=unit_cost,
        ))

        # تحديث المخزون والتكلفة تلقائيًا
        product.stock_qty = (product.stock_qty or 0) + qty
        product.cost_price = unit_cost

        session.add(StockMovement(
            product_id=product.id,
            change_qty=qty,
            reason="شراء",
            reference=purchase_number,
        ))

    purchase.total_cost = total_cost
    session.commit()
    purchase_id = purchase.id
    session.close()
    return purchase_id


def list_purchases():
    session = get_session()
    purchases = session.query(Purchase).order_by(Purchase.created_at.desc()).all()
    session.close()
    return purchases
