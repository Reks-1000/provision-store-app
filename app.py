import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import base64
from io import BytesIO
from PIL import Image
import math
import hashlib

# ==========================================
# 1. DATABASE SYSTEM & INITIALIZATION (SUPABASE)
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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit() or c == '+').strip()

# AUTO-INITIALIZE SECURE DEFAULT ADMIN USER IF WORKERS TABLE IS EMPTY
try:
    check_empty = supabase.table("workers").select("*").execute()
    if not check_empty.data:
        supabase.table("workers").insert({
            "name": "admin", 
            "role": "CEO", 
            "password": hash_password("Sammyreks2026!")
        }).execute()
except Exception:
    pass

def fetch_dataframe(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 2. CORE UTILITY FUNCTIONS (HD IMAGES & RECEIPTS)
# ==========================================
def get_image_base64(uploaded_file, max_size_mb=2):
    if uploaded_file is not None:
        try:
            if uploaded_file.size > max_size_mb * 1024 * 1024:
                st.error(f"Image file exceeds {max_size_mb}MB limit. Please upload a smaller image.")
                return None
            if isinstance(uploaded_file, Image.Image):
                img = uploaded_file
            else:
                img = Image.open(uploaded_file)
                
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=85, subsampling=0)
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception:
            return None
    return None

def display_image_base64(base64_str):
    if base64_str:
        try:
            return base64.b64decode(base64_str)
        except Exception:
            return None
    return None

def get_file_base64(uploaded_file, max_size_mb=10):
    if uploaded_file is not None:
        try:
            if uploaded_file.size > max_size_mb * 1024 * 1024:
                st.error(f"Video file exceeds {max_size_mb}MB limit.")
                return None
            return base64.b64encode(uploaded_file.read()).decode()
        except Exception:
            return None
    return None

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

store_title = "Sammyreks Business Center"

st.sidebar.title("🏢 Sammyreks Portal")
st.sidebar.markdown("---")

