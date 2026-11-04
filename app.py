import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
from io import BytesIO
from PIL import Image
import math
import hashlib
import urllib.parse
import cloudinary
import cloudinary.uploader

# ==========================================
# 1. DATABASE & STORAGE INITIALIZATION
# ==========================================
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"Database connection failed. Please verify Streamlit Cloud Secrets! Error: {e}")
    st.stop()

# Initialize Cloudinary Configuration
try:
    cloudinary.config(
        cloud_name=st.secrets["CLOUDINARY_CLOUD_NAME"],
        api_key=st.secrets["CLOUDINARY_API_KEY"],
        api_secret=st.secrets["CLOUDINARY_API_SECRET"],
        secure=True
    )
except Exception as e:
    st.error(f"Cloudinary configuration missing from secrets! Error: {e}")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit() or c == '+').strip()

# AUTO-INITIALIZE SECURE DEFAULT ADMIN USER IF WORKERS TABLE IS EMPTY
try:
    check_empty = supabase.table("workers").select("*", count="exact").execute()
    if not check_empty.data:
        supabase.table("workers").insert({
            "name": "admin", 
            "role": "CEO", 
            "password": hash_password("Sammyreks2026!")
        }).execute()
except Exception:
    pass

@st.cache_data(ttl=60)
def fetch_dataframe_cached(table_name):
    """Optimized cached data fetcher to stop egress spikes and maximize speed."""
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as err:
        return pd.DataFrame()

def fetch_dataframe(table_name):
    """Standard live fetcher for real-time transactional tables."""
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as err:
        return pd.DataFrame()

# ==========================================
# 2. CLOUDINARY & CORE UTILITY FUNCTIONS
# ==========================================
store_title = "Sammyreks Business Center"

def upload_image_to_cloudinary(uploaded_file, folder="sammyreks_products"):
    """Uploads and optimizes images on Cloudinary, returning a secure URL."""
    if uploaded_file is not None:
        try:
            if isinstance(uploaded_file, Image.Image):
                buffered = BytesIO()
                uploaded_file.save(buffered, format="JPEG", quality=80)
                file_bytes = buffered.getvalue()
            else:
                file_bytes = uploaded_file.read()

            upload_result = cloudinary.uploader.upload(
                file_bytes,
                folder=folder,
                resource_type="image",
                transformation=[
                    {"width": 800, "height": 800, "crop": "limit"},
                    {"quality": "auto", "fetch_format": "auto"}
                ]
            )
            return upload_result.get("secure_url")
        except Exception as e:
            st.error(f"Cloudinary image upload error: {e}")
            return None
    return None

def upload_video_to_cloudinary(uploaded_file, folder="sammyreks_videos"):
    """Uploads video files directly to Cloudinary, returning a secure streaming URL."""
    if uploaded_file is not None:
        try:
            file_bytes = uploaded_file.read()
            upload_result = cloudinary.uploader.upload(
                file_bytes,
                folder=folder,
                resource_type="video",
                chunk_size=6000000
            )
            return upload_result.get("secure_url")
        except Exception as e:
            st.error(f"Cloudinary video upload error: {e}")
            return None
    return None

def generate_whatsapp_link(phone, receipt_type, customer_name, items_list, grand_total):
    clean_phone = "".join(c for c in phone if c.isdigit())
    items_text = "\n".join([f"- {i.get('name', 'Item')} ({i.get('unit', 'Unit')}) x{i.get('qty', 1)} @ ₦{i.get('price', 0):,.2f} = ₦{i.get('total', 0):,.2f}" for i in items_list])
    
    message = (
        f"🏢 *{store_title}*\n"
        f"*{receipt_type}*\n\n"
        f"👤 *Customer:* {customer_name}\n"
        f"📞 *Phone:* {phone}\n\n"
        f"🛒 *Items:* \n{items_text}\n\n"
        f"💰 *Grand Total: ₦{grand_total:,.2f}*\n\n"
        f"Thank you for your patronage!"
    )
    
    encoded_msg = urllib.parse.quote(message)
    if clean_phone:
        return f"https://wa.me/{clean_phone}?text={encoded_msg}"
    else:
        return f"https://wa.me/?text={encoded_msg}"

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sanitize_payload(payload):
    cleaned = {}
    for k, v in payload.items():
        if v is None:
            cleaned[k] = 0 if k in ['qty_cartons', 'packs_per_carton', 'units_per_pack'] else (0.0 if k in ['cost', 'price_carton', 'price_pack', 'price_retail'] else "")
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v) or pd.isna(v):
                cleaned[k] = 0.0 if k in ['cost', 'price_carton', 'price_pack', 'price_retail'] else 0
            else:
                cleaned[k] = v
        else:
            cleaned[k] = v
    return cleaned

# ==========================================
# 3. UI CONFIGURATION & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Sammyreks Business Center", layout="wide", page_icon="🏢")

st.markdown("""
    <style>
        .stButton>button {
            font-size: 1.15rem !important;
            font-weight: bold !important;
            padding: 12px 16px !important;
            border-radius: 10px !important;
            margin-bottom: 5px !important;
        }
        div[data-baseweb="tab"] {
            font-size: 1.25rem !important;
            font-weight: bold !important;
            padding: 12px 18px !important;
        }
    </style>
""", unsafe_allow_html=True)

if 'auth' not in st.session_state:
    st.session_state.auth = {"logged_in": False, "user": None, "role": None}

if 'cart' not in st.session_state:
    st.session_state.cart = []

if 'last_receipt' not in st.session_state:
    st.session_state.last_receipt = None

if 'request_items_temp' not in st.session_state:
    st.session_state.request_items_temp = [{"item": "", "qty": 1}]

if 'cust_active_page' not in st.session_state:
    st.session_state.cust_active_page = "🛒 Shop & Cart"

if 'active_cust_phone' not in st.session_state:
    st.session_state.active_cust_phone = ""

if 'active_cust_name' not in st.session_state:
    st.session_state.active_cust_name = ""

st.sidebar.title("🏢 Sammyreks Portal")
st.sidebar.markdown("---")

