import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import base64
from io import BytesIO
from PIL import Image
import math

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

# AUTO-INITIALIZE DEFAULT ADMIN USER IF TABLES ARE EMPTY
try:
    check_empty = supabase.table("workers").select("*").execute()
    if not check_empty.data:
        supabase.table("workers").insert({
            "name": "admin", 
            "role": "CEO", 
            "password": "1234"
        }).execute()
except Exception:
    pass

try:
    check_merch = supabase.table("merchants").select("*").execute()
    if not check_merch.data:
        supabase.table("merchants").insert({
            "store_name": "Sammyreks Business Center",
            "store_slug": "sammyreks",
            "owner_name": "Sammyreks",
            "phone": "08000000000",
            "password": "1234"
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
        st.error(f"Failed to fetch {table_name}: {e}")
        return pd.DataFrame()

# ==========================================
# 2. CORE UTILITY FUNCTIONS (HD IMAGES)
# ==========================================
def get_image_base64(uploaded_file):
    if uploaded_file is not None:
        try:
            if isinstance(uploaded_file, Image.Image):
                img = uploaded_file
            else:
                img = Image.open(uploaded_file)
                
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=100, subsampling=0)
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            st.error(f"Image processing failed: {e}")
            return None
    return None

def display_image_base64(base64_str):
    if base64_str:
        try:
            return base64.b64decode(base64_str)
        except Exception:
            return None
    return None

def get_file_base64(uploaded_file):
    if uploaded_file is not None:
        try:
            return base64.b64encode(uploaded_file.read()).decode()
        except Exception as e:
            st.error(f"Video file processing failed: {e}")
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

if 'auth' not in st.session_state:
    st.session_state.auth = {"logged_in": False, "user": None, "role": None, "store_slug": "sammyreks", "store_name": "Sammyreks Business Center"}

store_title = "Sammyreks Business Center"
query_params = st.query_params
url_store = query_params.get("store", "sammyreks")

st.sidebar.title("🏢 Sammyreks Portal")
st.sidebar.markdown("---")

if not st.session_state.auth["logged_in"]:
    auth_mode = st.sidebar.selectbox("Choose Portal", ["🛍️ Customer Shop", "🔑 Staff/Admin Login", "🏬 Merchant Partner Login"])
    
    if auth_mode == "🔑 Staff/Admin Login":
        with st.sidebar.form("login_form"):
            user_input = st.text_input("Username").strip()
            pass_input = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Login"):
                if not user_input or not pass_input:
                    st.error("Please enter both Username and Password.")
                else:
                    try:
                        res = supabase.table("workers").select("role, name").ilike("name", user_input).eq("password", pass_input).execute()
                        if res.data and len(res.data) > 0:
                            matched_user = res.data[0]
                            st.session_state.auth = {
                                "logged_in": True, 
                                "user": matched_user['name'], 
                                "role": matched_user['role'],
                                "store_slug": "sammyreks",
                                "store_name": "Sammyreks Business Center"
                            }
                            st.success(f"Welcome back, {matched_user['name']}!")
                            st.rerun()
                        else:
                            st.error("Incorrect username or password.")
                    except Exception as e:
                        st.error(f"Login error: {e}")
                        
    elif auth_mode == "🏬 Merchant Partner Login":
        with st.sidebar.form("merchant_login_form"):
            m_slug_input = st.text_input("Store Slug / Username").strip().lower()
            m_pass_input = st.text_input("Store Password", type="password").strip()
            if st.form_submit_button("Merchant Login"):
                if not m_slug_input or not m_pass_input:
                    st.error("Please enter store slug and password.")
                else:
                    try:
                        m_res = supabase.table("merchants").select("*").eq("store_slug", m_slug_input).eq("password", m_pass_input).execute()
                        if m_res.data and len(m_res.data) > 0:
                            merch = m_res.data[0]
                            st.session_state.auth = {
                                "logged_in": True,
                                "user": merch['owner_name'],
                                "role": "MERCHANT",
                                "store_slug": merch['store_slug'],
                                "store_name": merch['store_name']
                            }
                            st.success(f"Welcome to {merch['store_name']} dashboard!")
                            st.rerun()
                        else:
                            st.error("Invalid store slug or password.")
                    except Exception as e:
                        st.error(f"Login error: {e}")
                        
    view_mode = "CUSTOMER"
else:
    st.sidebar.success(f"Logged in: {st.session_state.auth['user']} ({st.session_state.auth['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.auth = {"logged_in": False, "user": None, "role": None, "store_slug": "sammyreks", "store_name": "Sammyreks Business Center"}
        st.rerun()
    view_mode = "STAFF"

# ==========================================
# 4. STAFF & CEO & MERCHANT DASHBOARD
# ==========================================
if view_mode == "STAFF":
    role = st.session_state.auth["role"]
    user_logged = st.session_state.auth["user"]
    active_store_slug = st.session_state.auth["store_slug"]
    active_store_name = st.session_state.auth["store_name"]
    store_title = active_store_name
    
    st.title(f"🏢 Dashboard: {active_store_name}")

    if role == "MERCHANT":
        menu = ["📊 Dashboard", "🛒 POS & Sales", "📦 Inventory", "📋 Orders/Requests", "💬 Customer Chats", "⚙️ Settings"]
    else:
        menu = ["📊 Dashboard", "🛒 POS & Sales", "📦 Inventory", "📋 Orders/Requests", "💬 Customer Chats", "📓 Debtors", "⚙️ Settings"]
        if role == "CEO":
            menu += ["💸 Expenses", "👥 Workers", "🏪 Manage Merchant Stores"]
    
    tabs = st.tabs(menu)

    # TAB 0: DASHBOARD
    with tabs[0]:
        st.header("Business Analytics")
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
        st.header("New Sale Transaction")
        try:
            res_pos = supabase.table("products").select("*").eq("store_slug", active_store_slug).gt("qty_cartons", 0).execute()
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
                c_phone_pos = st.text_input("Customer Phone Number")
            with col_pos2:
                up = p['price_carton'] if sale_unit == m_label else (p['price_pack'] if sale_unit == p_label else p['price_retail'])
                grand_total = up * sale_qty
                st.subheader(f"Total: ₦{grand_total:,.2f}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🏁 Cash Sale", use_container_width=True):
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
                            
                        st.success("Sale Recorded permanently!")
                        st.rerun()
                
                with col_btn2:
                    if role != "MERCHANT" and st.button("📓 Record Debt", use_container_width=True):
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
        else:
            st.info("No products found in stock for this store.")

    # TAB 2: INVENTORY CONTROL
    with tabs[2]:
        st.header("📦 Stock & Warehouse Control")
        try:
            res_inv = supabase.table("products").select("*").eq("store_slug", active_store_slug).execute()
            df_inv = pd.DataFrame(res_inv.data) if res_inv.data else pd.DataFrame()
        except Exception:
            df_inv = pd.DataFrame()
        
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
        
        st.write("📷 **Product Image Input (Crisp HD Quality)**")
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
                    background_color="#2e7d32",
                    hover_background_color="#1b5e20",
                    errors="raise"
                )
                if paste_result.image_data is not None:
                    chosen_image = paste_result.image_data
                    st.image(chosen_image, caption="Pasted Image Preview", width=150)
            except Exception:
                st.info("Paste from clipboard component not available.")

        st.divider()
        st.write("🎥 **Product Video Advert Input**")
        vid_file = st.file_uploader("Upload Direct MP4 Video File (Max 10MB)", type=["mp4", "mov", "webm"])

        with st.form("inventory_form"):
            st.info(f"✏️ **Store Inventory**: Adding item to **{active_store_name}**.")
            
            default_cat = str(curr_data.get('category', 'General') or 'General')
            category_options = ["Raw Food", "Beverages", "Books", "Electronics", "Toiletries", "Provision", "General"]
            if default_cat not in category_options:
                category_options.append(default_cat)
            
            sel_category = st.selectbox("Product Category", category_options, index=category_options.index(default_cat))

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
                        "store_slug": active_store_slug,
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
                            st.error(f"A product named '{safe_name}' already exists in this store.")
                        else:
                            st.error(f"Database Save Error: {save_error}")

        st.divider()
        if not df_inv.empty:
            st.subheader("🗑️ Delete Unwanted Product")
            with st.expander("⚠️ Click here to delete a product permanently"):
                delete_target = st.selectbox("Select Item to PERMANENTLY Delete", df_inv['name'], key="del_box")
                st.error(f"Warning: Deleting '{delete_target}' cannot be undone!")
                if st.button(f"Confirm Delete: {delete_target}"):
                    supabase.table("products").delete().eq("name", delete_target).eq("store_slug", active_store_slug).execute()
                    st.success(f"'{delete_target}' has been removed.")
                    st.rerun()

    # TAB 3: ORDER LOG
    with tabs[3]:
        st.header("Order Log")
        df_order_list = fetch_dataframe("orders")
        if not df_order_list.empty:
            st.dataframe(df_order_list.sort_values('timestamp', ascending=False), use_container_width=True, hide_index=True)

    # TAB 4: CUSTOMER CHATS
    with tabs[4]:
        st.header("💬 Live Customer Communication")
        st.info("Chat management portal.")

    # TAB 5: DEBTORS (Admin only)
    if role != "MERCHANT":
        with tabs[5]:
            st.header("📓 Debtors Management")
            df_debtors = fetch_dataframe("debtors")
            if not df_debtors.empty:
                st.dataframe(df_debtors, use_container_width=True, hide_index=True)

    # TAB 6: SETTINGS
    setting_tab_idx = 6 if role != "MERCHANT" else 5
    with tabs[setting_tab_idx]:
        st.header("⚙️ User Settings")
        st.write(f"Logged into store: **{active_store_name}** (`?store={active_store_slug}`)")

    # CEO EXCLUSIVE TABS
    if role == "CEO":
        with tabs[7]:
            st.header("Expenditure Log")
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
            st.header("Staff Management")
            df_workers = fetch_dataframe("workers")
            if not df_workers.empty:
                st.dataframe(df_workers, use_container_width=True, hide_index=True)

        with tabs[9]:
            st.header("🏪 Manage Merchant Stores (Super Admin)")
            st.write("Create dedicated store accounts and links for other business owners!")
            
            df_merchants = fetch_dataframe("merchants")
            if not df_merchants.empty:
                st.subheader("Existing Merchant Stores")
                for _, m_row in df_merchants.iterrows():
                    store_link = f"https://your-app.streamlit.app/?store={m_row['store_slug']}"
                    st.markdown(f"**🏪 {m_row['store_name']}** (Owner: {m_row['owner_name']} | Phone: {m_row['phone']})")
                    st.code(store_link, language="text")
                    st.divider()

            st.subheader("➕ Create New Merchant Account")
            with st.form("create_merchant_form"):
                m_name = st.text_input("Store Name (e.g. John Electronics)")
                m_slug = st.text_input("Store URL Slug (e.g. john-store - no spaces)").strip().lower()
                m_owner = st.text_input("Owner Full Name")
                m_phone = st.text_input("Phone Number")
                m_pass = st.text_input("Assign Password", type="password")
                
                if st.form_submit_button("🚀 Create Merchant Store"):
                    if m_name and m_slug and m_owner and m_pass:
                        try:
                            merch_payload = {
                                "store_name": m_name,
                                "store_slug": m_slug.replace(" ", "-"),
                                "owner_name": m_owner,
                                "phone": m_phone,
                                "password": m_pass
                            }
                            supabase.table("merchants").insert(merch_payload).execute()
                            st.success(f"✅ Success! Merchant store '{m_name}' created successfully with link: `?store={m_slug}`")
                            st.rerun()
                        except Exception as me:
                            st.error(f"Creation failed (Store slug might already exist): {me}")
                    else:
                        st.error("Please fill in all required fields.")

# ==========================================
# 5. CUSTOMER PORTAL (MULTI-STOREFRONT)
# ==========================================
else:
    current_store_slug = url_store
    store_title = "Sammyreks Business Center"
    
    try:
        store_res = supabase.table("merchants").select("*").eq("store_slug", current_store_slug).execute()
        if store_res.data and len(store_res.data) > 0:
            store_info = store_res.data[0]
            store_title = store_info['store_name']
    except Exception:
        pass

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #2e7d32, #1b5e20); padding: 25px; border-radius: 12px; color: white; text-align: center; margin-bottom: 25px;">
            <h1 style="margin: 0; font-size: 2.2rem;">🏢 Welcome to {store_title}</h1>
            <p style="margin: 8px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Your trusted plug for quality products and verified wholesale provisions!</p>
        </div>
    """, unsafe_allow_html=True)

    c_tab1, c_tab2, c_tab3, c_tab4 = st.tabs(["🛍️ Shop by Category", "📝 Special Request", "🔍 Track My Order", "💬 Chat with Us"])
    
    with c_tab2:
        st.subheader("Can't find what you need?")
        with st.form("custom_order_form", clear_on_submit=True):
            cust_n = st.text_input("Your Full Name")
            cust_p = st.text_input("Your Phone Number")
            cust_i = st.text_input("Item Requested")
            cust_q = st.number_input("Quantity Needed", min_value=1)
            if st.form_submit_button("🚀 Submit Request"):
                if cust_n and cust_i and cust_p:
                    order_payload = {
                        "customer": cust_n, "item": f"SPECIAL: {cust_i}", "qty": int(cust_q),
                        "status": "Pending", "contact_phone": cust_p, "total_price": 0.0,
                        "date": date.today().isoformat(), "timestamp": get_now()
                    }
                    supabase.table("orders").insert(order_payload).execute()
                    st.success("✅ Request logged to database! We will contact you soon.")
                else:
                    st.error("Please fill all fields.")

    with c_tab3:
        st.subheader("Check your order status")
        track_phone = st.text_input("Enter the Phone Number used to order")
        if track_phone:
            try:
                res_track = supabase.table("orders").select("item, qty, status, total_price, date").eq("contact_phone", track_phone).execute()
                if res_track.data:
                    st.table(pd.DataFrame(res_track.data))
                else:
                    st.info("No orders found for this number.")
            except Exception:
                pass

    with c_tab4:
        st.subheader("💬 Direct Support Chat")
        c_phone_chat = st.text_input("Enter your Phone Number to start chatting", key="cust_chat_phone")
        
        if c_phone_chat.strip():
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

    with c_tab1:
        try:
            res_shop = supabase.table("products").select("*").eq("store_slug", current_store_slug).gt("qty_cartons", 0).execute()
            df_shop = pd.DataFrame(res_shop.data) if res_shop.data else pd.DataFrame()
        except Exception:
            df_shop = pd.DataFrame()

        if not df_shop.empty:
            if 'category' not in df_shop.columns:
                df_shop['category'] = 'General'

            categories = ["All Categories"] + sorted(df_shop['category'].dropna().unique().tolist())
            
            col_filt1, col_filt2 = st.columns([1, 2])
            with col_filt1:
                selected_cat = st.selectbox("📂 Filter by Category", categories)
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
                                st.image(img_bytes, width=200)
                            else:
                                st.info("No Image")
                        with col_info:
                            st.subheader(s_row['name'])
                            st.caption(f"📂 Category: **{s_row.get('category', 'General')}** | 📍 Shelf: {s_row.get('shelf', 'N/A')}")
                            st.write(s_row.get('description', ''))
                            
                            has_direct_vid = s_row.get('video_data') and str(s_row['video_data']).strip() not in ["None", "", "nan"]
                            has_url_vid = s_row.get('video_url') and str(s_row['video_url']).strip() not in ["None", "", "nan"]

                            if has_direct_vid or has_url_vid:
                                with st.expander("🎥 Watch Product Video Advert"):
                                    if has_direct_vid:
                                        try:
                                            vid_bytes = base64.b64decode(s_row['video_data'])
                                            st.video(vid_bytes)
                                        except Exception:
                                            st.error("Video file is corrupted.")
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
                            
                            with st.popover(f"🛒 Order - ₦{total_calc:,.2f}"):
                                st.subheader(f"{store_title}\nConfirm Order for {s_row['name']}")
                                with st.form(key=f"popover_form_{s_row['id']}"):
                                    c_name = st.text_input("Full Name")
                                    c_phone = st.text_input("Phone Number")
                                    submit_order = st.form_submit_button("Confirm Order Now")
                                    
                                    if submit_order:
                                        if c_name.strip() and c_phone.strip():
                                            order_payload = {
                                                "customer": c_name,
                                                "item": f"{s_row['name']} ({unit_choice})",
                                                "qty": int(qty_choice),
                                            "status": "Order Placed",
                                                "contact_phone": c_phone,
                                                "total_price": float(total_calc),
                                                "date": date.today().isoformat(),
                                                "timestamp": get_now()
                                            }
                                            try:
                                                supabase.table("orders").insert(order_payload).execute()
                                                st.success(f"✅ Success! Your order for {s_row['name']} has been placed.")
                                                st.rerun()
                                            except Exception as err:
                                                st.error(f"Order submission failed: {err}")
                                        else:
                                            st.error("Please enter both Name and Phone Number.")
                        st.divider()
            else:
                st.warning("No products found in this category or search for this store.")
        else:
            st.warning("No products available in this store yet.")

st.sidebar.caption(f"{store_title} v7.0 | {date.today().year}")
