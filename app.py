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

from database import init_db, get_session, Client, Product, Quote
from csv_importer import import_file
from scraper_maps import search_nearby_businesses as search_google, save_leads_to_db as save_google
from scraper_osm import search_nearby_businesses as search_osm, save_leads_to_db as save_osm
from quotes import (
    create_quote, export_quote_pdf, export_clients_excel,
    convert_quote_to_invoice, record_payment, get_paid_amount, get_payment_status,
)
from suppliers import create_supplier, list_suppliers, create_purchase, list_purchases

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

tab_dashboard, tab_leads, tab_products, tab_suppliers, tab_quotes, tab_payments = st.tabs(
    ["🏠 لوحة التحكم", "🔍 العملاء المحتملون", "📦 المنتجات",
     "🏭 الموردون والمشتريات", "🧾 عروض الأسعار والفواتير", "💰 الدفعات"]
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

    # --- ملخص مالي: المستحقات والأرباح التقديرية ---
    session = get_session()
    all_invoices = session.query(Quote).filter_by(is_invoice=True).all()
    session.close()

    if all_invoices:
        st.divider()
        st.subheader("💰 ملخص مالي")

        total_sales = sum(inv.total_amount for inv in all_invoices)
        total_paid = sum(get_paid_amount(inv.id) for inv in all_invoices)
        total_outstanding = total_sales - total_paid

        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("إجمالي المبيعات (فواتير)", f"{total_sales:.2f}")
        fc2.metric("المُحصَّل", f"{total_paid:.2f}")
        fc3.metric("المستحقات المتبقية", f"{total_outstanding:.2f}",
                   delta_color="inverse" if total_outstanding > 0 else "off")

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
                    const lat = pos.coords.latitude;
                    const lng = pos.coords.longitude;
                    var topOrigin = null;
                    try {
                        if (window.location.ancestorOrigins && window.location.ancestorOrigins.length > 0) {
                            topOrigin = window.location.ancestorOrigins[window.location.ancestorOrigins.length - 1];
                        }
                    } catch (e) {}

                    if (topOrigin) {
                        window.top.location.href = topOrigin + '/?lat=' + lat + '&lng=' + lng;
                    } else {
                        // خيار احتياطي إذا لم يدعم المتصفح ancestorOrigins
                        try {
                            window.top.location.href = '/?lat=' + lat + '&lng=' + lng;
                        } catch (e2) {
                            alert('تعذّر تحديث الصفحة تلقائيًا. حاول متصفحًا آخر مثل Chrome.');
                        }
                    }
                },
                function(err) {
                    alert('تعذّر الحصول على الموقع: ' + err.message +
                        ' — تأكد من السماح بالوصول للموقع من إعدادات المتصفح.');
                },
                { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 }
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
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("اسم المنتج")
        price = c2.number_input("سعر البيع", min_value=0.0, step=10.0)
        stock = c3.number_input("الكمية بالمخزون", min_value=0, step=1)
        low_threshold = c4.number_input("حد تنبيه النفاد", min_value=0, step=1, value=5)
        sku = st.text_input("رمز المنتج (SKU) - اختياري")
        add_btn = st.form_submit_button("➕ إضافة المنتج")

        if add_btn and name:
            try:
                session = get_session()
                session.add(Product(
                    name=name, price=price, stock_qty=int(stock),
                    low_stock_threshold=int(low_threshold), sku=sku or None
                ))
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
        low_stock = [p for p in products if p.stock_qty <= p.low_stock_threshold]
        if low_stock:
            names = "، ".join(f"{p.name} ({p.stock_qty})" for p in low_stock)
            st.warning(f"⚠️ منتجات على وشك النفاد: {names}")

        pdf_df = pd.DataFrame([{
            "المنتج": p.name,
            "سعر البيع": p.price,
            "تكلفة الشراء": p.cost_price,
            "الهامش": round(p.price - p.cost_price, 2),
            "المخزون": p.stock_qty,
            "SKU": p.sku,
        } for p in products])
        st.dataframe(pdf_df, use_container_width=True)
    else:
        st.info("لا توجد منتجات بعد.")

