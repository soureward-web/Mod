"""
scraper_maps.py
----------------
جلب أعمال/عملاء محتملين قريبين منك جغرافيًا عبر Google Places API.

⚠️ لماذا Places API وليس Selenium/Scraping مباشر من خرائط جوجل؟
- شروط استخدام جوجل تمنع استخراج بيانات خرائطها بالسكرابينج المباشر،
  وحساب الـ Selenium قد يُحظر أو يُوقَف مؤقتًا بسبب Captcha/Rate limiting.
- Places API رسمي، مستقر، ونتائجه دقيقة (هاتف، تقييم، عنوان، إحداثيات).
- التكلفة منخفضة جدًا لحجم استخدامك (مئات الاستعلامات شهريًا) وتوجد حصة مجانية شهرية.

خطوات الحصول على مفتاح API:
1. اذهب إلى https://console.cloud.google.com/
2. أنشئ مشروع جديد -> فعّل "Places API" و "Geocoding API"
3. أنشئ API Key من صفحة Credentials
4. ضع المفتاح في متغير بيئة GOOGLE_MAPS_API_KEY (أو في ملف .env)
"""

import os
import requests
from database import get_session, Client

def _get_api_key() -> str:
    env_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if env_key:
        return env_key
    try:
        import streamlit as st
        if "GOOGLE_MAPS_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_MAPS_API_KEY"]
    except Exception:
        pass
    return "ضع_مفتاحك_هنا"


API_KEY = _get_api_key()

NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def search_nearby_businesses(lat: float, lng: float, keyword: str,
                              radius_meters: int = 5000, max_results: int = 40):
    """
    يبحث عن أنشطة تجارية قريبة من إحداثيات معينة (lat, lng).

    مثال استخدام:
        search_nearby_businesses(33.5731, -7.5898, "مطاعم", radius_meters=3000)
        # الدار البيضاء - بحث عن مطاعم في نطاق 3 كم
    """
    results = []
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_meters,
        "keyword": keyword,
        "key": API_KEY,
    }

    while True:
        response = requests.get(NEARBY_SEARCH_URL, params=params, timeout=15)
        data = response.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"⚠️ خطأ من Google API: {data.get('status')} - {data.get('error_message', '')}")
            break

        for place in data.get("results", []):
            results.append({
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "latitude": place["geometry"]["location"]["lat"],
                "longitude": place["geometry"]["location"]["lng"],
                "rating": place.get("rating"),
                "place_id": place.get("place_id"),
                "category": keyword,
            })
            if len(results) >= max_results:
                return results

        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break

        # Google يتطلب مهلة قصيرة قبل استخدام next_page_token
        import time
        time.sleep(2)
        params = {"pagetoken": next_page_token, "key": API_KEY}

    return results


def enrich_with_details(place_id: str):
    """يجلب رقم الهاتف والموقع الإلكتروني لمكان معيّن عبر place_id."""
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number,website",
        "key": API_KEY,
    }
    response = requests.get(DETAILS_URL, params=params, timeout=15)
    data = response.json().get("result", {})
    return {
        "phone": data.get("formatted_phone_number"),
        "website": data.get("website"),
    }


def save_leads_to_db(leads: list, fetch_details: bool = True):
    """يحفظ نتائج البحث في قاعدة البيانات، متجنبًا التكرار حسب الاسم+العنوان."""
    session = get_session()
    saved_count = 0

    for lead in leads:
        exists = session.query(Client).filter_by(
            name=lead["name"], address=lead["address"]
        ).first()
        if exists:
            continue

        phone, website = None, None
        if fetch_details and lead.get("place_id"):
            details = enrich_with_details(lead["place_id"])
            phone, website = details.get("phone"), details.get("website")

        client = Client(
            name=lead["name"],
            phone=phone,
            address=lead["address"],
            category=lead.get("category"),
            source="google_maps",
            latitude=lead.get("latitude"),
            longitude=lead.get("longitude"),
            rating=lead.get("rating"),
            website=website,
            status="جديد",
        )
        session.add(client)
        saved_count += 1

    session.commit()
    session.close()
    return saved_count


if __name__ == "__main__":
    # مثال: بحث عن "محلات بناء" في نطاق 5 كم من نقطة معينة
    leads = search_nearby_businesses(33.5731, -7.5898, "محلات بناء", radius_meters=5000)
    print(f"🔎 تم العثور على {len(leads)} نتيجة")
    saved = save_leads_to_db(leads)
    print(f"💾 تم حفظ {saved} عميل جديد في قاعدة البيانات")