if not st.session_state.auth["logged_in"]:
    auth_mode = st.sidebar.selectbox("Choose Portal", ["🛍️ Customer Shop", "🔑 Staff/Admin Login"])
    
    if auth_mode == "🔑 Staff/Admin Login":
        with st.sidebar.form("login_form"):
            user_input = st.text_input("Username").strip()
            pass_input = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                if not user_input or not pass_input:
                    st.error("Please enter both Username and Password.")
                else:
                    try:
                        hashed_attempt = hash_password(pass_input)
                        # Hardened query matching username case-insensitively and verifying password hash
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
    if st.sidebar.button("Logout"):
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
        try:
            res_pos = supabase.table("products").select("*").execute()
            df_p_pos = pd.DataFrame(res_pos.data) if res_pos.data else pd.DataFrame()
        except Exception:
            df_p_pos = pd.DataFrame()
            
        if not df_p_pos.empty:
            col_pos1, col_pos2 = st.columns([2, 1])
            with col_pos1:
                sel_item = st.selectbox("Search & Select Item", df_p_pos['name'])
                p = df_p_pos[df_p_pos['name'] == sel_item].iloc[0]
                
                m_label = p.get('unit_main_label', 'Carton') or 'Carton'
                p_label = p.get('unit_pack_label', 'Pack') or 'Pack'
                r_label = p.get('unit_retail_label', 'Retail Unit') or 'Retail Unit'
                
                sale_unit = st.radio("Selling Unit", [m_label, p_label, r_label])
                sale_qty = st.number_input("Quantity", min_value=1, value=1)
                c_name_pos = st.text_input("Customer Name")
                c_phone_pos = normalize_phone(st.text_input("Customer Phone Number"))
            with col_pos2:
                up = p['price_carton'] if sale_unit == m_label else (p['price_pack'] if sale_unit == p_label else p['price_retail'])
                grand_total = up * sale_qty
                st.subheader(f"Total: ₦{grand_total:,.2f}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🏁 Cash Sale & Delivery Receipt", use_container_width=True):
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
                    if st.button("📓 Record Debt", use_container_width=True):
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
                                
                            st.warning(f"Debt logged for {c_name_pos}!")
                            st.rerun()

        if st.session_state.last_receipt:
            st.markdown("---")
            rec = st.session_state.last_receipt
            rec_type = rec.get('type', 'Official Receipt')
            sold_items_list = rec.get('sold_items', rec.get('items', []))

            rows_html = "".join([
                f"<tr style='border-bottom:1px solid #e0e0e0;'><td style='padding:10px;'>{itm.get('name','Item')} ({itm.get('unit','Unit')})</td><td style='padding:10px;text-align:center;'>{itm.get('qty',1)}</td><td style='padding:10px;text-align:right;'>₦{itm.get('price',0.0):,.2f}</td><td style='padding:10px;text-align:right;font-weight:bold;'>₦{itm.get('total',0.0):,.2f}</td></tr>"
                for itm in sold_items_list
            ])

            html_code = f"""
            <div style="background:#ffffff;color:#111;padding:24px;border-radius:12px;border:2.5px solid #1565c0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:620px;margin:auto;">
                <div style="text-align:center;"><h2 style="margin:0;color:#1565c0;">🏢 {store_title}</h2><p style="margin:4px 0;color:#555;font-weight:600;">{rec_type}</p></div>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <p style="margin:4px 0;"><b>Customer Name:</b> {rec.get('customer','Walk-in Customer')}</p>
                <p style="margin:4px 0;"><b>Phone Number:</b> {rec.get('phone','N/A')}</p>
                <p style="margin:4px 0;"><b>Date/Time:</b> {rec.get('date','')} | <b>Staff:</b> {rec.get('cashier','Staff')}</p>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                    <thead><tr style="background:#f5f7fa;border-bottom:2px solid #ddd;"><th style="padding:10px;text-align:left;">Item</th><th style="padding:10px;text-align:center;">Qty</th><th style="padding:10px;text-align:right;">Price</th><th style="padding:10px;text-align:right;">Total</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">
                <h3 style="text-align:right;color:#1565c0;margin:10px 0;">Grand Total: ₦{rec.get('grand_total',0.0):,.2f}</h3>
            </div>
            """
            components.html(html_code, height=360 + (len(sold_items_list) * 45), scrolling=True)

            if st.button("❌ Close Receipt View"):
                st.session_state.last_receipt = None
                st.rerun()

    # TAB 2: INVENTORY CONTROL
    with tabs[2]:
        st.header("📦 Stock & Warehouse Control")
        df_inv = fetch_dataframe("products")
        
        if not df_inv.empty:
            st.dataframe(df_inv.drop(columns=['img_data', 'video_data'], errors='ignore'), use_container_width=True, hide_index=True)
        st.divider()
        
        st.subheader("📝 Add / Update Item")
        action = st.radio("Action", ["Add New Item", "Update Existing Item"], horizontal=True)
        
        if action == "Update Existing Item" and not df_inv.empty:
            target = st.selectbox("Select Item to Update", df_inv['name'])
            curr_data = df_inv[df_inv['name'] == target].iloc[0]
        else:
            curr_data = {
                "name": "", "cost": 0.0, "price_carton": 0.0, "price_pack": 0.0, "price_retail": 0.0,
                "qty_cartons": 0, "packs_per_carton": 1, "units_per_pack": 1, "shelf": "",
                "expiry": str(date.today()), "description": "", "img_data": None, "video_url": "", "video_data": None,
                "unit_main_label": "Carton", "unit_pack_label": "Pack", "unit_retail_label": "Retail Unit",
                "category": "General"
            }
        
        st.write("📷 **Product Image Input (Compressed HD Quality, Max 2MB)**")
        img_tab1, img_tab2 = st.tabs(["📁 Upload Image File", "📋 Paste from Clipboard"])
        chosen_image = None

        with img_tab1:
            n_file = st.file_uploader("Choose image file", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
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
                    errors="raise"
                )
                if paste_result.image_data is not None:
                    chosen_image = paste_result.image_data
                    st.image(chosen_image, caption="Pasted Image Preview", width=150)
            except Exception:
                st.info("Paste from clipboard component not available.")

        st.divider()
        st.write("🎥 **Product Video Advert Input (Max 10MB)**")
        vid_file = st.file_uploader("Upload Direct MP4 Video File", type=["mp4", "mov", "webm"])

        with st.form("inventory_form"):
            st.info("✏️ **Category & Box Headings**: Type any category name of your choice below.")
            
            default_cat = str(curr_data.get('category', 'General') or 'General')
            sel_category = st.text_input("Product Category (Type any category e.g. Cosmetics, Drinks, Books, etc.)", value=default_cat).strip().title()

            st.divider()
            ul1, ul2, ul3 = st.columns(3)
            with ul1:
                custom_main_label = st.text_input("Main Unit Name (e.g. Carton, Box)", value=str(curr_data.get('unit_main_label', 'Carton') or 'Carton'))
            with ul2:
                custom_pack_label = st.text_input("Sub-Unit Name (e.g. Pack, Bundle)", value=str(curr_data.get('unit_pack_label', 'Pack') or 'Pack'))
            with ul3:
                custom_retail_label = st.text_input("Retail Name (e.g. Piece, Bottle)", value=str(curr_data.get('unit_retail_label', 'Retail Unit') or 'Retail Unit'))

            st.divider()

            ca, cb, cc = st.columns(3)
            with ca:
                n_name = st.text_input("Product Name", value=str(curr_data['name'])).strip()
                n_cost = st.number_input(f"Cost Price (Per {custom_main_label})", value=float(curr_data.get('cost', 0.0)))
                n_shelf = st.text_input("Shelf Location", value=str(curr_data.get('shelf', '')))
            with cb:
                n_pc = st.number_input(f"Price (Per {custom_main_label})", value=float(curr_data.get('price_carton', 0.0)))
                n_pp = st.number_input(f"Price (Per {custom_pack_label})", value=float(curr_data.get('price_pack', 0.0)))
                n_pr = st.number_input(f"Price (Per {custom_retail_label})", value=float(curr_data.get('price_retail', 0.0)))
            with cc:
                n_stock = st.number_input(f"Total Stock ({custom_main_label}s)", value=float(curr_data.get('qty_cartons', 0)))
                n_ppc = st.number_input(f"Count of {custom_pack_label}s in 1 {custom_main_label}", value=int(curr_data.get('packs_per_carton', 1)), min_value=1)
                n_upp = st.number_input(f"Count of {custom_retail_label}s in 1 {custom_pack_label}", value=int(curr_data.get('units_per_pack', 1)), min_value=1)
            
            try:
                default_exp = datetime.strptime(str(curr_data.get('expiry')), '%Y-%m-%d').date()
            except Exception:
                default_exp = date.today()

            n_exp = st.date_input("Expiry Date", value=default_exp)
            n_video_url = st.text_input("OR Video Web Link (YouTube / Vimeo / Cloud Link)", value=str(curr_data.get('video_url', '') or ''))
            n_desc = st.text_area("Product Description", value=str(curr_data.get('description', '')))
            
            if st.form_submit_button("💾 Save Product Data"):
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

                    img_encoded = get_image_base64(chosen_image) if chosen_image else curr_data.get('img_data')
                    video_encoded = get_file_base64(vid_file) if vid_file else curr_data.get('video_data')
                    
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
                        "img_data": img_encoded,
                        "video_data": video_encoded,
                        "video_url": str(n_video_url).strip() if n_video_url else "",
                        "description": safe_desc,
                        "category": sel_category,
                        "unit_main_label": custom_main_label.strip() or "Carton",
                        "unit_pack_label": custom_pack_label.strip() or "Pack",
                        "unit_retail_label": custom_retail_label.strip() or "Retail Unit",
                        "timestamp": get_now()
                    }

                    prod_payload = sanitize_payload(raw_payload)
                    
                    try:
                        if action == "Update Existing Item" and 'id' in curr_data:
                            supabase.table("products").update(prod_payload).eq("id", int(curr_data['id'])).execute()
                            st.success(f"Updated '{safe_name}' successfully!")
                        else:
                            supabase.table("products").insert(prod_payload).execute()
                            st.success(f"Added '{safe_name}' to inventory!")
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
                if st.button(f"Confirm Delete: {delete_target}"):
                    supabase.table("products").delete().eq("name", delete_target).execute()
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

                selected_batch_label = st.selectbox("Select Customer Request Batch", list(request_batches.keys()))
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
                        st.success(f"Individual prices & availability quotes updated for customer receipt portfolio!")
                        st.rerun()
            else:
                st.caption("No pending special requests found requiring itemized price audit.")

        st.divider()

        st.subheader("📦 All Orders Log & Status Control")
        if not df_order_list.empty:
            grouped_orders = []
            for (cust, phone, ts, status, date_val), group in df_order_list.groupby(['customer', 'contact_phone', 'timestamp', 'status', 'date']):
                combined_items = ", ".join(group['item'].astype(str).tolist())
                order_ids = ", ".join(group['id'].astype(str).tolist()) if 'id' in group.columns else "N/A"
                total_sum = group['total_price'].sum() if 'total_price' in group.columns else 0.0
                grouped_orders.append({
                    "Order ID(s)": order_ids,
                    "Customer Name": cust,
                    "Phone Number": phone,
                    "Ordered Items": combined_items,
                    "Total Amount (₦)": total_sum,
                    "Status": status,
                    "Date": date_val,
                    "Timestamp": ts
                })
            df_grouped = pd.DataFrame(grouped_orders)
            st.dataframe(df_grouped.sort_values('Timestamp', ascending=False), use_container_width=True, hide_index=True)
            
            st.divider()

            with st.expander("✏️ Select Order to Respond, Update Status or Cancel", expanded=True):
                order_options = {}
                for _, row in df_order_list.iterrows():
                    o_id = int(row['id'])
                    o_cust = row.get('customer', 'Unknown')
                    o_item = row.get('item', 'Item')
                    o_status = row.get('status', 'Pending')
                    label = f"Order #{o_id} — {o_cust} | {o_item} (Current: {o_status})"
                    order_options[label] = o_id

                selected_label = st.selectbox("Select Customer Order", list(order_options.keys()))
                target_order_id = order_options[selected_label]
                
                new_st = st.selectbox("Update Status To:", ["Pending", "In Progress", "Ready", "Delivered", "Cancelled"])
                
                col_up1, col_up2 = st.columns(2)
                with col_up1:
                    if st.button("🔄 Apply Status Change", use_container_width=True):
                        supabase.table("orders").update({"status": new_st}).eq("id", target_order_id).execute()
                        st.success(f"Order #{target_order_id} updated to '{new_st}'!")
                        st.rerun()
                with col_up2:
                    if st.button("❌ Quick Cancel (No Receipt Generated)", use_container_width=True):
                        supabase.table("orders").update({"status": "Cancelled"}).eq("id", target_order_id).execute()
                        st.warning(f"Order #{target_order_id} has been Cancelled. No receipt generated.")
                        st.rerun()
        else:
            st.info("No customer orders found yet.")

    # TAB 4: CUSTOMER CHATS
    with tabs[4]:
        st.header("💬 Live Customer Communication")
        try:
            res_msg = supabase.table("messages").select("customer_phone").execute()
            if res_msg.data:
                unique_phones = list(set([m['customer_phone'] for m in res_msg.data]))
                selected_phone = st.selectbox("Select Customer Phone Number to Chat", unique_phones)
                
                if selected_phone:
                    st.subheader(f"Chat History with {selected_phone}")
                    chat_data = supabase.table("messages").select("*").eq("customer_phone", selected_phone).order("id").execute()
                    
                    for msg in chat_data.data:
                        role_label = f"👤 {msg['sender']}" if msg['sender'] != "Customer" else "🛍️ Customer"
                        st.markdown(f"**{role_label}** *({msg['timestamp']})*:\n> {msg['message']}")
                    
                    st.divider()
                    with st.form("staff_reply_form", clear_on_submit=True):
                        reply_text = st.text_input("Type your response to the customer...")
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
                selected_id = st.selectbox("Select Debt ID to Update", df_debtors['id'])
                debt_to_edit = df_debtors[df_debtors['id'] == selected_id].iloc[0]
            with col_ed2:
                edit_action = st.radio("What do you want to do?", ["Update Amount", "Mark as Fully Paid (Delete)"])

            if edit_action == "Update Amount":
                with st.form("update_debt_form"):
                    new_amount = st.number_input("New Balance (₦)", value=float(debt_to_edit['amount']))
                    if st.form_submit_button("Update Balance"):
                        supabase.table("debtors").update({"amount": float(new_amount)}).eq("id", int(selected_id)).execute()
                        st.success("Balance updated!")
                        st.rerun()
            else:
                if st.button(f"🗑️ Confirm: Clear all debt for {debt_to_edit['customer']}"):
                    supabase.table("debtors").delete().eq("id", int(selected_id)).execute()
                    st.success("Debt cleared!")
                    st.rerun()
        
        st.subheader("➕ Log New Debt")
        with st.form("debt_form"):
            debt_c = st.text_input("Customer Name")
            debt_p = normalize_phone(st.text_input("Phone"))
            debt_i = st.text_area("Evidence (Items Bought)")
            debt_a = st.number_input("Amount (₦)", 0.0)
            if st.form_submit_button("Log New Debt"):
                if debt_c and debt_a > 0:
                    debt_payload = {
                        "customer": debt_c, "amount": float(debt_a), "items_bought": debt_i,
                        "phone": debt_p, "date": date.today().isoformat(), "timestamp": get_now()
                    }
                    supabase.table("debtors").insert(debt_payload).execute()
                    st.success("New debt logged to cloud.")
                    st.rerun()
                else:
                    st.error("Name and Amount are required.")

    # TAB 6: SETTINGS
    with tabs[6]:
        st.header("⚙️ User Settings & Announcements")
        
        st.subheader("📌 Notice Board / Announcement Ticker")
        st.caption("Type a notice (e.g. Sunday greetings, Christmas wishes, brand updates) to display on the customer app.")
        
        try:
            curr_notice_res = supabase.table("app_settings").select("value").eq("key", "active_notice").execute()
            existing_notice = curr_notice_res.data[0]['value'] if (curr_notice_res.data and len(curr_notice_res.data) > 0) else ""
        except Exception:
            existing_notice = ""

        with st.form("notice_form"):
            notice_input = st.text_area("Notice Message (Leave blank to remove notice)", value=existing_notice)
            if st.form_submit_button("📢 Publish / Update Notice"):
                try:
                    chk_notice = supabase.table("app_settings").select("*").eq("key", "active_notice").execute()
                    if chk_notice.data:
                        supabase.table("app_settings").update({"value": notice_input.strip()}).eq("key", "active_notice").execute()
                    else:
                        supabase.table("app_settings").insert({"key": "active_notice", "value": notice_input.strip()}).execute()
                    st.success("Notice board updated successfully!")
                    st.rerun()
                except Exception as ne:
                    st.error(f"Failed to update notice: {ne}")

        st.divider()

        st.subheader("📢 General Awareness / Advert Video")
        st.caption("Upload or update the general video displayed at the top of the customer portal.")
        
        gen_vid_file = st.file_uploader("Upload General Advert MP4 Video", type=["mp4", "mov", "webm"], key="gen_vid_upload")
        
        if gen_vid_file:
            if st.button("💾 Save General Advert Video"):
                try:
                    vid_encoded = get_file_base64(gen_vid_file)
                    if vid_encoded:
                        chk_setting = supabase.table("app_settings").select("*").eq("key", "general_video").execute()
                        if chk_setting.data:
                            supabase.table("app_settings").update({"value": vid_encoded}).eq("key", "general_video").execute()
                        else:
                            supabase.table("app_settings").insert({"key": "general_video", "value": vid_encoded}).execute()
                        st.success("General awareness video updated successfully!")
                        st.rerun()
                except Exception as ex:
                    st.error(f"Failed to save video: {ex}")

        st.divider()
        st.subheader("Change Your Password")
        with st.form("change_pass_form"):
            old_p = st.text_input("Current Password", type="password")
            new_p = st.text_input("New Password", type="password")
            confirm_p = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Password"):
                verify = supabase.table("workers").select("*").ilike("name", user_logged).eq("password", hash_password(old_p)).execute()
                if not verify.data:
                    st.error("Current password is incorrect.")
                elif new_p != confirm_p:
                    st.error("New passwords do not match.")
                elif len(new_p) < 6:
                    st.error("Password too short (minimum 6 characters).")
                else:
                    supabase.table("workers").update({"password": hash_password(new_p)}).ilike("name", user_logged).execute()
                    st.success("Password updated securely in cloud database!")

    # CEO TABS
    if role == "CEO":
        with tabs[7]:
            st.header("💸 Expenditure Log")
            df_exp_view = fetch_dataframe("expenses")
            if not df_exp_view.empty:
                st.dataframe(df_exp_view, use_container_width=True, hide_index=True)
            with st.form("expense_entry"):
                ex_cat = st.selectbox("Category", ["Salaries", "Rent", "Utility", "Stocking", "Fuel", "Other"])
                ex_val = st.number_input("Amount", 0.0)
                ex_note = st.text_input("Note")
                if st.form_submit_button("Record Expense"):
                    exp_payload = {"category": ex_cat, "amount": float(ex_val), "note": ex_note, "date": date.today().isoformat(), "timestamp": get_now()}
                    supabase.table("expenses").insert(exp_payload).execute()
                    st.rerun()

        with tabs[8]:
            st.header("👥 Staff Management")
            df_workers = fetch_dataframe("workers")
            if not df_workers.empty:
                st.dataframe(df_workers.drop(columns=['password'], errors='ignore'), use_container_width=True, hide_index=True)
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.subheader("Add New Worker")
                with st.form("worker_add"):
                    w_n = st.text_input("Worker Name")
                    w_r = st.selectbox("Role", ["Staff", "CEO"])
                    w_p = st.text_input("Set Password (Min 6 chars)", type="password")
                    if st.form_submit_button("Create Account"):
                        try:
                            if len(w_p) < 6:
                                st.error("Password must be at least 6 characters.")
                            else:
                                supabase.table("workers").insert({"name": w_n, "role": w_r, "password": hash_password(w_p)}).execute()
                                st.success("Worker created successfully!")
                                st.rerun()
                        except Exception:
                            st.error("Worker exists or entry error.")
            with col_w2:
                st.subheader("Reset Worker Password")
                with st.form("worker_reset"):
                    target_worker = st.selectbox("Select Worker", df_workers['name']) if not df_workers.empty else st.selectbox("Select Worker", ["None"])
                    new_reset_p = st.text_input("New Temporary Password", type="password")
                    if st.form_submit_button("Reset Password"):
                        if len(new_reset_p) < 6:
                            st.error("Password must be at least 6 characters.")
                        else:
                            supabase.table("workers").update({"password": hash_password(new_reset_p)}).ilike("name", target_worker).execute()
                            st.success("Password reset successfully.")