# =================================================================
# التبويب 4: الموردون والمشتريات
# =================================================================
with tab_suppliers:
    st.subheader("🏭 الموردون")

    with st.form("add_supplier_form"):
        sc1, sc2 = st.columns(2)
        supplier_name = sc1.text_input("اسم المورد")
        supplier_phone = sc2.text_input("الهاتف")
        supplier_address = st.text_input("العنوان (اختياري)")
        add_supplier_btn = st.form_submit_button("➕ إضافة مورد")

        if add_supplier_btn and supplier_name:
            create_supplier(supplier_name, supplier_phone or None, supplier_address or None)
            st.success("تمت إضافة المورد ✅")
            st.rerun()
        elif add_supplier_btn and not supplier_name:
            st.warning("الرجاء إدخال اسم المورد.")

    suppliers = list_suppliers()

    st.divider()
    st.subheader("🧾 تسجيل عملية شراء جديدة")

    session = get_session()
    products = session.query(Product).all()
    session.close()

    if not suppliers or not products:
        st.info("أضف موردًا واحدًا ومنتجًا واحدًا على الأقل أولًا لتسجيل عملية شراء.")
    else:
        supplier_choice = st.selectbox("اختر المورد", suppliers, format_func=lambda s: s.name)

        st.write("أدخل الكميات وتكلفة الشراء لكل منتج تريد إدخاله للمخزون:")
        purchase_items = []
        for p in products:
            pc1, pc2 = st.columns(2)
            qty = pc1.number_input(f"كمية {p.name}", min_value=0, step=1, key=f"pq_{p.id}")
            cost = pc2.number_input(f"تكلفة الوحدة ({p.name})", min_value=0.0, step=1.0,
                                     value=p.cost_price, key=f"pc_{p.id}")
            if qty > 0:
                purchase_items.append({"product_id": p.id, "quantity": qty, "unit_cost": cost})

        if st.button("💾 تسجيل عملية الشراء وتحديث المخزون"):
            if not purchase_items:
                st.error("أدخل كمية منتج واحد على الأقل.")
            else:
                create_purchase(supplier_choice.id, purchase_items)
                st.success("تم تسجيل الشراء وتحديث المخزون تلقائيًا ✅")
                st.rerun()

    st.divider()
    st.subheader("📜 سجل المشتريات")
    purchases = list_purchases()
    if purchases:
        purchases_df = pd.DataFrame([{
            "رقم الشراء": pu.purchase_number,
            "المورد": pu.supplier.name if pu.supplier else "-",
            "التاريخ": pu.created_at.strftime("%Y-%m-%d %H:%M"),
            "الإجمالي": pu.total_cost,
        } for pu in purchases])
        st.dataframe(purchases_df, use_container_width=True)
    else:
        st.info("لا توجد عمليات شراء بعد.")

# =================================================================
# التبويب 5: عروض الأسعار والفواتير
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

    st.divider()
    st.subheader("📜 سجل عروض الأسعار والفواتير")

    session = get_session()
    all_quotes = session.query(Quote).order_by(Quote.created_at.desc()).all()
    session.close()

    if not all_quotes:
        st.info("لا توجد عروض أسعار بعد.")
    else:
        for q in all_quotes:
            kind_badge = "🧾 فاتورة بيع" if q.is_invoice else "📋 عرض سعر"
            payment_status = get_payment_status(q)
            with st.expander(f"{kind_badge} — {q.quote_number} — {q.client.name if q.client else '-'} ({payment_status})"):
                st.write(f"الإجمالي: {q.total_amount:.2f}")
                st.write(f"التاريخ: {q.created_at.strftime('%Y-%m-%d %H:%M')}")
                if not q.is_invoice:
                    if st.button("✅ تحويل إلى فاتورة بيع (يخصم المخزون)", key=f"conv_{q.id}"):
                        convert_quote_to_invoice(q.id)
                        st.success("تم التحويل لفاتورة بيع، وخُصم المخزون تلقائيًا ✅")
                        st.rerun()
                else:
                    st.caption("✅ هذه فاتورة بيع فعلية، تم خصم المخزون بالفعل.")

# =================================================================
# التبويب 6: الدفعات
# =================================================================
with tab_payments:
    st.subheader("💰 تسجيل ومتابعة الدفعات")

    session = get_session()
    invoices = session.query(Quote).filter_by(is_invoice=True).order_by(Quote.created_at.desc()).all()
    session.close()

    if not invoices:
        st.info("لا توجد فواتير بيع بعد. حوّل عرض سعر إلى فاتورة أولًا من تبويب 'عروض الأسعار والفواتير'.")
    else:
        invoice_choice = st.selectbox(
            "اختر الفاتورة",
            invoices,
            format_func=lambda q: f"{q.quote_number} — {q.client.name if q.client else '-'} ({get_payment_status(q)})"
        )

        paid_so_far = get_paid_amount(invoice_choice.id)
        remaining = invoice_choice.total_amount - paid_so_far

        col1, col2, col3 = st.columns(3)
        col1.metric("الإجمالي", f"{invoice_choice.total_amount:.2f}")
        col2.metric("المدفوع", f"{paid_so_far:.2f}")
        col3.metric("المتبقي", f"{remaining:.2f}")

        with st.form("record_payment_form"):
            pay_amount = st.number_input("مبلغ الدفعة", min_value=0.0, step=50.0)
            pay_method = st.selectbox("طريقة الدفع", ["نقدًا", "تحويل بنكي", "شيك", "أخرى"])
            pay_notes = st.text_input("ملاحظات (اختياري)")
            record_btn = st.form_submit_button("💾 تسجيل الدفعة")

            if record_btn and pay_amount > 0:
                record_payment(invoice_choice.id, pay_amount, pay_method, pay_notes or None)
                st.success("تم تسجيل الدفعة ✅")
                st.rerun()
            elif record_btn:
                st.warning("أدخل مبلغًا أكبر من صفر.")

        st.divider()
        st.subheader("سجل الدفعات لهذه الفاتورة")
        if invoice_choice.payments:
            payments_df = pd.DataFrame([{
                "التاريخ": p.payment_date.strftime("%Y-%m-%d %H:%M"),
                "المبلغ": p.amount,
                "الطريقة": p.method,
                "ملاحظات": p.notes or "-",
            } for p in invoice_choice.payments])
            st.dataframe(payments_df, use_container_width=True)
        else:
            st.caption("لا توجد دفعات مسجلة على هذه الفاتورة بعد.")