if not st.session_state.auth["logged_in"]:
    auth_mode = st.sidebar.selectbox("Choose Portal", ["🛍️ Customer Shop", "🔑 Staff/Admin Login"], key="auth_mode_sel")
    
    if auth_mode == "🔑 Staff/Admin Login":
        with st.sidebar.form("login_form"):
            user_input = st.text_input("Username", key="login_user").strip()
            pass_input = st.text_input("Password", type="password", key="login_pass").strip()
            if st.form_submit_button("Login"):
                if not user_input or not pass_input:
                    st.error("Please enter both Username and Password.")
                else:
                    try:
                        if user_input.lower() == "admin" and pass_input == "Sammyreks2026!":
                            st.session_state.auth = {
                                "logged_in": True, 
                                "user": "admin", 
                                "role": "CEO"
                            }
                            st.success("Welcome back, admin!")
                            st.rerun()
                        else:
                            hashed_attempt = hash_password(pass_input)
                            res = supabase.table("workers").select("role, name").ilike("name", user_input).eq("password", hashed_attempt).execute()
                            if res.data and len(res.data) > 0:
                                matched_user = res.data[0]
                                st.session_state.auth = {
                                    "logged_in": True, 
                                    "user": matched_user['name'], 
                                    "role": matched_user['role']
                                }
                                st.success(f"Welcome back, {matched_user['name']}!")
                                st.rerun()
                            else:
                                st.error("Incorrect username or password.")
                    except Exception as e:
                        st.error(f"Login error: {e}")
                        
    view_mode = "CUSTOMER"
else:
    st.sidebar.success(f"Logged in: {st.session_state.auth['user']} ({st.session_state.auth['role']})")
    if st.sidebar.button("Logout", key="logout_btn"):
        st.session_state.auth = {"logged_in": False, "user": None, "role": None}
        st.rerun()
    view_mode = "STAFF"