# ==========================================
# 5. MOBILE-FRIENDLY CUSTOMER PORTAL
# ==========================================
else:
    # 1. NOTICE BOARD
    try:
        notice_res = supabase.table("app_settings").select("value").eq("key", "active_notice").execute()
        if notice_res.data and len(notice_res.data) > 0 and notice_res.data[0].get('value'):
            notice_text = notice_res.data[0]['value'].strip()
            if notice_text:
                st.markdown(f"""
                    <div style="background: #1565c0; padding: 14px 20px; border-radius: 10px; color: #ffffff; font-weight: bold; text-align: center; margin-bottom: 15px; font-size: 1.1rem; box-shadow: 0 2px 5px rgba(0,0,0,0.15);">
                        📢 {notice_text}
                    </div>
                """, unsafe_allow_html=True)
    except Exception:
        pass

    # 2. GENERAL AWARENESS VIDEO BOX
    try:
        set_res = supabase.table("app_settings").select("value").eq("key", "general_video").execute()
        if set_res.data and len(set_res.data) > 0 and set_res.data[0].get('value'):
            gen_vid_b64 = set_res.data[0]['value']
            vid_bytes_gen = base64.b64decode(gen_vid_b64)
            st.video(vid_bytes_gen)
    except Exception:
        pass

    # 3. GREEN WELCOME BANNER
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1565c0, #0d47a1); padding: 22px; border-radius: 14px; color: white; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(21,101,192,0.35);">
            <h1 style="margin: 0; font-size: 2.1rem;">🏢 Welcome to {store_title}</h1>
            <p style="margin: 6px 0 0 0; font-size: 1.05rem; opacity: 0.95;">Your trusted plug for raw food, beverages, books, and premium provisions!</p>
        </div>
    """, unsafe_allow_html=True)

    # 4. ALWAYS-VISIBLE PROMINENT MOBILE ICON GRID NAVIGATION
    st.markdown("### 📱 Quick Navigation (Tap below)")
    c_grid1, c_grid2 = st.columns(2)
    with c_grid1:
        if st.button("🛒 Shop Products & Cart", use_container_width=True):
            st.session_state.cust_active_page = "🛒 Shop & Cart"
            st.rerun()
        if st.button("🔍 Track Order Status", use_container_width=True):
            st.session_state.cust_active_page = "🔍 Track Order"
            st.rerun()
        if st.button("💬 Support Chat", use_container_width=True):
            st.session_state.cust_active_page = "💬 Chat with Us"
            st.rerun()

    with c_grid2:
        if st.button("📝 Multi-Item Request", use_container_width=True):
            st.session_state.cust_active_page = "📝 Multi-Item Special Request"
            st.rerun()
        if st.button("🧾 Receipt Portfolio", use_container_width=True):
            st.session_state.cust_active_page = "🧾 Receipt Portfolio"
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
            with st.expander("🛍️ View Cart & Checkout All Items", expanded=True):
                cart_df = pd.DataFrame(st.session_state.cart)
                st.dataframe(cart_df[['name', 'unit', 'qty', 'total_price']], use_container_width=True, hide_index=True)
                st.markdown(f"### Grand Total: ₦{cart_total:,.2f}")
                
                with st.form("checkout_cart_form"):
                    c_name_cart = st.text_input("Your Full Name", value=st.session_state.active_cust_name)
                    c_phone_cart = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone))
                    c_details_cart = st.text_area("📍 Delivery Address & Order Notes", placeholder="Include street address, nearest landmark, delivery preferences, or special instructions...")
                    
                    checkout_btn = st.form_submit_button("🚀 Checkout & Generate Receipt")
                    
                    if checkout_btn:
                        if c_name_cart.strip() and c_phone_cart.strip():
                            st.session_state.active_cust_name = c_name_cart.strip()
                            st.session_state.active_cust_phone = c_phone_cart.strip()

                            receipt_items = []
                            for item in st.session_state.cart:
                                order_payload = {
                                    "customer": c_name_cart.strip(),
                                    "item": f"{item['name']} ({item['unit']})",
                                    "qty": int(item['qty']),
                                    "status": "Pending",
                                    "contact_phone": c_phone_cart.strip(),
                                    "total_price": float(item['total_price']),
                                    "date": date.today().isoformat(),
                                    "timestamp": get_now()
                                }
                                supabase.table("orders").insert(order_payload).execute()
                                receipt_items.append({
                                    "name": item['name'], "unit": item['unit'], 
                                    "qty": item['qty'], "price": item['unit_price'], "total": item['total_price'],
                                    "item_status": "Available"
                                })
                            
                            st.session_state.last_receipt = {
                                "type": "Initial Customer Order Receipt", 
                                "customer": c_name_cart.strip(),
                                "phone": c_phone_cart.strip(), 
                                "delivery_notes": c_details_cart.strip(),
                                "date": get_now(),
                                "sold_items": receipt_items, 
                                "grand_total": cart_total, 
                                "status": "Pending"
                            }
                            st.session_state.cart = []
                            st.session_state.cust_active_page = "🧾 Receipt Portfolio"
                            st.success("✅ Order placed successfully! Delivery details saved.")
                            st.rerun()
                        else:
                            st.error("Please enter both Name and Phone Number.")
                
                if st.button("🗑️ Clear Cart"):
                    st.session_state.cart = []
                    st.rerun()

        try:
            res_shop = supabase.table("products").select("*").execute()
            df_shop = pd.DataFrame(res_shop.data) if res_shop.data else pd.DataFrame()
        except Exception:
            df_shop = pd.DataFrame()

        if not df_shop.empty:
            if 'category' not in df_shop.columns:
                df_shop['category'] = 'General'

            categories = ["All Categories"] + sorted(df_shop['category'].dropna().unique().tolist())
            
            col_filt1, col_filt2 = st.columns([1, 2])
            with col_filt1:
                selected_cat = st.selectbox("📂 Category", categories)
            with col_filt2:
                search_query = st.text_input("🔍 Search products...", placeholder="Type product name...")

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
                            img_bytes = display_image_base64(s_row.get('img_data'))
                            if img_bytes:
                                st.image(img_bytes, width=180)
                            else:
                                st.info("No Image")
                        with col_info:
                            st.subheader(s_row['name'])
                            st.caption(f"📂 Category: **{s_row.get('category', 'General')}** | 📍 Shelf: {s_row.get('shelf', 'N/A')}")
                            st.write(s_row.get('description', ''))
                            
                            has_direct_vid = s_row.get('video_data') and str(s_row['video_data']).strip() not in ["None", "", "nan"]
                            has_url_vid = s_row.get('video_url') and str(s_row['video_url']).strip() not in ["None", "", "nan"]

                            if has_direct_vid or has_url_vid:
                                with st.expander("🎥 Watch Video Advert"):
                                    if has_direct_vid:
                                        try:
                                            vid_bytes = base64.b64decode(s_row['video_data'])
                                            st.video(vid_bytes)
                                        except Exception:
                                            st.error("Video file error.")
                                    elif has_url_vid:
                                        st.video(s_row['video_url'])
                                    
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
                                st.success(f"Added {qty_choice} {unit_choice}(s) of {s_row['name']} to cart!")
                                st.rerun()
                        st.divider()
            else:
                st.warning("No products matching filter.")
        else:
            st.warning("No products available in stock yet.")

    # PAGE 2: MULTI-ITEM SPECIAL REQUEST
    elif st.session_state.cust_active_page == "📝 Multi-Item Special Request":
        st.subheader("📝 Multi-Item Special Request")
        st.caption("Enter each item name and quantity separately below:")
        
        cust_n = st.text_input("Your Full Name", value=st.session_state.active_cust_name, key="req_name_input")
        cust_p = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone, key="req_phone_input"))
        c_details_req = st.text_area("📍 Delivery Address & General Notes", placeholder="Describe landmark, delivery area, or special notes...", key="req_details_input")

        st.markdown("---")
        st.markdown("#### 🛒 Requested Items List")
        
        for idx, entry in enumerate(st.session_state.request_items_temp):
            c_r1, c_r2 = st.columns([3, 1])
            with c_r1:
                entry['item'] = st.text_input(f"Item #{idx+1} Name", value=entry['item'], key=f"req_item_{idx}")
            with c_r2:
                entry['qty'] = st.number_input(f"Qty", min_value=1, value=entry['qty'], key=f"req_qty_{idx}")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            if st.button("➕ Add Item Row", use_container_width=True):
                st.session_state.request_items_temp.append({"item": "", "qty": 1})
                st.rerun()
        with col_m2:
            if len(st.session_state.request_items_temp) > 1:
                if st.button("➖ Remove Row", use_container_width=True):
                    st.session_state.request_items_temp.pop()
                    st.rerun()

        st.markdown("---")
        if st.button("🚀 Submit Multi-Item Special Request Batch", use_container_width=True):
            if cust_n.strip() and cust_p.strip():
                st.session_state.active_cust_name = cust_n.strip()
                st.session_state.active_cust_phone = cust_p.strip()

                valid_entries = [e for e in st.session_state.request_items_temp if e['item'].strip()]
                if valid_entries:
                    batch_timestamp = get_now()
                    receipt_items = []
                    for e in valid_entries:
                        order_payload = {
                            "customer": cust_n.strip(),
                            "item": f"SPECIAL: {e['item'].strip()}",
                            "qty": int(e['qty']),
                            "status": "Pending Price Audit",
                            "contact_phone": cust_p.strip(),
                            "total_price": 0.0,
                            "date": date.today().isoformat(),
                            "timestamp": batch_timestamp
                        }
                        supabase.table("orders").insert(order_payload).execute()
                        receipt_items.append({
                            "name": f"SPECIAL: {e['item'].strip()}",
                            "unit": "Request",
                            "qty": int(e['qty']),
                            "price": 0.0,
                            "total": 0.0,
                            "item_status": "Pending Price Audit"
                        })
                    
                    st.session_state.last_receipt = {
                        "type": "Initial Custom Request Log Receipt",
                        "customer": cust_n.strip(),
                        "phone": cust_p.strip(),
                        "delivery_notes": c_details_req.strip(),
                        "date": batch_timestamp,
                        "sold_items": receipt_items,
                        "grand_total": 0.0,
                        "status": "Pending Admin Price Audit"
                    }
                    st.session_state.request_items_temp = [{"item": "", "qty": 1}]
                    st.session_state.cust_active_page = "🧾 Receipt Portfolio"
                    st.success("✅ Multi-item request submitted! Admin is auditing prices now.")
                    st.rerun()
                else:
                    st.error("Please enter at least one valid item name.")
            else:
                st.error("Please fill in your Name and Phone Number.")

    # PAGE 3: TRACK ORDER
    elif st.session_state.cust_active_page == "🔍 Track Order":
        st.subheader("🔍 Track Order Status")
        track_phone = normalize_phone(st.text_input("Enter your Phone Number to check status", value=st.session_state.active_cust_phone))
        if track_phone.strip():
            st.session_state.active_cust_phone = track_phone.strip()
            try:
                res_track = supabase.table("orders").select("item, qty, status, total_price, date").eq("contact_phone", track_phone.strip()).execute()
                if res_track.data:
                    st.dataframe(pd.DataFrame(res_track.data), use_container_width=True, hide_index=True)
                else:
                    st.info("No orders found for this number.")
            except Exception:
                pass

    # PAGE 4: SUPPORT CHAT
    elif st.session_state.cust_active_page == "💬 Chat with Us":
        st.subheader("💬 Support Chat")
        c_phone_chat = normalize_phone(st.text_input("Enter your Phone Number to start chatting", value=st.session_state.active_cust_phone, key="cust_chat_phone"))
        
        if c_phone_chat.strip():
            st.session_state.active_cust_phone = c_phone_chat.strip()
            try:
                chat_res = supabase.table("messages").select("*").eq("customer_phone", c_phone_chat.strip()).order("id").execute()
                if chat_res.data:
                    for m in chat_res.data:
                        sender_tag = "🛍️ You" if m['sender'] == "Customer" else f"👤 {m['sender']}"
                        st.markdown(f"**{sender_tag}** *({m['timestamp']})*:\n> {m['message']}")
                else:
                    st.info("No previous messages found. Send your first message below!")

                st.divider()
                with st.form("cust_msg_form", clear_on_submit=True):
                    user_msg = st.text_input("Type your message here...")
                    if st.form_submit_button("📤 Send Message"):
                        if user_msg.strip():
                            msg_payload = {
                                "sender": "Customer",
                                "customer_phone": c_phone_chat.strip(),
                                "message": user_msg.strip(),
                                "timestamp": get_now()
                            }
                            supabase.table("messages").insert(msg_payload).execute()
                            st.rerun()
            except Exception as e:
                st.error(f"Chat connection error: {e}")
        else:
            st.warning("Please enter your phone number to load or start a chat thread.")

    # PAGE 5: RECEIPT PORTFOLIO
    elif st.session_state.cust_active_page == "🧾 Receipt Portfolio":
        st.subheader("🧾 Receipt Portfolio & Active Status")
        lookup_phone = normalize_phone(st.text_input("Enter your Phone Number to load your Portfolio Receipt", value=st.session_state.active_cust_phone))
        
        active_rec = None
        available_order_ids = []
        
        if lookup_phone.strip():
            st.session_state.active_cust_phone = lookup_phone.strip()
            try:
                cust_orders_res = supabase.table("orders").select("*").eq("contact_phone", lookup_phone.strip()).order("id", desc=True).execute()
                if cust_orders_res.data:
                    latest_ts = cust_orders_res.data[0]['timestamp']
                    batch_orders = [o for o in cust_orders_res.data if o['timestamp'] == latest_ts]
                    
                    c_name = batch_orders[0]['customer']
                    c_date = batch_orders[0]['date']
                    
                    items_list = []
                    total_sum = 0.0
                    has_quoted = False
                    
                    for bo in batch_orders:
                        st_item = bo['status']
                        if "Available" in st_item and "Unavailable" not in st_item:
                            available_order_ids.append(int(bo['id']))
                            
                        if "Quoted" in st_item:
                            has_quoted = True

                        items_list.append({
                            "id": bo['id'],
                            "name": str(bo['item']).replace("SPECIAL:", "").strip(),
                            "qty": bo['qty'],
                            "price": bo['total_price'] / bo['qty'] if bo['qty'] > 0 else 0.0,
                            "total": bo['total_price'],
                            "item_status": st_item
                        })
                        total_sum += bo['total_price']
                    
                    first_st = batch_orders[0]['status']
                    if first_st == "Delivered":
                        rec_title = "Successful Delivery Receipt"
                    elif has_quoted:
                        rec_title = "Quoted & Audited Receipt (Available vs Out of Stock)"
                    else:
                        rec_title = "Initial Customer Request Log Receipt"

                    if first_st != "Cancelled":
                        active_rec = {
                            "type": rec_title,
                            "customer": c_name,
                            "phone": lookup_phone.strip(),
                            "date": c_date,
                            "sold_items": items_list,
                            "grand_total": total_sum,
                            "status": first_st
                        }
            except Exception:
                pass
        
        if not active_rec and st.session_state.last_receipt:
            active_rec = st.session_state.last_receipt

        if active_rec:
            rec_type = active_rec.get('type', 'Customer Order Receipt')
            sold_items_list = active_rec.get('sold_items', [])
            delivery_notes = active_rec.get('delivery_notes', '')
            
            notes_html = f"<p style='margin: 4px 0;'><b>Delivery Location / Notes:</b> {delivery_notes}</p>" if delivery_notes else ""
            
            rows_html = ""
            for itm in sold_items_list:
                i_name = itm.get('name', 'Item')
                i_qty = itm.get('qty', 1)
                i_price = f"₦{itm.get('price', 0.0):,.2f}" if itm.get('price', 0.0) > 0 else "Pending"
                i_total = f"₦{itm.get('total', 0.0):,.2f}" if itm.get('total', 0.0) > 0 else "Pending"
                i_st = itm.get('item_status', 'Pending Audit')
                
                status_color = "#2e7d32" if "Available" in i_st and "Unavailable" not in i_st else ("#c62828" if "Unavailable" in i_st else "#f57c00")
                
                rows_html += f"""
                <tr style="border-bottom: 1px solid #e0e0e0;">
                    <td style="padding: 10px; font-weight: 500;">{i_name}</td>
                    <td style="padding: 10px; text-align: center;">{i_qty}</td>
                    <td style="padding: 10px; text-align: right;">{i_price}</td>
                    <td style="padding: 10px; text-align: right; font-weight: bold;">{i_total}</td>
                    <td style="padding: 10px; text-align: center; color: {status_color}; font-weight: bold;">{i_st}</td>
                </tr>
                """

            tot_str = f"₦{active_rec.get('grand_total', 0.0):,.2f}" if active_rec.get('grand_total', 0.0) > 0 else "Pending Price Audit"

            full_receipt_html = f"""
            <div style="background: #ffffff; color: #111; padding: 24px; border-radius: 12px; border: 2.5px solid #1565c0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 620px; margin: 0 auto; box-shadow: 0 4px 15px rgba(0,0,0,0.08);">
                <div style="text-align: center;">
                    <h2 style="margin: 0; color: #1565c0; font-size: 1.6rem;">🏢 {store_title}</h2>
                    <p style="margin: 4px 0 0 0; color: #555; font-weight: 600;">{rec_type}</p>
                </div>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <div style="font-size: 0.95rem; line-height: 1.6;">
                    <p style="margin: 4px 0;"><b>Customer Name:</b> {active_rec.get('customer', 'Customer')}</p>
                    <p style="margin: 4px 0;"><b>Phone Number:</b> {active_rec.get('phone', 'N/A')}</p>
                    {notes_html}
                </div>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                        <thead>
                            <tr style="background-color: #f5f7fa; border-bottom: 2px solid #ddd;">
                                <th style="padding: 10px; text-align: left;">Item Description</th>
                                <th style="padding: 10px; text-align: center;">Qty</th>
                                <th style="padding: 10px; text-align: right;">Price</th>
                                <th style="padding: 10px; text-align: right;">Total</th>
                                <th style="padding: 10px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
                <h3 style="text-align: right; color: #1565c0; margin: 10px 0;">Total: {tot_str}</h3>
                <p style="text-align: center; color: #666; font-size: 0.82rem; margin-top: 18px;">
                    Thank you for shopping with Sammyreks Business Center!<br>
                    <i>This portfolio automatically updates item-by-item prices and availability status.</i>
                </p>
            </div>
            """
            
            calc_height = 420 + (len(sold_items_list) * 45) + (60 if delivery_notes else 0)
            components.html(full_receipt_html, height=calc_height, scrolling=True)

            if available_order_ids:
                st.markdown("---")
                if st.button("🚀 Confirm & Place Final Order for Available Items Only", use_container_width=True):
                    for oid in available_order_ids:
                        supabase.table("orders").update({"status": "Order Placed & Confirmed"}).eq("id", oid).execute()
                    st.success("✅ Order confirmed for available items! We are preparing your delivery.")
                    st.rerun()

            st.success("💡 Every new order or custom request automatically updates and replaces this portfolio receipt view!")
        else:
            st.info("Enter your phone number above or submit a request to load your active order portfolio receipt.")

st.sidebar.caption(f"{store_title} v11.0 | {date.today().year}")
