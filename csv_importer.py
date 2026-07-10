"""
csv_importer.py
----------------
استيراد عملاء محتملين من ملف CSV أو Excel جاهز (مصدر إضافي قابل للتوسع).
الأعمدة المتوقعة (بأي ترتيب، غير حساسة لحالة الأحرف):
  name, phone, address, category, website, notes
الأعمدة الناقصة تُترك فارغة تلقائيًا.
"""

import pandas as pd
from database import get_session, Client


COLUMN_MAP = {
    "name": ["name", "اسم", "الاسم"],
    "phone": ["phone", "هاتف", "رقم الهاتف"],
    "address": ["address", "عنوان", "العنوان"],
    "category": ["category", "نوع", "الفئة"],
    "website": ["website", "موقع"],
    "notes": ["notes", "ملاحظات"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """يحاول مطابقة أعمدة الملف المرفوع مع الأعمدة المتوقعة بمرونة."""
    rename_dict = {}
    lower_cols = {c.lower().strip(): c for c in df.columns}

    for target, aliases in COLUMN_MAP.items():
        for alias in aliases:
            if alias.lower() in lower_cols:
                rename_dict[lower_cols[alias.lower()]] = target
                break

    return df.rename(columns=rename_dict)


def import_file(file_path: str) -> int:
    """يقرأ CSV أو Excel ويحفظ العملاء الجدد في قاعدة البيانات. يُرجع عدد العملاء المستوردين."""
    if file_path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    df = _normalize_columns(df)

    if "name" not in df.columns:
        raise ValueError("الملف لا يحتوي على عمود لاسم العميل (name).")

    session = get_session()
    imported = 0

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name or name.lower() == "nan":
            continue

        address = str(row.get("address", "") or "")
        exists = session.query(Client).filter_by(name=name, address=address).first()
        if exists:
            continue

        client = Client(
            name=name,
            phone=str(row.get("phone", "") or "") or None,
            address=address or None,
            category=str(row.get("category", "") or "") or None,
            website=str(row.get("website", "") or "") or None,
            notes=str(row.get("notes", "") or "") or None,
            source="csv",
            status="جديد",
        )
        session.add(client)
        imported += 1

    session.commit()
    session.close()
    return imported


if __name__ == "__main__":
    count = import_file("data/example_clients.csv")
    print(f"✅ تم استيراد {count} عميل جديد")