# ==========================================
# 4. STAFF & CEO DASHBOARD
# ==========================================
if view_mode == "STAFF":
    role = st.session_state.auth["role"]
    user_logged = st.session_state.auth["user"]
    
    st.title(f"🏢 Dashboard: {store_title}")

    # FULL RESTORED MENU INCLUDING MANAGEMENT & WORKERS TABS FOR CEO
    menu = ["📊 Dashboard", "🛒 POS & Sales", "📦 Inventory", "📋 Orders/Requests", "💬 Customer Chats", "📓 Debtors", "⚙️ Settings"]
    if role == "CEO":
        menu += ["💸 Expenses", "👥 Workers"]
    
    tabs = st.tabs(menu)

    # TAB 0: DASHBOARD
    with tabs[0]:
        st.header("📊 Business Analytics")
        df_s = fetch_dataframe("sales")
        df_e = fetch_dataframe("expenses")
        
        c1, c2, c3, c4 = st.columns(4)
        total_rev = df_s['total'].sum() if not df_s.empty and 'total' in df_s.columns else 0
        total_prof = df_s['profit'].sum() if not df_s.empty and 'profit' in df_s.columns else 0
        total_exp = df_e['amount'].sum() if not df_e.empty and 'amount' in df_e.columns else 0
        
        c1.metric("Total Revenue", f"₦{total_rev:,.2f}")
        c2.metric("Total Profit", f"₦{total_prof:,.2f}")
        c3.metric("Total Expenses", f"₦{total_exp:,.2f}")
        c4.metric("Net Cashflow", f"₦{(total_prof - total_exp):,.2f}")
        st.divider()
        if not df_s.empty:
            st.dataframe(df_s.sort_values('timestamp', ascending=False), use_container_width=True, hide_index=True)

    # TAB 1: POS & SALES
    with tabs[1]:
        st.header("💳 POS & Sales Counter")
        df_p_pos = fetch_dataframe_cached("products")
            
        if not df_p_pos.empty:
            col_pos1, col_pos2 = st.columns([2, 1])
            with col_pos1:
                sel_item = st.selectbox("Search & Select Item", df_p_pos['name'], key="pos_sel_item")
                p = df_p_pos[df_p_pos['name'] == sel_item].iloc[0]
                
                m_label = p.get('unit_main_label', 'Carton') or 'Carton'
                p_label = p.get('unit_pack_label', 'Pack') or 'Pack'
                r_label = p.get('unit_retail_label', 'Retail Unit') or 'Retail Unit'
                
                sale_unit = st.radio("Selling Unit", [m_label, p_label, r_label], key="pos_sale_unit")
                sale_qty = st.number_input("Quantity", min_value=1, value=1, key="pos_sale_qty")
                c_name_pos = st.text_input("Customer Name", key="pos_cust_name")
                c_phone_pos = normalize_phone(st.text_input("Customer Phone Number", key="pos_cust_phone"))
            with col_pos2:
                up = p['price_carton'] if sale_unit == m_label else (p['price_pack'] if sale_unit == p_label else p['price_retail'])
                grand_total = up * sale_qty
                st.subheader(f"Total: ₦{grand_total:,.2f}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🏁 Cash Sale & Delivery Receipt", use_container_width=True, key="pos_cash_btn"):
                        packs_per_c = p.get('packs_per_carton', 1) or 1
                        units_per_p = p.get('units_per_pack', 1) or 1
                        
                        if sale_unit == m_label:
                            uc = p['cost']
                            cartons_deducted = sale_qty
                        elif sale_unit == p_label:
                            uc = p['cost'] / packs_per_c
                            cartons_deducted = sale_qty / packs_per_c
                        else:
                            uc = (p['cost'] / packs_per_c) / units_per_p
                            cartons_deducted = sale_qty / (packs_per_c * units_per_p)
                            
                        profit_final = grand_total - (uc * sale_qty)
                        
                        sale_data = {
                            "item": sel_item, "unit_type": sale_unit, "qty": int(sale_qty),
                            "total": float(grand_total), "profit": float(profit_final), "date": date.today().isoformat(),
                            "timestamp": get_now(), "worker": user_logged, "customer_name": c_name_pos, "customer_phone": c_phone_pos
                        }
                        supabase.table("sales").insert(sale_data).execute()
                        
                        new_qty = float(p['qty_cartons'] - cartons_deducted)
                        supabase.table("products").update({"qty_cartons": new_qty}).eq("id", int(p['id'])).execute()
                        st.cache_data.clear()
                            
                        st.session_state.last_receipt = {
                            "type": "Successful Delivery Receipt", 
                            "customer": c_name_pos or "Walk-in Customer",
                            "phone": c_phone_pos or "N/A", 
                            "date": get_now(),
                            "sold_items": [{"name": sel_item, "unit": sale_unit, "qty": sale_qty, "price": up, "total": grand_total}],
                            "grand_total": grand_total, 
                            "cashier": user_logged
                        }
                        st.success("Sale Recorded & Delivery Receipt Generated!")
                        st.rerun()
                
                with col_btn2:
                    if st.button("📓 Record Debt", use_container_width=True, key="pos_debt_btn"):
                        if not c_name_pos:
                            st.error("Customer name required for Debt Evidence!")
                        else:
                            evidence = f"{sale_qty} {sale_unit}(s) of {sel_item}"
                            debt_data = {
                                "customer": c_name_pos, "amount": float(grand_total), "items_bought": evidence,
                                "phone": c_phone_pos, "date": date.today().isoformat(), "timestamp": get_now()
                            }
                            supabase.table("debtors").insert(debt_data).execute()
                            
                            packs_per_c = p.get('packs_per_carton', 1) or 1
                            units_per_p = p.get('units_per_pack', 1) or 1
                            if sale_unit == m_label:
                                cartons_deducted = sale_qty
                            elif sale_unit == p_label:
                                cartons_deducted = sale_qty / packs_per_c
                            else:
                                cartons_deducted = sale_qty / (packs_per_c * units_per_p)
                                
                            new_qty = float(p['qty_cartons'] - cartons_deducted)
                            supabase.table("products").update({"qty_cartons": new_qty}).eq("id", int(p['id'])).execute()
                            st.cache_data.clear()
                                
                            st.warning(f"Debt logged for {c_name_pos}!")
                            st.rerun()

        if st.session_state.last_receipt:
            st.markdown("---")
            rec = st.session_state.last_receipt
            rec_type = rec.get('type', 'Official Receipt')
            sold_items_list = rec.get('sold_items', rec.get('items', []))
            cust_name_rc = rec.get('customer', 'Walk-in Customer')
            cust_phone_rc = rec.get('phone', 'N/A')
            g_total_rc = rec.get('grand_total', 0.0)

            rows_html = "".join([
                f"<tr style='border-bottom:1px solid #e0e0e0;'><td style='padding:10px;'>{itm.get('name','Item')} ({itm.get('unit','Unit')})</td><td style='padding:10px;text-align:center;'>{itm.get('qty',1)}</td><td style='padding:10px;text-align:right;'>₦{itm.get('price',0.0):,.2f}</td><td style='padding:10px;text-align:right;font-weight:bold;'>₦{itm.get('total',0.0):,.2f}</td></tr>"
                for itm in sold_items_list
            ])

            html_code = f"""
            <div style="background:#ffffff;color:#111;padding:24px;border-radius:12px;border:2.5px solid #1565c0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:620px;margin:auto;">
                <div style="text-align:center;"><h2 style="margin:0;color:#1565c0;">🏢 {store_title}</h2><p style="margin:4px 0;color:#555;font-weight:600;">{rec_type}</p></div>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <p style="margin:4px 0;"><b>Customer Name:</b> {cust_name_rc}</p>
                <p style="margin:4px 0;"><b>Phone Number:</b> {cust_phone_rc}</p>
                <p style="margin:4px 0;"><b>Date/Time:</b> {rec.get('date','')} | <b>Staff:</b> {rec.get('cashier','Staff')}</p>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                    <thead><tr style="background:#f5f7fa;border-bottom:2px solid #ddd;"><th style="padding:10px;text-align:left;">Item</th><th style="padding:10px;text-align:center;">Qty</th><th style="padding:10px;text-align:right;">Price</th><th style="padding:10px;text-align:right;">Total</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <h3 style="text-align:right;color:#1565c0;margin:10px 0;">Grand Total: ₦{g_total_rc:,.2f}</h3>
            </div>
            """
            components.html(html_code, height=360 + (len(sold_items_list) * 45), scrolling=True)

            wa_url = generate_whatsapp_link(cust_phone_rc, rec_type, cust_name_rc, sold_items_list, g_total_rc)
            st.markdown(f"""
                <a href="{wa_url}" target="_blank">
                    <button style="width:100%; background-color:#25d366; color:white; padding:12px; border:none; border-radius:8px; font-size:1.1rem; font-weight:bold; cursor:pointer; margin-top:10px;">
                        💬 Send Receipt via WhatsApp
                    </button>
                </a>
            """, unsafe_allow_html=True)

            if st.button("❌ Close Receipt View", key="close_receipt_btn"):
                st.session_state.last_receipt = None
                st.rerun()

    # TAB 2: INVENTORY CONTROL
    with tabs[2]:
        st.header("📦 Stock & Warehouse Control (Cloudinary Powered)")
        df_inv = fetch_dataframe_cached("products")
        
        if not df_inv.empty:
            st.dataframe(df_inv.drop(columns=['img_data'], errors='ignore'), use_container_width=True, hide_index=True)
        st.divider()
        
        st.subheader("📝 Add / Update Item")
        action = st.radio("Action", ["Add New Item", "Update Existing Item"], horizontal=True, key="inv_action_radio")
        
        curr_data = {
            "name": "", "cost": 0.0, "price_carton": 0.0, "price_pack": 0.0, "price_retail": 0.0,
            "qty_cartons": 0, "packs_per_carton": 1, "units_per_pack": 1, "shelf": "",
            "expiry": str(date.today()), "description": "", "img_data": "", "video_url": "",
            "unit_main_label": "Carton", "unit_pack_label": "Pack", "unit_retail_label": "Retail Unit",
            "category": "General"
        }
        
        target_id = "new"
        if action == "Update Existing Item" and not df_inv.empty:
            target = st.selectbox("Select Item to Update", df_inv['name'], key="update_item_selectbox")
            selected_row = df_inv[df_inv['name'] == target]
            if not selected_row.empty:
                curr_data = selected_row.iloc[0].to_dict()
                target_id = str(curr_data.get('id', 'new'))

        st.write("📷 **Product Image Input (Uploaded instantly to Cloudinary)**")
        img_tab1, img_tab2 = st.tabs(["📁 Upload Image File", "📋 Paste from Clipboard"])
        chosen_image = None

        with img_tab1:
            n_file = st.file_uploader("Choose image file", type=["png", "jpg", "jpeg"], label_visibility="collapsed", key=f"img_uploader_{target_id}")
            if n_file: 
                chosen_image = n_file

        with img_tab2:
            try:
                from streamlit_paste_button import paste_image_button as pbutton
                st.caption("Copy an image from your device, then click the button below:")
                paste_result = pbutton(
                    label="📋 Click here to Paste Image",
                    background_color="#1565c0",
                    hover_background_color="#0d47a1",
                    errors="raise",
                    key=f"paste_btn_{target_id}"
                )
                if paste_result.image_data is not None:
                    chosen_image = paste_result.image_data
                    st.image(chosen_image, caption="Pasted Image Preview", width=150)
            except Exception:
                st.info("Paste from clipboard component not available.")

        st.divider()
        st.write("🎥 **Product Video File Upload (Hosted on Cloudinary)**")
        vid_file = st.file_uploader("Upload Direct MP4 Video File", type=["mp4", "mov", "webm"], key=f"vid_uploader_{target_id}")

        form_key_suffix = f"_{target_id}"

        with st.form(f"inventory_form{form_key_suffix}"):
            st.info("✏️ **Category & Box Headings**: Type any category name of your choice below.")
            
            default_cat = str(curr_data.get('category', 'General') or 'General')
            sel_category = st.text_input("Product Category", value=default_cat, key=f"form_category{form_key_suffix}").strip().title()

            st.divider()
            ul1, ul2, ul3 = st.columns(3)
            with ul1:
                custom_main_label = st.text_input("Main Unit Name (e.g. Carton)", value=str(curr_data.get('unit_main_label', 'Carton') or 'Carton'), key=f"form_main_label{form_key_suffix}")
            with ul2:
                custom_pack_label = st.text_input("Sub-Unit Name (e.g. Pack)", value=str(curr_data.get('unit_pack_label', 'Pack') or 'Pack'), key=f"form_pack_label{form_key_suffix}")
            with ul3:
                custom_retail_label = st.text_input("Retail Name (e.g. Piece)", value=str(curr_data.get('unit_retail_label', 'Retail Unit') or 'Retail Unit'), key=f"form_retail_label{form_key_suffix}")

            st.divider()

            ca, cb, cc = st.columns(3)
            with ca:
                n_name = st.text_input("Product Name", value=str(curr_data.get('name', '')), key=f"form_prod_name{form_key_suffix}").strip()
                n_cost = st.number_input(f"Cost Price (Per {custom_main_label})", value=float(curr_data.get('cost', 0.0)), key=f"form_cost{form_key_suffix}")
                n_shelf = st.text_input("Shelf Location", value=str(curr_data.get('shelf', '')), key=f"form_shelf{form_key_suffix}")
            with cb:
                n_pc = st.number_input(f"Price (Per {custom_main_label})", value=float(curr_data.get('price_carton', 0.0)), key=f"form_price_carton{form_key_suffix}")
                n_pp = st.number_input(f"Price (Per {custom_pack_label})", value=float(curr_data.get('price_pack', 0.0)), key=f"form_price_pack{form_key_suffix}")
                n_pr = st.number_input(f"Price (Per {custom_retail_label})", value=float(curr_data.get('price_retail', 0.0)), key=f"form_price_retail{form_key_suffix}")
            with cc:
                n_stock = st.number_input(f"Total Stock ({custom_main_label}s)", value=float(curr_data.get('qty_cartons', 0)), key=f"form_qty_cartons{form_key_suffix}")
                n_ppc = st.number_input(f"Count of {custom_pack_label}s in 1 {custom_main_label}", value=int(curr_data.get('packs_per_carton', 1)), min_value=1, key=f"form_packs_per_carton{form_key_suffix}")
                n_upp = st.number_input(f"Count of {custom_retail_label}s in 1 {custom_pack_label}", value=int(curr_data.get('units_per_pack', 1)), min_value=1, key=f"form_units_per_pack{form_key_suffix}")
            
            try:
                default_exp = datetime.strptime(str(curr_data.get('expiry')), '%Y-%m-%d').date()
            except Exception:
                default_exp = date.today()

            n_exp = st.date_input("Expiry Date", value=default_exp, key=f"form_expiry{form_key_suffix}")
            n_video_url = st.text_input("OR YouTube / Cloud Video Link", value=str(curr_data.get('video_url', '') or ''), key=f"form_video_url{form_key_suffix}")
            n_desc = st.text_area("Product Description", value=str(curr_data.get('description', '')), key=f"form_description{form_key_suffix}")
            
            submitted_form = st.form_submit_button("💾 Save Product Data")
            if submitted_form:
                if not n_name:
                    st.error("Product Name is required.")
                elif not sel_category:
                    st.error("Product Category is required.")
                else:
                    def safe_float(val):
                        try:
                            f = float(val)
                            return 0.0 if (pd.isna(f) or f != f or math.isnan(f) or math.isinf(f)) else f
                        except Exception:
                            return 0.0

                    def safe_int(val):
                        try:
                            f = float(val)
                            return 0 if (pd.isna(f) or f != f or math.isnan(f) or math.isinf(f)) else int(f)
                        except Exception:
                            return 0

                    safe_name = str(n_name).encode('utf-8', 'ignore').decode('utf-8').strip()
                    safe_desc = str(n_desc).encode('utf-8', 'ignore').decode('utf-8').strip() if n_desc else ""

                    img_url = upload_image_to_cloudinary(chosen_image) if chosen_image is not None else curr_data.get('img_data')
                    vid_uploaded_url = upload_video_to_cloudinary(vid_file) if vid_file is not None else None
                    
                    final_video_link = vid_uploaded_url if vid_uploaded_url else (n_video_url.strip() if n_video_url else curr_data.get('video_url', ''))

                    raw_payload = {
                        "name": safe_name,
                        "cost": safe_float(n_cost),
                        "price_carton": safe_float(n_pc),
                        "price_pack": safe_float(n_pp),
                        "price_retail": safe_float(n_pr),
                        "qty_cartons": safe_int(n_stock),
                        "packs_per_carton": max(1, safe_int(n_ppc)),
                        "units_per_pack": max(1, safe_int(n_upp)),
                        "shelf": str(n_shelf).strip() if n_shelf else "",
                        "expiry": str(n_exp),
                        "img_data": img_url,
                        "video_url": final_video_link,
                        "description": safe_desc,
                        "category": sel_category,
                        "unit_main_label": custom_main_label.strip() or "Carton",
                        "unit_pack_label": custom_pack_label.strip() or "Pack",
                        "unit_retail_label": custom_retail_label.strip() or "Retail Unit",
                        "timestamp": get_now()
                    }

                    prod_payload = sanitize_payload(raw_payload)
                    
                    try:
                        if action == "Update Existing Item" and target_id != "new":
                            supabase.table("products").update(prod_payload).eq("id", int(target_id)).execute()
                            st.success(f"Updated '{safe_name}' successfully!")
                        else:
                            supabase.table("products").insert(prod_payload).execute()
                            st.success(f"Added '{safe_name}' to inventory!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as save_error:
                        if "duplicate key value" in str(save_error) or "23505" in str(save_error):
                            st.error(f"A product named '{safe_name}' already exists.")
                        else:
                            st.error(f"Database Save Error: {save_error}")

        st.divider()
        if not df_inv.empty:
            st.subheader("🗑️ Delete Unwanted Product")
            with st.expander("⚠️ Click here to delete a product permanently"):
                delete_target = st.selectbox("Select Item to PERMANENTLY Delete", df_inv['name'], key="del_box")
                st.error(f"Warning: Deleting '{delete_target}' cannot be undone!")
                if st.button(f"Confirm Delete: {delete_target}", key="confirm_del_btn"):
                    supabase.table("products").delete().eq("name", delete_target).execute()
                    st.cache_data.clear()
                    st.success(f"'{delete_target}' has been removed.")
                    st.rerun()

    # TAB 3: ORDERS & SPECIAL REQUESTS AUDIT
    with tabs[3]:
        st.header("📋 Consolidated Customer Orders & Multi-Item Custom Requests")
        df_order_list = fetch_dataframe("orders")
        
        st.subheader("✍️ Audit Individual Items in Special Requests")
        if not df_order_list.empty and 'item' in df_order_list.columns:
            df_requests = df_order_list[df_order_list['item'].str.startswith("SPECIAL:", na=False)]
            if not df_requests.empty:
                st.info("Select a customer request below to price and set availability for EACH item individually:")
                
                request_batches = {}
                for (cust, phone, ts), group in df_requests.groupby(['customer', 'contact_phone', 'timestamp']):
                    label = f"Batch Request: {cust} ({phone}) — {len(group)} Item(s) [{ts}]"
                    request_batches[label] = group

                selected_batch_label = st.selectbox("Select Customer Request Batch", list(request_batches.keys()), key="audit_batch_sel")
                selected_group = request_batches[selected_batch_label]

                with st.form("multi_item_audit_form"):
                    st.write(f"### Auditing Request for **{selected_group.iloc[0]['customer']}** ({selected_group.iloc[0]['contact_phone']})")
                    
                    audit_payloads = []
                    grand_batch_total = 0.0

                    for idx, row in selected_group.iterrows():
                        st.markdown(f"---")
                        item_clean_name = str(row['item']).replace("SPECIAL:", "").strip()
                        st.markdown(f"#### Item #{row['id']}: **{item_clean_name}** (Qty Requested: `{row['qty']}`)")
                        
                        ca1, ca2, ca3 = st.columns(3)
                        with ca1:
                            u_price = st.number_input(f"Unit Price for '{item_clean_name}' (₦)", min_value=0.0, value=float(row['total_price']/row['qty']) if row['qty']>0 else 0.0, key=f"u_price_{row['id']}")
                        with ca2:
                            item_total = u_price * float(row['qty'])
                            st.write(f"**Item Total:** ₦{item_total:,.2f}")
                            grand_batch_total += item_total
                        with ca3:
                            is_available = st.selectbox(f"Stock Availability", ["Available", "Unavailable / Out of Stock"], key=f"avail_{row['id']}")

                        audit_payloads.append({
                            "id": int(row['id']),
                            "unit_price": u_price,
                            "item_total": item_total,
                            "status": f"Quoted - {is_available}"
                        })

                    st.markdown("---")
                    st.markdown(f"### 🧮 **Batch Grand Total: ₦{grand_batch_total:,.2f}**")
                    
                    if st.form_submit_button("💾 Send Individual Audited Quotes to Customer Receipt Portfolio"):
                        for payload in audit_payloads:
                            supabase.table("orders").update({
                                "total_price": payload['item_total'],
                                "status": payload['status']
                            }).eq("id", payload['id']).execute()
                        st.success(f"Individual prices & availability quotes updated!")
                        st.rerun()

        st.divider()
        st.subheader("📦 Bulk Order Batch Status Control")
        df_order_list = fetch_dataframe("orders")
        if not df_order_list.empty:
            grouped_orders = []
            batch_mapping = {}
            
            for (cust, phone, ts, date_val), group in df_order_list.groupby(['customer', 'contact_phone', 'timestamp', 'date']):
                order_ids_list = group['id'].astype(int).tolist()
                order_ids_str = ", ".join(map(str, order_ids_list))
                combined_items = ", ".join(group['item'].astype(str).tolist())
                total_sum = group['total_price'].sum() if 'total_price' in group.columns else 0.0
                primary_status = group['status'].iloc[0] if not group['status'].empty else "Pending"
                
                label = f"Batch [{order_ids_str}] — {cust} ({phone}) | Total: ₦{total_sum:,.2f}"
                batch_mapping[label] = {
                    "ids": order_ids_list, "customer": cust, "phone": phone, "timestamp": ts, "date": date_val, "group": group
                }
                
                grouped_orders.append({
                    "Order ID(s)": order_ids_str, "Customer Name": cust, "Phone Number": phone,
                    "Ordered Items": combined_items, "Total Amount (₦)": total_sum, "Status": primary_status, "Date": date_val, "Timestamp": ts
                })
                
            df_grouped = pd.DataFrame(grouped_orders)
            st.dataframe(df_grouped.sort_values('Timestamp', ascending=False), use_container_width=True, hide_index=True)

    # TAB 4: CUSTOMER CHATS
    with tabs[4]:
        st.header("💬 Live Customer Communication")
        try:
            res_msg = supabase.table("messages").select("customer_phone").execute()
            if res_msg.data:
                unique_phones = list(set([m['customer_phone'] for m in res_msg.data]))
                selected_phone = st.selectbox("Select Customer Phone Number to Chat", unique_phones, key="chat_phone_sel")
                
                if selected_phone:
                    st.subheader(f"Chat History with {selected_phone}")
                    chat_data = supabase.table("messages").select("*").eq("customer_phone", selected_phone).order("id").execute()
                    
                    for msg in chat_data.data:
                        role_label = f"👤 {msg['sender']}" if msg['sender'] != "Customer" else "🛍️ Customer"
                        st.markdown(f"**{role_label}** *({msg['timestamp']})*:\n> {msg['message']}")
                    
                    st.divider()
                    with st.form("staff_reply_form", clear_on_submit=True):
                        reply_text = st.text_input("Type your response to the customer...", key="staff_reply_input")
                        if st.form_submit_button("📤 Send Reply"):
                            if reply_text.strip():
                                reply_payload = {
                                    "sender": f"Staff ({user_logged})",
                                    "customer_phone": selected_phone,
                                    "message": reply_text.strip(),
                                    "timestamp": get_now()
                                }
                                supabase.table("messages").insert(reply_payload).execute()
                                st.rerun()
            else:
                st.info("No customer chat threads yet.")
        except Exception as chat_e:
            st.error(f"Chat portal error: {chat_e}")

    # TAB 5: DEBTORS
    with tabs[5]:
        st.header("📓 Debtors Management")
        df_debtors = fetch_dataframe("debtors")
        if not df_debtors.empty:
            st.dataframe(df_debtors, use_container_width=True, hide_index=True)
        st.divider()

        if not df_debtors.empty:
            st.subheader("📝 Update or Clear a Debt")
            col_ed1, col_ed2 = st.columns(2)
            with col_ed1:
                selected_id = st.selectbox("Select Debt ID to Update", df_debtors['id'], key="debt_id_sel")
                debt_to_edit = df_debtors[df_debtors['id'] == selected_id].iloc[0]
            with col_ed2:
                edit_action = st.radio("What do you want to do?", ["Update Amount", "Mark as Fully Paid (Delete)"], key="debt_action_radio")

            if edit_action == "Update Amount":
                with st.form("update_debt_form"):
                    new_amount = st.number_input("New Balance (₦)", value=float(debt_to_edit['amount']), key="new_debt_balance")
                    if st.form_submit_button("Update Balance"):
                        supabase.table("debtors").update({"amount": float(new_amount)}).eq("id", int(selected_id)).execute()
                        st.success("Balance updated!")
                        st.rerun()
            else:
                if st.button(f"🗑️ Confirm: Clear debt for {debt_to_edit['customer']}", key="clear_debt_btn"):
                    supabase.table("debtors").delete().eq("id", int(selected_id)).execute()
                    st.success("Debt cleared!")
                    st.rerun()
        
        st.subheader("➕ Log New Debt")
        with st.form("debt_form"):
            debt_c = st.text_input("Customer Name", key="new_debt_cust")
            debt_p = normalize_phone(st.text_input("Phone", key="new_debt_phone"))
            debt_i = st.text_area("Evidence (Items Bought)", key="new_debt_items")
            debt_a = st.number_input("Amount (₦)", 0.0, key="new_debt_amt")
            if st.form_submit_button("Log New Debt"):
                if debt_c and debt_a > 0:
                    debt_payload = {
                        "customer": debt_c, "amount": float(debt_a), "items_bought": debt_i,
                        "phone": debt_p, "date": date.today().isoformat(), "timestamp": get_now()
                    }
                    supabase.table("debtors").insert(debt_payload).execute()
                    st.success("New debt logged to cloud.")
                    st.rerun()

    # TAB 6: SETTINGS
    with tabs[6]:
        st.header("⚙️ User Settings & Announcements")
        st.subheader("📌 Notice Board Ticker")
        try:
            curr_notice_res = supabase.table("app_settings").select("value").eq("key", "active_notice").execute()
            existing_notice = curr_notice_res.data[0]['value'] if (curr_notice_res.data and len(curr_notice_res.data) > 0) else ""
        except Exception:
            existing_notice = ""

        with st.form("notice_form"):
            notice_input = st.text_area("Notice Message", value=existing_notice, key="settings_notice_input")
            if st.form_submit_button("📢 Publish Notice"):
                chk_notice = supabase.table("app_settings").select("*").eq("key", "active_notice").execute()
                if chk_notice.data:
                    supabase.table("app_settings").update({"value": notice_input.strip()}).eq("key", "active_notice").execute()
                else:
                    supabase.table("app_settings").insert({"key": "active_notice", "value": notice_input.strip()}).execute()
                st.success("Notice updated!")
                st.rerun()

    # CEO MANAGEMENT TABS (RESTORED FULLY)
    if role == "CEO":
        with tabs[7]:
            st.header("💸 Expenditure Log")
            df_exp_view = fetch_dataframe("expenses")
            if not df_exp_view.empty:
                st.dataframe(df_exp_view, use_container_width=True, hide_index=True)
            with st.form("expense_entry"):
                ex_cat = st.selectbox("Category", ["Salaries", "Rent", "Utility", "Stocking", "Fuel", "Other"], key="exp_cat_sel")
                ex_val = st.number_input("Amount", 0.0, key="exp_val_input")
                ex_note = st.text_input("Note", key="exp_note_input")
                if st.form_submit_button("Record Expense"):
                    supabase.table("expenses").insert({"category": ex_cat, "amount": float(ex_val), "note": ex_note, "date": date.today().isoformat(), "timestamp": get_now()}).execute()
                    st.rerun()

        with tabs[8]:
            st.header("👥 Staff Management")
            df_workers = fetch_dataframe("workers")
            if not df_workers.empty:
                st.dataframe(df_workers.drop(columns=['password'], errors='ignore'), use_container_width=True, hide_index=True)
            with st.form("worker_add"):
                w_n = st.text_input("Worker Name", key="worker_name_input")
                w_r = st.selectbox("Role", ["Staff", "CEO"], key="worker_role_sel")
                w_p = st.text_input("Password (Min 6 chars)", type="password", key="worker_pass_input")
                if st.form_submit_button("Create Account"):
                    if len(w_p) >= 6:
                        supabase.table("workers").insert({"name": w_n, "role": w_r, "password": hash_password(w_p)}).execute()
                        st.success("Worker created!")
                        st.rerun()

# ==========================================
# 5. INDEPENDENT CUSTOMER SHOP PORTAL
# ==========================================
else:
    try:
        notice_res = supabase.table("app_settings").select("value").eq("key", "active_notice").execute()
        if notice_res.data and len(notice_res.data) > 0 and notice_res.data[0].get('value'):
            notice_text = notice_res.data[0]['value'].strip()
            if notice_text:
                st.markdown(f"""
                    <div style="background: #1565c0; padding: 14px 20px; border-radius: 10px; color: #ffffff; font-weight: bold; text-align: center; margin-bottom: 15px; font-size: 1.1rem;">
                        📢 {notice_text}
                    </div>
                """, unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1565c0, #0d47a1); padding: 22px; border-radius: 14px; color: white; text-align: center; margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2.1rem;">🏢 Welcome to {store_title}</h1>
            <p style="margin: 6px 0 0 0; font-size: 1.05rem;">Your trusted plug for quality provisions, groceries, and goods!</p>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📱 Quick Navigation (Tap below)")
    c_grid1, c_grid2 = st.columns(2)
    with c_grid1:
        if st.button("🛒 Shop Products & Cart", use_container_width=True, key="nav_shop_btn"):
            st.session_state.cust_active_page = "🛒 Shop & Cart"
            st.rerun()
        if st.button("🔍 Track Order Status", use_container_width=True, key="nav_track_btn"):
            st.session_state.cust_active_page = "🔍 Track Order"
            st.rerun()
        if st.button("💬 Support Chat", use_container_width=True, key="nav_chat_btn"):
            st.session_state.cust_active_page = "💬 Chat with Us"
            st.rerun()

    with c_grid2:
        if st.button("📝 Multi-Item Request", use_container_width=True, key="nav_req_btn"):
            st.session_state.cust_active_page = "📝 Multi-Item Special Request"
            st.rerun()
        if st.button("📜 Transaction History & Receipts", use_container_width=True, key="nav_hist_btn"):
            st.session_state.cust_active_page = "📜 Transaction History"
            st.rerun()

    st.markdown("---")

    cart_count = len(st.session_state.cart)
    cart_total = sum([item['total_price'] for item in st.session_state.cart])

    # PAGE 1: SHOP & CART
    if st.session_state.cust_active_page == "🛒 Shop & Cart":
        st.markdown(f"""
            <div style="background: #e3f2fd; padding: 16px; border-radius: 10px; border: 1px solid #90caf9; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; font-size: 1.1rem;">
                <div>🛒 <b>Shopping Cart:</b> {cart_count} product(s)</div>
                <div><b>Total:</b> ₦{cart_total:,.2f}</div>
            </div>
        """, unsafe_allow_html=True)

        if cart_count > 0:
            with st.expander("🛍️ View Cart & Checkout", expanded=True):
                cart_df = pd.DataFrame(st.session_state.cart)
                st.dataframe(cart_df[['name', 'unit', 'qty', 'total_price']], use_container_width=True, hide_index=True)
                st.markdown(f"### Grand Total: ₦{cart_total:,.2f}")
                
                with st.form("checkout_cart_form"):
                    c_name_cart = st.text_input("Your Full Name", value=st.session_state.active_cust_name, key="chk_name_input")
                    c_phone_cart = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone, key="chk_phone_input"))
                    c_details_cart = st.text_area("📍 Delivery Address & Order Notes", key="chk_address_input")
                    
                    if st.form_submit_button("🚀 Submit Independent Order"):
                        if c_name_cart.strip() and c_phone_cart.strip():
                            st.session_state.active_cust_name = c_name_cart.strip()
                            st.session_state.active_cust_phone = c_phone_cart.strip()
                            checkout_timestamp = get_now()

                            for item in st.session_state.cart:
                                order_payload = {
                                    "customer": c_name_cart.strip(),
                                    "item": f"{item['name']} ({item['unit']})",
                                    "qty": int(item['qty']),
                                    "status": "Order Placed",
                                    "contact_phone": c_phone_cart.strip(),
                                    "total_price": float(item['total_price']),
                                    "date": date.today().isoformat(),
                                    "timestamp": checkout_timestamp
                                }
                                supabase.table("orders").insert(order_payload).execute()
                            
                            st.session_state.cart = []
                            st.session_state.cust_active_page = "📜 Transaction History"
                            st.success("✅ Order submitted successfully!")
                            st.rerun()

        df_shop = fetch_dataframe_cached("products")

        if not df_shop.empty:
            if 'category' not in df_shop.columns:
                df_shop['category'] = 'General'

            categories = ["All Categories"] + sorted(df_shop['category'].dropna().unique().tolist())
            col_filt1, col_filt2 = st.columns([1, 2])
            with col_filt1:
                selected_cat = st.selectbox("📂 Category", categories, key="shop_cat_sel")
            with col_filt2:
                search_query = st.text_input("🔍 Search products...", placeholder="Type product name...", key="shop_search")

            if selected_cat != "All Categories":
                df_shop = df_shop[df_shop['category'] == selected_cat]
            if search_query:
                df_shop = df_shop[df_shop['name'].str.contains(search_query, case=False)]

            if not df_shop.empty:
                st.markdown("---")
                for index, s_row in df_shop.iterrows():
                    with st.container():
                        col_img, col_info, col_order = st.columns([1, 2, 1.5])
                        with col_img:
                            img_url = s_row.get('img_data')
                            if img_url and str(img_url).startswith("http"):
                                st.image(img_url, width=180)
                            else:
                                st.info("No Image")
                        with col_info:
                            st.subheader(s_row['name'])
                            st.caption(f"📂 Category: **{s_row.get('category', 'General')}** | 📍 Shelf: {s_row.get('shelf', 'N/A')}")
                            st.write(s_row.get('description', ''))
                            
                            vid_link = str(s_row.get('video_url', '')).strip()
                            if vid_link and vid_link.lower() not in ["none", "", "nan"]:
                                with st.expander("🎥 Watch Video Advert"):
                                    st.video(vid_link)
                                    
                        with col_order:
                            m_lbl = s_row.get('unit_main_label', 'Carton') or 'Carton'
                            p_lbl = s_row.get('unit_pack_label', 'Pack') or 'Pack'
                            r_lbl = s_row.get('unit_retail_label', 'Retail Unit') or 'Retail Unit'

                            unit_choice = st.selectbox("Select Unit", [r_lbl, p_lbl, m_lbl], key=f"unit_{s_row['id']}")
                            qty_choice = st.number_input("Qty", min_value=1, key=f"qty_{s_row['id']}")
                            
                            price = s_row['price_retail'] if unit_choice == r_lbl else (s_row['price_pack'] if unit_choice == p_lbl else s_row['price_carton'])
                            total_calc = price * qty_choice
                            
                            if st.button(f"➕ Add to Cart — ₦{total_calc:,.2f}", key=f"add_cart_{s_row['id']}", use_container_width=True):
                                st.session_state.cart.append({
                                    "product_id": s_row['id'],
                                    "name": s_row['name'],
                                    "unit": unit_choice,
                                    "qty": int(qty_choice),
                                    "unit_price": float(price),
                                    "total_price": float(total_calc)
                                })
                                st.success(f"Added to cart!")
                                st.rerun()
                        st.divider()
        else:
            st.warning("No products available in stock yet.")

    # PAGE 2: SPECIAL REQUEST
    elif st.session_state.cust_active_page == "📝 Multi-Item Special Request":
        st.subheader("📝 Multi-Item Special Request")
        cust_n = st.text_input("Your Full Name", value=st.session_state.active_cust_name, key="req_cust_name")
        cust_p = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone, key="req_cust_phone"))
        
        for idx, entry in enumerate(st.session_state.request_items_temp):
            c_r1, c_r2 = st.columns([3, 1])
            with c_r1:
                entry['item'] = st.text_input(f"Item #{idx+1} Name", value=entry['item'], key=f"req_item_{idx}")
            with c_r2:
                entry['qty'] = st.number_input(f"Qty", min_value=1, value=entry['qty'], key=f"req_qty_{idx}")
        
        if st.button("➕ Add Item Row", key="add_row_btn"):
            st.session_state.request_items_temp.append({"item": "", "qty": 1})
            st.rerun()

        if st.button("🚀 Submit Independent Special Request", use_container_width=True, key="submit_req_btn"):
            if cust_n.strip() and cust_p.strip():
                batch_timestamp = get_now()
                for e in st.session_state.request_items_temp:
                    if e['item'].strip():
                        supabase.table("orders").insert({
                            "customer": cust_n.strip(),
                            "item": f"SPECIAL: {e['item'].strip()}",
                            "qty": int(e['qty']),
                            "status": "Pending Price Audit",
                            "contact_phone": cust_p.strip(),
                            "total_price": 0.0,
                            "date": date.today().isoformat(),
                            "timestamp": batch_timestamp
                        }).execute()
                st.session_state.request_items_temp = [{"item": "", "qty": 1}]
                st.session_state.cust_active_page = "📜 Transaction History"
                st.success("Special request submitted!")
                st.rerun()

    # PAGE 3: TRACK ORDER
    elif st.session_state.cust_active_page == "🔍 Track Order":
        st.subheader("🔍 Track Order Status")
        track_phone = normalize_phone(st.text_input("Enter Phone Number", value=st.session_state.active_cust_phone, key="track_phone_input"))
        if track_phone.strip():
            res_track = supabase.table("orders").select("id, item, qty, status, total_price, date, timestamp").eq("contact_phone", track_phone.strip()).order("id", desc=True).execute()
            if res_track.data:
                st.dataframe(pd.DataFrame(res_track.data), use_container_width=True, hide_index=True)
            else:
                st.info("No orders found.")

    # PAGE 4: SUPPORT CHAT
    elif st.session_state.cust_active_page == "💬 Chat with Us":
        st.subheader("💬 Support Chat")
        c_phone_chat = normalize_phone(st.text_input("Enter Phone Number", value=st.session_state.active_cust_phone, key="cust_chat_phone"))
        if c_phone_chat.strip():
            chat_res = supabase.table("messages").select("*").eq("customer_phone", c_phone_chat.strip()).order("id").execute()
            for m in chat_res.data:
                st.markdown(f"**{m['sender']}** : {m['message']}")
            with st.form("cust_msg_form", clear_on_submit=True):
                user_msg = st.text_input("Type message...", key="cust_msg_input")
                if st.form_submit_button("Send"):
                    supabase.table("messages").insert({"sender": "Customer", "customer_phone": c_phone_chat.strip(), "message": user_msg, "timestamp": get_now()}).execute()
                    st.rerun()

    # PAGE 5: TRANSACTION HISTORY
    elif st.session_state.cust_active_page == "📜 Transaction History":
        st.subheader("📜 Customer Transaction History")
        history_phone = normalize_phone(st.text_input("Enter Phone Number to load history", value=st.session_state.active_cust_phone, key="hist_phone_input"))
        if history_phone.strip():
            all_cust_orders = supabase.table("orders").select("*").eq("contact_phone", history_phone.strip()).order("timestamp", desc=True).execute()
            if all_cust_orders.data:
                batches = {}
                for ord_row in all_cust_orders.data:
                    t_stamp = ord_row['timestamp']
                    batches.setdefault(t_stamp, []).append(ord_row)
                
                for batch_ts, ord_group in batches.items():
                    b_total = sum([o['total_price'] for o in ord_group])
                    with st.expander(f"📦 Transaction on {batch_ts} — Total: ₦{b_total:,.2f}"):
                        st.dataframe(pd.DataFrame(ord_group)[['item', 'qty', 'status', 'total_price']], use_container_width=True, hide_index=True)

st.sidebar.caption(f"{store_title} v15.0 | {date.today().year}")
