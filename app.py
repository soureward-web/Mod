"""
app.py
-------
لوحة تحكم Streamlit: عرض العملاء، تغيير حالتهم، إدارة المنتجات،
إنشاء عروض أسعار، استيراد ملفات، وتصدير تقارير.

للتشغيل:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import os

from database import init_db, get_session, Client, Product
from csv_importer import import_file
from scraper_maps import search_nearby_businesses as search_google, save_leads_to_db as save_google
from scraper_osm import search_nearby_businesses as search_osm, save_leads_to_db as save_osm
from quotes import create_quote, export_quote_pdf, export_clients_excel

# ---------------------------------------------------------------
init_db()
st.set_page_config(
    page_title="نظام إدارة العملاء والمبيعات",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- تنسيق مخصص لمظهر أكثر احترافية (بطاقات، أزرار، تباعد) ---
st.markdown("""
<style>
    /* تباعد أنظف أعلى الصفحة */
    .block-container { padding-top: 2rem; }

    /* بطاقات المقاييس (عدد العملاء، إلخ) */
    div[data-testid="stMetric"] {
        background-color: #1C1F26;
        border: 1px solid #2A2E37;
        border-radius: 10px;
        padding: 1rem 1rem 0.6rem 1rem;
    }
    div[data-testid="stMetricLabel"] { font-size: 0.95rem; }

    /* أزرار بلون أساسي مميز */
    .stButton>button, .stFormSubmitButton>button {
        border-radius: 8px;
        font-weight: 600;
    }

    /* تبويبات أوضح وأسهل قراءة */
    button[data-baseweb="tab"] { font-size: 1.05rem; padding: 0.5rem 1rem; }

    /* عناصر expander (بطاقات العملاء) بحواف مستديرة */
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid #2A2E37;
    }
