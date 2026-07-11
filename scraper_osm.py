"""
scraper_osm.py
----------------
بديل مجاني بالكامل لـ Google Places API - يستخدم OpenStreetMap عبر Overpass API.
لا يحتاج أي مفتاح API ولا بطاقة بنكية ولا حساب - مناسب للتجربة الفورية.

⚠️ الفرق عن Google Maps:
- البيانات مجانية بالكامل لكنها أقل اكتمالًا (قد ينقص رقم الهاتف لبعض الأماكن)
- لا حدود صارمة للاستخدام المعتدل، لكن يُفضل عدم الإفراط في الطلبات (مهلة بين الطلبات)
- ممتاز للتجربة والتعلم، ويمكن التحول لاحقًا لـ Google Places لبيانات أدق
"""

import requests
from database import get_session, Client

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def search_nearby_businesses(lat: float, lng: float, keyword: str, radius_meters: int = 5000):
    """
    يبحث عن أنشطة تجارية قريبة من إحداثيات معينة عبر OpenStreetMap.

    keyword أمثلة شائعة (تُطابق تصنيفات OSM):
        "restaurant", "cafe", "pharmacy", "hardware", "supermarket",
        "clothes", "bakery", "car_repair", "hairdresser"

    مثال استخدام:
        search_nearby_businesses(33.5731, -7.5898, "restaurant", radius_meters=3000)
    """
    # استعلام Overpass QL: يبحث عن نقاط (nodes) بها الوسم shop أو amenity المطلوب
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="{keyword}"](around:{radius_meters},{lat},{lng});
      node["shop"="{keyword}"](around:{radius_meters},{lat},{lng});
    );
    out body;
    """

    headers = {
        "User-Agent": "LeadGenApp/1.0 (streamlit business lead finder)"
    }
    response = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    results = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # نتجاهل النقاط بدون اسم (غير مفيدة كعميل محتمل)

        address_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", ""),
        ]
        address = " ".join(p for p in address_parts if p) or None

        results.append({
            "name": name,
            "address": address,
            "latitude": element.get("lat"),
            "longitude": element.get("lon"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "category": keyword,
        })

    return results


def save_leads_to_db(leads: list):
    """يحفظ نتائج البحث في قاعدة البيانات، متجنبًا التكرار حسب الاسم."""
    session = get_session()
    saved_count = 0

    for lead in leads:
        exists = session.query(Client).filter_by(name=lead["name"]).first()
        if exists:
            continue

        client = Client(
            name=lead["name"],
            phone=lead.get("phone"),
            address=lead.get("address"),
            category=lead.get("category"),
            source="openstreetmap",
            latitude=lead.get("latitude"),
            longitude=lead.get("longitude"),
            website=lead.get("website"),
            status="جديد",
        )
        session.add(client)
        saved_count += 1

    session.commit()
    session.close()
    return saved_count


if __name__ == "__main__":
    leads = search_nearby_businesses(33.5731, -7.5898, "restaurant", radius_meters=3000)
    print(f"🔎 تم العثور على {len(leads)} نتيجة")
    saved = save_leads_to_db(leads)
    print(f"💾 تم حفظ {saved} عميل جديد في قاعدة البيانات")
