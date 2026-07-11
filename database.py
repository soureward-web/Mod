"""
database.py
------------
طبقة قاعدة البيانات (SQLite) - تحتوي على جداول:
- clients        : العملاء المحتملون (من Maps / CSV / يدوي)
- products        : المنتجات المادية (مع المخزون والسعر)
- quotes          : عروض الأسعار
- quote_items      : تفاصيل كل عرض سعر (منتج + كمية)

مصممة بحيث يسهل ترحيلها لاحقًا إلى PostgreSQL (نفس بنية SQLAlchemy تعمل على الاثنين).
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime,
    ForeignKey, Text, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "leadgen.db")


def _get_database_url() -> str:
    # 1) متغير بيئة (يعمل محليًا وفي أي استضافة عامة)
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # 2) Streamlit Cloud يقرأ من .streamlit/secrets.toml تلقائيًا
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass

    # 3) الافتراضي: SQLite محلي (وضع التطوير على جهازك)
    return f"sqlite:///{DB_PATH}"


DATABASE_URL = _get_database_url()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True,   # يتحقق من صلاحية الاتصال قبل كل استخدام، ويعيد الاتصال تلقائيًا إن انقطع
    pool_recycle=300,     # يجدد الاتصال كل 5 دقائق لتفادي إغلاق Supabase له من جهته
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------
# جدول العملاء المحتملين
# ---------------------------------------------------------------
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50))
    address = Column(String(300))
    category = Column(String(100))          # نوع النشاط (مطعم، محل، ورشة...)
    source = Column(String(50), default="google_maps")   # google_maps / csv / linkedin / manual
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    website = Column(String(300), nullable=True)
    status = Column(String(30), default="جديد")   # جديد / تم التواصل / مهتم / متفاوض / مشترٍ / غير مهتم
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    quotes = relationship("Quote", back_populates="client")


# ---------------------------------------------------------------
# جدول المنتجات (مادية - فيها مخزون)
# ---------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=True)
    price = Column(Float, nullable=False, default=0.0)          # سعر البيع
    cost_price = Column(Float, nullable=False, default=0.0)      # آخر تكلفة شراء (لحساب الهامش)
    stock_qty = Column(Integer, default=0)
    low_stock_threshold = Column(Integer, default=5)             # تنبيه عند الوصول لهذه الكمية أو أقل
    unit = Column(String(30), default="قطعة")
    description = Column(Text, nullable=True)

    quote_items = relationship("QuoteItem", back_populates="product")
    purchase_items = relationship("PurchaseItem", back_populates="product")
    stock_movements = relationship("StockMovement", back_populates="product")


# ---------------------------------------------------------------
# جدول عروض الأسعار
# ---------------------------------------------------------------
class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    quote_number = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    total_amount = Column(Float, default=0.0)
    status = Column(String(30), default="مسودة")   # مسودة / مرسل / مقبول / مرفوض
    is_invoice = Column(Boolean, default=False)     # False = عرض سعر فقط، True = فاتورة بيع فعلية

    client = relationship("Client", back_populates="quotes")
    items = relationship("QuoteItem", back_populates="quote", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="quote", cascade="all, delete-orphan")


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, default=0.0)   # نسخة من السعر وقت العرض (حتى لو تغير لاحقًا)

    quote = relationship("Quote", back_populates="items")
    product = relationship("Product", back_populates="quote_items")


# ---------------------------------------------------------------
# جدول الدفعات (مرتبطة بفاتورة/عرض سعر - تتبع من دفع كم ومتى)
# ---------------------------------------------------------------
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"))
    amount = Column(Float, nullable=False, default=0.0)
    payment_date = Column(DateTime, default=datetime.utcnow)
    method = Column(String(30), default="نقدًا")  # نقدًا / تحويل بنكي / شيك / أخرى
    notes = Column(Text, nullable=True)

    quote = relationship("Quote", back_populates="payments")


# ---------------------------------------------------------------
# جدول الموردين
# ---------------------------------------------------------------
class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    address = Column(String(300), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    purchases = relationship("Purchase", back_populates="supplier")


# ---------------------------------------------------------------
# جدول عمليات الشراء (فواتير الشراء من الموردين)
# ---------------------------------------------------------------
class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    purchase_number = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    total_cost = Column(Float, default=0.0)

    supplier = relationship("Supplier", back_populates="purchases")
    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    unit_cost = Column(Float, default=0.0)

    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product", back_populates="purchase_items")


# ---------------------------------------------------------------
# جدول حركة المخزون (سجل تلقائي لكل دخول/خروج بضاعة)
# ---------------------------------------------------------------
class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    change_qty = Column(Integer, nullable=False)   # موجب = دخول (شراء)، سالب = خروج (بيع)
    reason = Column(String(50))                    # "شراء" / "بيع" / "تعديل يدوي"
    reference = Column(String(50), nullable=True)  # رقم الفاتورة/عرض السعر أو الشراء المرتبط
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="stock_movements")


# ---------------------------------------------------------------
# دالة تهيئة قاعدة البيانات (تُستدعى مرة واحدة عند أول تشغيل)
# ---------------------------------------------------------------
def init_db():
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()


if __name__ == "__main__":
    init_db()
    print(f"✅ تم إنشاء قاعدة البيانات بنجاح في: {DB_PATH}")
