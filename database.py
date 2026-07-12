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
def _run_lightweight_migrations():
    """
    يفحص الجداول الموجودة مسبقًا (من إصدار سابق للتطبيق) ويضيف أي أعمدة جديدة
    ناقصة فيها، دون المساس بالبيانات الحالية. آمن للتشغيل في كل مرة (idempotent).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # كل عمود جديد أُضيف لاحقًا لجدول كان موجودًا من قبل: (الجدول، العمود، تعريف SQL)
    required_columns = [
        ("products", "cost_price", "FLOAT DEFAULT 0.0"),
        ("products", "low_stock_threshold", "INTEGER DEFAULT 5"),
        ("quotes", "is_invoice", "BOOLEAN DEFAULT FALSE"),
    ]

    with engine.connect() as conn:
        for table_name, column_name, column_def in required_columns:
            if table_name not in existing_tables:
                continue  # الجدول نفسه غير موجود بعد، create_all سيُنشئه بكامل أعمدته
            existing_columns = [c["name"] for c in inspector.get_columns(table_name)]
            if column_name in existing_columns:
                continue  # العمود موجود بالفعل، لا شيء لفعله
            try:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                conn.commit()
            except Exception:
                conn.rollback()  # تجاهل بأمان إن فشل (مثلًا صلاحيات، أو عمود أُضيف بالتزامن)


def init_db():
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    Base.metadata.create_all(engine)   # يُنشئ أي جداول جديدة كليًا (مثل suppliers, payments...)
    _run_lightweight_migrations()      # يُضيف أعمدة جديدة ناقصة للجداول القديمة   # ينشئ الجداول الجديدة فقط (الموردين، المشتريات، الدفعات...)
    _run_migrations()                   # يضيف الأعمدة الجديدة للجداول القديمة الموجودة مسبقًا


def _run_migrations():
    """
    ترحيل آمن وبسيط: يفحص الجداول الموجودة مسبقًا (قبل هذا التحديث) ويضيف
    أي عمود جديد ناقص فيها، بدون حذف أو المساس بأي بيانات موجودة.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # كل جدول قديم قد يحتاج أعمدة جديدة + تعريفها المتوافق مع SQLite و PostgreSQL معًا
    migrations = {
        "products": [
            ("cost_price", "FLOAT DEFAULT 0"),
            ("low_stock_threshold", "INTEGER DEFAULT 5"),
        ],
        "quotes": [
            ("is_invoice", "BOOLEAN DEFAULT FALSE"),
        ],
    }

    with engine.begin() as conn:
        for table, columns in migrations.items():
            if table not in existing_tables:
                continue  # جدول جديد بالكامل، create_all تكفّل به بالفعل
            existing_columns = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_def in columns:
                if col_name not in existing_columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def get_session():
    return SessionLocal()


if __name__ == "__main__":
    init_db()
    print(f"✅ تم إنشاء قاعدة البيانات بنجاح في: {DB_PATH}")
