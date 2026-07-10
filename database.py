"""
database.py
"""

from sqlalchemy import (
create_engine, Column, Integer, String, Float, DateTime,
ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(file), "data", "leadgen.db")

def _get_database_url() -> str:
env_url = os.getenv("DATABASE_URL")
if env_url:
return env_url
try:
import streamlit as st
if "DATABASE_URL" in st.secrets:
return st.secrets["DATABASE_URL"]
except Exception:
pass
return f"sqlite:///{DB_PATH}"

DATABASE_URL = _get_database_url()

if DATABASE_URL.startswith("postgres://"):
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Client(Base):
tablename = "clients"

id = Column(Integer, primary_key=True)
name = Column(String(200), nullable=False)
phone = Column(String(50))
address = Column(String(300))
category = Column(String(100))
source = Column(String(50), default="google_maps")
latitude = Column(Float, nullable=True)
longitude = Column(Float, nullable=True)
rating = Column(Float, nullable=True)
website = Column(String(300), nullable=True)
status = Column(String(30), default="جديد")
notes = Column(Text, nullable=True)
created_at = Column(DateTime, default=datetime.utcnow)

quotes = relationship("Quote", back_populates="client")

class Product(Base):
tablename = "products"

id = Column(Integer, primary_key=True)
name = Column(String(200), nullable=False)
sku = Column(String(50), unique=True, nullable=True)
price = Column(Float, nullable=False, default=0.0)
stock_qty = Column(Integer, default=0)
unit = Column(String(30), default="قطعة")
description = Column(Text, nullable=True)

quote_items = relationship("QuoteItem", back_populates="product")

class Quote(Base):
tablename = "quotes"

id = Column(Integer, primary_key=True)
client_id = Column(Integer, ForeignKey("clients.id"))
quote_number = Column(String(50))
created_at = Column(DateTime, default=datetime.utcnow)
total_amount = Column(Float, default=0.0)
status = Column(String(30), default="مسودة")

client = relationship("Client", back_populates="quotes")
items = relationship("QuoteItem", back_populates="quote", cascade="all, delete-orphan")

class QuoteItem(Base):
tablename = "quote_items"

id = Column(Integer, primary_key=True)
quote_id = Column(Integer, ForeignKey("quotes.id"))
product_id = Column(Integer, ForeignKey("products.id"))
quantity = Column(Integer, default=1)
unit_price = Column(Float, default=0.0)

quote = relationship("Quote", back_populates="items")
product = relationship("Product", back_populates="quote_items")

def init_db():
os.makedirs(os.path.join(os.path.dirname(file), "data"), exist_ok=True)
Base.metadata.create_all(engine)

def get_session():
return SessionLocal()