</style>
""", unsafe_allow_html=True)

STATUS_OPTIONS = ["جديد", "تم التواصل", "مهتم", "متفاوض", "مشترٍ", "غير مهتم"]

# --- شارات ألوان لكل حالة، تُستخدم أينما ظهرت الحالة ---
STATUS_COLORS = {
    "جديد": "🔵",
    "تم التواصل": "🟡",
    "مهتم": "🟢",
    "متفاوض": "🟠",
    "مشترٍ": "✅",
    "غير مهتم": "⚪",
}

st.title("📊 نظام إيجاد العملاء المحتملين وإدارة المبيعات")
st.caption("لوحة تحكم مركزية لإدارة عملائك ومنتجاتك وعروض أسعارك")

tab_dashboard, tab_leads, tab_products, tab_quotes = st.tabs(
    ["🏠 لوحة التحكم", "🔍 العملاء المحتملون", "📦 المنتجات", "🧾 عروض الأسعار"]
)

# =================================================================
# التبويب 1: لوحة التحكم العامة
# =================================================================
with tab_dashboard:
    session = get_session()
    clients = session.query(Client).all()
    session.close()

    df = pd.DataFrame([{
        "id": c.id, "name": c.name, "status": c.status,
        "category": c.category, "source": c.source
    } for c in clients])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("إجمالي العملاء", len(df))
    if not df.empty:
        col2.metric("مهتمون", (df["status"] == "مهتم").sum())
        col3.metric("متفاوضون", (df["status"] == "متفاوض").sum())
        col4.metric("مشترون", (df["status"] == "مشترٍ").sum())
    else:
        col2.metric("مهتمون", 0)
        col3.metric("متفاوضون", 0)
        col4.metric("مشترون", 0)

    if not df.empty:
        st.subheader("توزيع العملاء حسب الحالة")
        st.bar_chart(df["status"].value_counts())

        st.subheader("توزيع العملاء حسب المصدر")
        st.bar_chart(df["source"].value_counts())
    else:
        st.markdown("### 👋 مرحبًا بك!")
        st.info(
            "لا يوجد عملاء بعد. اذهب إلى تبويب **'🔍 العملاء المحتملون'** وابحث حول موقعك "
            "لتبدأ في جمع عملاء محتملين تلقائيًا، أو استورد قائمة جاهزة من ملف Excel/CSV."
        )

# =================================================================
# التبويب 2: البحث عن عملاء محتملين + إدارتهم
# =================================================================
with tab_leads:
    st.subheader("🔍 البحث عن عملاء قريبين")

    # --- قراءة الإحداثيات من رابط الصفحة إن وافق المستخدم على مشاركة موقعه ---
    if "lat" in st.query_params and "lng" in st.query_params:
        try:
            st.session_state["auto_lat"] = float(st.query_params["lat"])
            st.session_state["auto_lng"] = float(st.query_params["lng"])
        except (ValueError, TypeError):
            pass

    if st.button("📍 استخدم موقعي الحالي"):
        st.components.v1.html(
            """
            <script>
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set('lat', pos.coords.latitude);
                    url.searchParams.set('lng', pos.coords.longitude);
                    window.parent.location.href = url.toString();
                },
                function(err) {
                    window.parent.alert('تعذّر الحصول على الموقع: ' + err.message +
                        ' — تأكد من السماح بالوصول للموقع من إعدادات المتصفح.');
                }
            );
            </script>
            """,
            height=0,
        )
        st.info("⏳ بانتظار موافقتك على مشاركة الموقع من المتصفح...")

    source_choice = st.radio(
        "اختر مصدر البحث:",
        ["🆓 OpenStreetMap (مجاني - بدون مفتاح)", "🗺️ Google Maps (يحتاج مفتاح API)"],
        horizontal=False,
    )
    use_osm = source_choice.startswith("🆓")

    with st.form("maps_search_form"):
        c1, c2, c3 = st.columns(3)
        lat = c1.number_input(
            "خط العرض (Latitude)",
            value=st.session_state.get("auto_lat", 33.5731),
            format="%.6f"
        )
        lng = c2.number_input(
            "خط الطول (Longitude)",
            value=st.session_state.get("auto_lng", -7.5898),
            format="%.6f"
        )
        radius = c3.number_input("نطاق البحث (متر)", value=5000, step=500)

        if use_osm:
            keyword = st.text_input(
                "نوع النشاط (بالإنجليزية - مثل: restaurant, cafe, pharmacy, supermarket)",
                value="restaurant"
            )
        else:
            keyword = st.text_input("نوع النشاط / كلمة البحث", value="محلات بناء")

        submitted = st.form_submit_button("🔎 ابحث واحفظ النتائج")

        if submitted:
            try:
                with st.spinner("جاري البحث..."):
                    if use_osm:
                        leads = search_osm(lat, lng, keyword, radius_meters=int(radius))
                        saved = save_osm(leads)
                    else:
                        leads = search_google(lat, lng, keyword, radius_meters=int(radius))
                        saved = save_google(leads)
                st.success(f"تم العثور على {len(leads)} نتيجة، وحفظ {saved} عميل جديد ✅")
            except Exception as e:
                st.error(f"⚠️ تعذّر إتمام البحث: {e}")

    st.divider()
    st.subheader("📁 استيراد عملاء من ملف CSV / Excel")
    uploaded_file = st.file_uploader("ارفع ملف", type=["csv", "xlsx", "xls"])
    if uploaded_file is not None:
        temp_path = os.path.join("data", uploaded_file.name)
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        if st.button("استيراد الملف الآن"):
            count = import_file(temp_path)
            st.success(f"تم استيراد {count} عميل جديد ✅")

    st.divider()
    st.subheader("📋 قائمة العملاء وإدارة الحالة")

    session = get_session()
    clients = session.query(Client).order_by(Client.created_at.desc()).all()
    session.close()

    if clients:
        # --- فلاتر سريعة لتسهيل تصفح قائمة طويلة ---
        fcol1, fcol2 = st.columns([2, 1])
        with fcol1:
            search_term = st.text_input("🔎 ابحث بالاسم", placeholder="اكتب جزءًا من اسم العميل...")
        with fcol2:
            status_filter = st.multiselect("تصفية حسب الحالة", STATUS_OPTIONS)

        filtered_clients = clients
        if search_term:
            filtered_clients = [c for c in filtered_clients if search_term.strip() in c.name]
        if status_filter:
            filtered_clients = [c for c in filtered_clients if c.status in status_filter]

        st.caption(f"عرض {len(filtered_clients)} من أصل {len(clients)} عميل")

        selected_ids = []
        for c in filtered_clients:
            badge = STATUS_COLORS.get(c.status, "⚪")
            with st.expander(f"{badge} **{c.name}** — {c.status} ({c.category or 'غير محدد'})"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📍 العنوان: {c.address or '-'}")
                    st.write(f"📞 الهاتف: {c.phone or '-'}")
                    st.write(f"🌐 الموقع: {c.website or '-'}")
                    st.write(f"⭐ التقييم: {c.rating or '-'}")
                    include = st.checkbox("تحديد للتصدير", key=f"chk_{c.id}")
                    if include:
                        selected_ids.append(c.id)
                with col2:
                    new_status = st.selectbox(
                        "الحالة", STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(c.status) if c.status in STATUS_OPTIONS else 0,
                        key=f"status_{c.id}"
                    )
                    if new_status != c.status:
                        s = get_session()
                        obj = s.query(Client).get(c.id)
                        obj.status = new_status
                        s.commit()
                        s.close()
                        st.rerun()

        if selected_ids and st.button("📤 تصدير العملاء المحددين إلى Excel"):
            path = export_clients_excel(selected_ids)
            with open(path, "rb") as f:
                st.download_button("⬇️ تحميل ملف Excel", f, file_name=os.path.basename(path))
    else:
        st.info("لا يوجد عملاء بعد.")

# =================================================================
# التبويب 3: إدارة المنتجات
# =================================================================
with tab_products:
    st.subheader("📦 إدارة المنتجات (مادية)")

    with st.form("add_product_form"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("اسم المنتج")
        price = c2.number_input("السعر", min_value=0.0, step=10.0)
        stock = c3.number_input("الكمية بالمخزون", min_value=0, step=1)
        sku = st.text_input("رمز المنتج (SKU) - اختياري")
        add_btn = st.form_submit_button("➕ إضافة المنتج")

        if add_btn and name:
            try:
                session = get_session()
                session.add(Product(name=name, price=price, stock_qty=int(stock), sku=sku or None))
                session.commit()
                session.close()
                st.success("تمت إضافة المنتج ✅")
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ تعذّرت إضافة المنتج. جرّب مرة أخرى. ({e})")
        elif add_btn and not name:
            st.warning("الرجاء إدخال اسم المنتج أولًا.")

    session = get_session()
    products = session.query(Product).all()
    session.close()

    if products:
        pdf_df = pd.DataFrame([{
            "المنتج": p.name, "السعر": p.price, "المخزون": p.stock_qty, "SKU": p.sku
        } for p in products])
        st.dataframe(pdf_df, use_container_width=True)
    else:
        st.info("لا توجد منتجات بعد.")

# =================================================================
# التبويب 4: عروض الأسعار
# =================================================================
with tab_quotes:
    st.subheader("🧾 إنشاء عرض سعر جديد")

    session = get_session()
    clients = session.query(Client).all()
    products = session.query(Product).all()
    session.close()

    if not clients or not products:
        st.warning("يجب إضافة عميل واحد ومنتج واحد على الأقل أولًا.")
    else:
        client_choice = st.selectbox("اختر العميل", clients, format_func=lambda c: c.name)

        st.write("اختر المنتجات والكميات:")
        selected_items = []
        for p in products:
            qty = st.number_input(f"{p.name} (سعر: {p.price})", min_value=0, step=1, key=f"qty_{p.id}")
            if qty > 0:
                selected_items.append({"product_id": p.id, "quantity": qty})

        if st.button("📝 إنشاء عرض السعر"):
            if not selected_items:
                st.error("اختر منتجًا واحدًا على الأقل.")
            else:
                quote_id = create_quote(client_choice.id, selected_items)
                pdf_path = export_quote_pdf(quote_id, company_name="اسم شركتك هنا")
                st.success("تم إنشاء عرض السعر ✅")
                with open(pdf_path, "rb") as f:
                    st.download_button("⬇️ تحميل عرض السعر PDF", f, file_name=os.path.basename(pdf_path))
