import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
from io import BytesIO
from PIL import Image
import math
import hashlib
import urllib.parse
import random
import json
import base64
import cloudinary
import cloudinary.uploader
from streamlit_autorefresh import st_autorefresh

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

@st.cache_data(ttl=120)
def fetch_dataframe_cached(table_name):
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as err:
        return pd.DataFrame()

def fetch_dataframe(table_name):
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
    items_text = "\n".join([f"• {i.get('name', 'Item')} ({i.get('unit', 'Unit')}) x{i.get('qty', 1)} @ ₦{i.get('price', 0):,.2f} = ₦{i.get('total', 0):,.2f}" for i in items_list])
    
    message = (
        f"🏢 *{store_title}*\n"
        f"----------------------------------------\n"
        f"*{receipt_type}*\n"
        f"----------------------------------------\n\n"
        f"👤 *Customer:* {customer_name}\n"
        f"📞 *Phone:* {phone}\n\n"
        f"🛒 *Purchased Items:*\n{items_text}\n\n"
        f"----------------------------------------\n"
        f"💰 *Grand Total: ₦{grand_total:,.2f}*\n"
        f"----------------------------------------\n"
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
            padding: 10px 14px !important;
            border-radius: 8px !important;
            margin-bottom: 3px !important;
        }
        div[data-baseweb="tab"] {
            font-size: 1.1rem !important;
            font-weight: bold !important;
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
            login_submitted = st.form_submit_button("Login")
            
            if login_submitted:
                if not user_input or not pass_input:
                    st.error("Please enter both Username and Password.")
                else:
                    try:
                        # Instant hardcoded check for admin
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
                            # Optimized indexed query lookup
                            res = supabase.table("workers").select("role, name").ilike("name", user_input).eq("password", hashed_attempt).limit(1).execute()
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

    tab_titles = [
        "📊 Dashboard", 
        "💳 POS & Sales", 
        "📦 Inventory", 
        "💬 Live Chat & One-Tap Receipt Center", 
        "📜 Saved Receipts Vault", 
        "📓 Debtors", 
        "⚙️ Settings", 
        "💸 Expenses", 
        "👥 Workers"
    ]
    tabs = st.tabs(tab_titles)

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
                pay_source_pos = st.selectbox("Payment Gateway / Source", ["Moniepoint MFB", "OPay", "Access Bank", "Cash", "Transfer"], key="pos_pay_source")
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
                        pos_ref = f"POS-{random.randint(1000, 9999)}"
                        
                        sold_item_entry = [{"name": sel_item, "unit": sale_unit, "qty": int(sale_qty), "price": up, "total": grand_total}]
                        
                        supabase.table("saved_receipts").insert({
                            "payment_ref": pos_ref,
                            "customer_name": c_name_pos or "Walk-in Customer",
                            "customer_phone": c_phone_pos or "N/A",
                            "items_json": json.dumps(sold_item_entry),
                            "grand_total": float(grand_total),
                            "payment_source": pay_source_pos,
                            "cashier": user_logged,
                            "timestamp": get_now()
                        }).execute()

                        sale_data = {
                            "item": f"{sel_item} ({sale_qty} {sale_unit})", "unit_type": sale_unit, "qty": int(sale_qty),
                            "total": float(grand_total), "profit": float(profit_final), "date": date.today().isoformat(),
                            "timestamp": get_now(), "worker": user_logged, "customer_name": c_name_pos, "customer_phone": c_phone_pos,
                            "payment_source": pay_source_pos, "payment_ref": pos_ref
                        }
                        supabase.table("sales").insert(sale_data).execute()
                        
                        new_qty = float(p['qty_cartons'] - cartons_deducted)
                        supabase.table("products").update({"qty_cartons": new_qty}).eq("id", int(p['id'])).execute()
                        st.cache_data.clear()
                            
                        st.session_state.last_receipt = {
                            "type": "Official Sales & Delivery Receipt", 
                            "customer": c_name_pos or "Walk-in Customer",
                            "phone": c_phone_pos or "N/A", 
                            "date": get_now(),
                            "sold_items": sold_item_entry,
                            "grand_total": grand_total, 
                            "cashier": user_logged,
                            "payment_source": pay_source_pos,
                            "payment_ref": pos_ref
                        }
                        st.success("Sale Recorded & Permanent Receipt Saved!")
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
            rec_type = rec.get('type', 'OFFICIAL SALES RECEIPT')
            sold_items_list = rec.get('sold_items', rec.get('items', []))
            cust_name_rc = rec.get('customer', 'Walk-in Customer')
            cust_phone_rc = rec.get('phone', 'N/A')
            g_total_rc = rec.get('grand_total', 0.0)
            p_source_rc = rec.get('payment_source', 'Moniepoint MFB')
            p_ref_rc = rec.get('payment_ref', 'N/A')

            receipt_rows_html = "".join([
                f"<tr><td style='padding:6px 0; font-size:0.9rem;'><b>{itm.get('name','Item')}</b><br><span style='font-size:0.75rem; color:#555;'>{itm.get('qty',1)} x ₦{itm.get('price',0.0):,.2f} ({itm.get('unit','Unit')})</span></td><td style='padding:6px 0; text-align:right; font-size:0.9rem; vertical-align:top; font-weight:bold;'>₦{itm.get('total',0.0):,.2f}</td></tr>"
                for itm in sold_items_list
            ])

            thermal_html = f"""
            <div style="background:#fdfcf7; color:#111; padding:25px; border-radius:4px; border:1px solid #dcd6cd; font-family:'Courier New', Courier, monospace; max-width:420px; margin:auto; box-shadow: 0 6px 18px rgba(0,0,0,0.12);">
                <div style="text-align:center; border-bottom:1px dashed #333; padding-bottom:12px; margin-bottom:12px;">
                    <h3 style="margin:0; font-size:1.3rem; letter-spacing:1px;">{store_title.upper()}</h3>
                    <p style="margin:2px 0; font-size:0.75rem; color:#444;">WHOLESALE & RETAIL DISTRIBUTION</p>
                    <p style="margin:6px 0 0 0; font-size:0.85rem; font-weight:bold; background:#222; color:#fff; display:inline-block; padding:2px 8px; border-radius:3px;">{rec_type}</p>
                </div>
                <div style="font-size:0.8rem; margin-bottom:12px; border-bottom:1px dashed #333; padding-bottom:8px;">
                    <p style="margin:2px 0;"><b>DATE:</b> {rec.get('date','')}</p>
                    <p style="margin:2px 0;"><b>CUSTOMER:</b> {cust_name_rc}</p>
                    <p style="margin:2px 0;"><b>PHONE:</b> {cust_phone_rc}</p>
                    <p style="margin:2px 0;"><b>REF CODE:</b> {p_ref_rc}</p>
                    <p style="margin:2px 0;"><b>PAYMENT SOURCE:</b> {p_source_rc}</p>
                    <p style="margin:2px 0;"><b>CASHIER:</b> {rec.get('cashier','Staff')}</p>
                </div>
                <table style="width:100%; border-collapse:collapse; margin-bottom:15px;">
                    <thead>
                        <tr style="border-bottom:1px solid #333; font-size:0.8rem;">
                            <th style="text-align:left; padding-bottom:4px;">ITEM / DESC</th>
                            <th style="text-align:right; padding-bottom:4px;">TOTAL</th>
                        </tr>
                    </thead>
                    <tbody>{receipt_rows_html}</tbody>
                </table>
                <div style="border-top:1px dashed #333; border-bottom:1px dashed #333; padding:10px 0; margin-bottom:15px;">
                    <div style="display:flex; justify-content:space-between; font-size:1.1rem; font-weight:bold;">
                        <span>GRAND TOTAL:</span>
                        <span>₦{g_total_rc:,.2f}</span>
                    </div>
                </div>
                <div style="text-align:center; font-size:0.75rem; color:#555;">
                    <p style="margin:2px 0;">*** THANK YOU FOR YOUR PATRONAGE ***</p>
                    <p style="margin:2px 0;">Goods sold in good condition are non-refundable.</p>
                </div>
            </div>
            """
            st.markdown(thermal_html, unsafe_allow_html=True)

            wa_url = generate_whatsapp_link(cust_phone_rc, rec_type, cust_name_rc, sold_items_list, g_total_rc)
            st.markdown(f"""
                <a href="{wa_url}" target="_blank">
                    <button style="width:100%; background-color:#25d366; color:white; padding:14px; border:none; border-radius:8px; font-size:1.1rem; font-weight:bold; cursor:pointer; margin-top:15px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
                        💬 Send Thermal Receipt via WhatsApp
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

        st.write("📷 **Product Image Upload (Select from Gallery or Files)**")
        chosen_image = st.file_uploader("Upload Product Image", type=["png", "jpg", "jpeg", "webp"], key=f"img_uploader_{target_id}")

        st.divider()
        st.write("🎥 **Product Video File Upload (Hosted on Cloudinary)**")
        vid_file = st.file_uploader("Upload Direct MP4 Video File", type=["mp4", "mov", "webm", "mkv"], key=f"vid_uploader_{target_id}")

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

    # TAB 3: LIVE CHAT & ONE-TAP RECEIPT CENTER (HIGH SPEED SYNC)
    with tabs[3]:
        st.header("💬 Live Chat & One-Tap Receipt Center")
        
        st_autorefresh(interval=5000, limit=None, key="staff_chat_fast_sync")
        
        try:
            res_msg = supabase.table("messages").select("customer_phone, customer_name").execute()
            if res_msg.data:
                chat_threads = {}
                for m in res_msg.data:
                    ph = m.get('customer_phone')
                    nm = m.get('customer_name', 'Customer')
                    if ph:
                        chat_threads[f"{nm} ({ph})"] = ph

                if chat_threads:
                    selected_thread_label = st.selectbox("Select Customer Chat Thread", list(chat_threads.keys()), key="staff_chat_sel")
                    active_phone = chat_threads[selected_thread_label]
                    
                    st.markdown(f"### 💬 Conversation with **{selected_thread_label}** *(Instant Sync)*")
                    
                    thread_msgs = supabase.table("messages").select("*").eq("customer_phone", active_phone).order("id").execute()
                    
                    for msg in thread_msgs.data:
                        sender_role = msg.get('sender', 'Customer')
                        msg_text = msg.get('message', '')
                        img_proof = msg.get('proof_url')
                        
                        if sender_role == "Customer":
                            st.markdown(f"👤 **Customer** *({msg.get('timestamp','')})*:\n> {msg_text}")
                            if img_proof and isinstance(img_proof, str) and img_proof.startswith("http"):
                                st.image(img_proof, width=300, caption="Uploaded Payment Proof")
                        elif sender_role == "System":
                            st.markdown(f"🤖 **Receipt Notice** *({msg.get('timestamp','')})*")
                            st.markdown(msg_text, unsafe_allow_html=True)
                        else:
                            st.markdown(f"🏢 **{sender_role}** *({msg.get('timestamp','')})*:\n> {msg_text}")

                    st.divider()
                    
                    c_rep1, c_rep2 = st.columns([2, 1])
                    with c_rep1:
                        with st.form("staff_chat_reply_form", clear_on_submit=True):
                            staff_reply = st.text_input("Type message / availability / substitute options...", key="staff_reply_text")
                            if st.form_submit_button("📤 Send Chat to Customer"):
                                if staff_reply.strip():
                                    supabase.table("messages").insert({
                                        "sender": f"Staff ({user_logged})",
                                        "customer_phone": active_phone,
                                        "customer_name": selected_thread_label.split(" (")[0],
                                        "message": staff_reply.strip(),
                                        "timestamp": get_now()
                                    }).execute()
                                    st.rerun()
                                    
                    with c_rep2:
                        st.write("⚡ **One-Tap Receipt Action**")
                        pay_source_choice = st.selectbox("Select Payment Account/Gateway", ["Moniepoint MFB", "OPay", "Access Bank", "Cash", "Transfer"], key="staff_pay_source_choice")
                        
                        cust_orders = supabase.table("orders").select("*").eq("contact_phone", active_phone).execute()
                        
                        if cust_orders.data and len(cust_orders.data) > 0:
                            pending_orders = [o for o in cust_orders.data if "Pending" in o.get('status', '') or "Submitted" in o.get('status', '') or "Order Placed" in o.get('status', '')]
                            
                            if pending_orders:
                                order_ref = pending_orders[0].get('payment_ref', 'SRK-XXXX')
                                grand_sum = sum([float(o.get('total_price', 0.0)) for o in pending_orders])
                                cust_nm = pending_orders[0].get('customer', 'Customer')
                                
                                if st.button(f"✅ One-Tap Approve & Release Thermal Receipt [{order_ref}]", key="staff_one_tap_btn", use_container_width=True):
                                    receipt_rows_html = ""
                                    saved_items_list = []
                                    
                                    for o in pending_orders:
                                        supabase.table("orders").update({"status": "Completed / Paid"}).eq("id", int(o['id'])).execute()
                                        
                                        clean_nm = str(o['item']).replace("SPECIAL:", "").replace("[Cart Order]", "").strip()
                                        q_val = float(o['qty']) if o['qty'] > 0 else 1.0
                                        t_val = float(o['total_price'])
                                        u_price = t_val / q_val if q_val > 0 else t_val
                                        
                                        receipt_rows_html += f"<tr><td style='padding:6px 0; font-size:0.9rem;'><b>{clean_nm}</b><br><span style='font-size:0.75rem; color:#555;'>{int(q_val)} x ₦{u_price:,.2f}</span></td><td style='padding:6px 0; text-align:right; font-size:0.9rem; vertical-align:top; font-weight:bold;'>₦{t_val:,.2f}</td></tr>"
                                        
                                        saved_items_list.append({"name": clean_nm, "unit": "Unit", "qty": int(q_val), "price": u_price, "total": t_val})
                                        
                                        supabase.table("sales").insert({
                                            "item": clean_nm, "unit_type": "Unit", "qty": int(q_val),
                                            "total": t_val, "profit": t_val * 0.15, "date": date.today().isoformat(),
                                            "timestamp": get_now(), "worker": user_logged, "customer_name": cust_nm, 
                                            "customer_phone": active_phone, "payment_source": pay_source_choice, "payment_ref": order_ref
                                        }).execute()

                                    supabase.table("saved_receipts").insert({
                                        "payment_ref": order_ref,
                                        "customer_name": cust_nm,
                                        "customer_phone": active_phone,
                                        "items_json": json.dumps(saved_items_list),
                                        "grand_total": float(grand_sum),
                                        "payment_source": pay_source_choice,
                                        "cashier": user_logged,
                                        "timestamp": get_now()
                                    }).execute()

                                    professional_receipt_html = f"""
                                    <div style="background:#fdfcf7; color:#111; padding:20px; border-radius:6px; border:1px solid #dcd6cd; font-family:'Courier New', Courier, monospace; max-width:380px; margin:10px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                                        <div style="text-align:center; border-bottom:1px dashed #333; padding-bottom:10px; margin-bottom:10px;">
                                            <h3 style="margin:0; font-size:1.2rem; letter-spacing:1px;">{store_title.upper()}</h3>
                                            <p style="margin:2px 0; font-size:0.75rem; color:#444;">OFFICIAL PURCHASE RECEIPT</p>
                                            <span style="background:#222; color:#fff; font-size:0.75rem; padding:2px 6px; border-radius:3px; font-weight:bold;">PAID & VERIFIED</span>
                                        </div>
                                        <div style="font-size:0.8rem; margin-bottom:10px; border-bottom:1px dashed #333; padding-bottom:6px;">
                                            <p style="margin:2px 0;"><b>REF CODE:</b> {order_ref}</p>
                                            <p style="margin:2px 0;"><b>CUSTOMER:</b> {cust_nm}</p>
                                            <p style="margin:2px 0;"><b>PHONE:</b> {active_phone}</p>
                                            <p style="margin:2px 0;"><b>GATEWAY:</b> {pay_source_choice}</p>
                                            <p style="margin:2px 0;"><b>DATE:</b> {get_now()}</p>
                                        </div>
                                        <table style="width:100%; border-collapse:collapse; margin-bottom:12px;">
                                            <thead>
                                                <tr style="border-bottom:1px solid #333; font-size:0.8rem;">
                                                    <th style="text-align:left; padding-bottom:4px;">ITEM / DESC</th>
                                                    <th style="text-align:right; padding-bottom:4px;">TOTAL</th>
                                                </tr>
                                            </thead>
                                            <tbody>{receipt_rows_html}</tbody>
                                        </table>
                                        <div style="border-top:1px dashed #333; border-bottom:1px dashed #333; padding:8px 0; margin-bottom:10px;">
                                            <div style="display:flex; justify-content:space-between; font-size:1rem; font-weight:bold;">
                                                <span>TOTAL PAID:</span>
                                                <span>₦{grand_sum:,.2f}</span>
                                            </div>
                                        </div>
                                        <div style="text-align:center; font-size:0.75rem; color:#555;">
                                            <p style="margin:2px 0;">*** THANK YOU FOR YOUR PATRONAGE ***</p>
                                            <p style="margin:2px 0;">Saved permanently to transaction vault.</p>
                                        </div>
                                    </div>
                                    """
                                    
                                    supabase.table("messages").insert({
                                        "sender": "System",
                                        "customer_phone": active_phone,
                                        "customer_name": cust_nm,
                                        "message": professional_receipt_html,
                                        "timestamp": get_now()
                                    }).execute()
                                    
                                    st.success("Professional receipt saved & sent to chat!")
                                    st.rerun()
                            else:
                                st.info("No active pending orders requiring approval.")
                        else:
                            st.info("No orders found for this customer thread.")
            else:
                st.info("No active chat conversations yet.")
        except Exception as chat_err:
            st.error(f"Chat dashboard error: {chat_err}")

    # TAB 4: SAVED RECEIPTS VAULT (BANK-STYLE)
    with tabs[4]:
        st.header("📜 Saved Receipts Vault (Bank-Style Ledger)")
        st.caption("All completed purchase transactions are permanently archived here as individual receipts.")
        
        df_vault = fetch_dataframe("saved_receipts")
        if not df_vault.empty:
            search_vault = st.text_input("🔍 Search by Ref Code or Customer Name/Phone", key="vault_search")
            if search_vault:
                df_vault = df_vault[
                    df_vault['payment_ref'].str.contains(search_vault, case=False, na=False) |
                    df_vault['customer_name'].str.contains(search_vault, case=False, na=False) |
                    df_vault['customer_phone'].str.contains(search_vault, case=False, na=False)
                ]
            
            for idx, r_row in df_vault.sort_values('id', ascending=False).iterrows():
                with st.expander(f"🧾 Ref: [{r_row['payment_ref']}] — {r_row['customer_name']} ({r_row['customer_phone']}) — ₦{float(r_row['grand_total']):,.2f} [{r_row['timestamp']}]"):
                    col_v1, col_v2 = st.columns([2, 1])
                    with col_v1:
                        st.write(f"**Gateway Source:** {r_row['payment_source']}")
                        st.write(f"**Cashier / Staff:** {r_row['cashier']}")
                        st.write(f"**Transaction Timestamp:** {r_row['timestamp']}")
                        
                        try:
                            items_parsed = json.loads(r_row['items_json'])
                            items_html_vault = "".join([f"<li>{i.get('name')} ({i.get('qty')} x ₦{i.get('price',0):,.2f}) = ₦{i.get('total',0):,.2f}</li>" for i in items_parsed])
                            st.markdown(f"<ul>{items_html_vault}</ul>", unsafe_allow_html=True)
                        except Exception:
                            st.write(r_row['items_json'])
                    with col_v2:
                        st.metric("Total Amount", f"₦{float(r_row['grand_total']):,.2f}")
        else:
            st.info("No saved receipts in vault yet.")

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
        st.subheader("📌 Notice Board Ticker & Direct Cloudinary Broadcast Video Upload")
        
        try:
            curr_notice_res = supabase.table("app_settings").select("value").eq("key", "active_notice").execute()
            existing_notice = curr_notice_res.data[0]['value'] if (curr_notice_res.data and len(curr_notice_res.data) > 0) else ""
        except Exception:
            existing_notice = ""

        try:
            curr_video_res = supabase.table("app_settings").select("value").eq("key", "broadcast_video_url").execute()
            existing_video = curr_video_res.data[0]['value'] if (curr_video_res.data and len(curr_video_res.data) > 0) else ""
        except Exception:
            existing_video = ""

        st.write("🎥 **Upload Broadcast Announcement Video (Direct to Cloudinary)**")
        broadcast_vid_file = st.file_uploader("Choose MP4 Video File for Top Broadcast", type=["mp4", "mov", "webm", "mkv"], key="broadcast_file_uploader")

        with st.form("notice_form"):
            notice_input = st.text_area("Notice Message (Ticker)", value=existing_notice, key="settings_notice_input")
            fallback_video_url = st.text_input("OR Direct Video / YouTube URL", value=existing_video, key="settings_video_input")
            
            if st.form_submit_button("📢 Publish Notice & Broadcast Video"):
                uploaded_broadcast_url = upload_video_to_cloudinary(broadcast_vid_file) if broadcast_vid_file is not None else None
                final_broadcast_link = uploaded_broadcast_url if uploaded_broadcast_url else fallback_video_url.strip()

                chk_notice = supabase.table("app_settings").select("*").eq("key", "active_notice").execute()
                if chk_notice.data:
                    supabase.table("app_settings").update({"value": notice_input.strip()}).eq("key", "active_notice").execute()
                else:
                    supabase.table("app_settings").insert({"key": "active_notice", "value": notice_input.strip()}).execute()

                chk_video = supabase.table("app_settings").select("*").eq("key", "broadcast_video_url").execute()
                if chk_video.data:
                    supabase.table("app_settings").update({"value": final_broadcast_link}).eq("key", "broadcast_video_url").execute()
                else:
                    supabase.table("app_settings").insert({"key": "broadcast_video_url", "value": final_broadcast_link}).execute()

                st.success("Notice board and broadcast video updated successfully!")
                st.rerun()

    # TAB 7: EXPENSES (CEO ONLY)
    with tabs[7]:
        st.header("💸 Expenditure Log")
        if role == "CEO":
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
        else:
            st.warning("⚠️ Access restricted to CEO accounts only.")

    # TAB 8: WORKERS (CEO ONLY)
    with tabs[8]:
        st.header("👥 Staff Management")
        if role == "CEO":
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
        else:
            st.warning("⚠️ Access restricted to CEO accounts only.")

# ==========================================
# 5. INDEPENDENT CUSTOMER SHOP PORTAL
# ==========================================
else:
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1565c0, #0d47a1); padding: 22px; border-radius: 14px; color: white; text-align: center; margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2.1rem;">🏢 Welcome to {store_title}</h1>
            <p style="margin: 6px 0 0 0; font-size: 1.05rem;">Your trusted plug for quality provisions, groceries, and goods!</p>
        </div>
    """, unsafe_allow_html=True)

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

    try:
        vid_res = supabase.table("app_settings").select("value").eq("key", "broadcast_video_url").execute()
        if vid_res.data and len(vid_res.data) > 0 and vid_res.data[0].get('value'):
            b_video_url = vid_res.data[0]['value'].strip()
            if b_video_url and b_video_url.lower() not in ["none", "", "nan"]:
                st.markdown("""
                    <div style="background: linear-gradient(135deg, #0d47a1, #1565c0); padding: 8px 12px; border-radius: 8px; color: white; text-align: center; margin-bottom: 10px; font-weight: bold; font-size: 0.95rem;">
                        📢 FEATURED BROADCAST VIDEO ADVERT & ANNOUNCEMENT
                    </div>
                """, unsafe_allow_html=True)
                st.video(b_video_url)
                st.markdown("---")
    except Exception:
        pass

    st.markdown("### 📱 Quick Navigation (Tap below)")
    c_grid1, c_grid2 = st.columns(2)
    with c_grid1:
        if st.button("🛒 Shop Products & Cart", use_container_width=True, key="nav_shop_btn"):
            st.session_state.cust_active_page = "🛒 Shop & Cart"
            st.rerun()
        if st.button("💬 Live Chat & Receipt Center", use_container_width=True, key="nav_chat_btn"):
            st.session_state.cust_active_page = "💬 Live Chat & Receipt Center"
            st.rerun()

    with c_grid2:
        if st.button("📝 Multi-Item Request", use_container_width=True, key="nav_req_btn"):
            st.session_state.cust_active_page = "📝 Multi-Item Special Request"
            st.rerun()
        if st.button("📜 My Saved Receipts Vault", use_container_width=True, key="nav_vault_btn"):
            st.session_state.cust_active_page = "📜 My Saved Receipts"
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
            with st.expander("🛍️ View Cart & Send Order to Live Chat", expanded=True):
                cart_df = pd.DataFrame(st.session_state.cart)
                st.dataframe(cart_df[['name', 'unit', 'qty', 'total_price']], use_container_width=True, hide_index=True)
                st.markdown(f"### Grand Total: ₦{cart_total:,.2f}")
                
                with st.form("checkout_cart_form"):
                    c_name_cart = st.text_input("Your Full Name", value=st.session_state.active_cust_name, key="chk_name_input")
                    c_phone_cart = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone, key="chk_phone_input"))
                    c_details_cart = st.text_area("📍 Delivery Address & Order Notes", key="chk_address_input")
                    
                    if st.form_submit_button("🚀 Send Order to Live Chat"):
                        if c_name_cart.strip() and c_phone_cart.strip():
                            st.session_state.active_cust_name = c_name_cart.strip()
                            st.session_state.active_cust_phone = c_phone_cart.strip()
                            checkout_timestamp = get_now()
                            unique_pay_ref = f"SRK-{random.randint(1000, 9999)}"

                            items_summary = ", ".join([f"{i['qty']} {i['unit']}(s) of {i['name']}" for i in st.session_state.cart])
                            
                            for item in st.session_state.cart:
                                order_payload = {
                                    "customer": c_name_cart.strip(),
                                    "item": f"[Cart Order] {item['name']} ({item['unit']})",
                                    "qty": int(item['qty']),
                                    "status": "Order Placed - Pending Staff Quote",
                                    "contact_phone": c_phone_cart.strip(),
                                    "total_price": float(item['total_price']),
                                    "payment_ref": unique_pay_ref,
                                    "date": date.today().isoformat(),
                                    "timestamp": checkout_timestamp
                                }
                                supabase.table("orders").insert(order_payload).execute()
                            
                            chat_intro = f"Hello! I just submitted an order. Items: {items_summary}. Total: ₦{cart_total:,.2f}. My Reference Code is `{unique_pay_ref}`."
                            supabase.table("messages").insert({
                                "sender": "Customer",
                                "customer_phone": c_phone_cart.strip(),
                                "customer_name": c_name_cart.strip(),
                                "message": chat_intro,
                                "timestamp": get_now()
                            }).execute()

                            st.session_state.cart = []
                            st.session_state.cust_active_page = "💬 Live Chat & Receipt Center"
                            st.success(f"✅ Order & chat opened! Reference: {unique_pay_ref}")
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

        if st.button("🚀 Send Special Request to Live Chat", use_container_width=True, key="submit_req_btn"):
            if cust_n.strip() and cust_p.strip():
                batch_timestamp = get_now()
                unique_pay_ref = f"SRK-{random.randint(1000, 9999)}"
                
                req_names = []
                for e in st.session_state.request_items_temp:
                    if e['item'].strip():
                        req_names.append(f"{e['qty']} of {e['item'].strip()}")
                        supabase.table("orders").insert({
                            "customer": cust_n.strip(),
                            "item": f"SPECIAL: {e['item'].strip()}",
                            "qty": int(e['qty']),
                            "status": "Order Placed - Pending Staff Quote",
                            "contact_phone": cust_p.strip(),
                            "total_price": 0.0,
                            "payment_ref": unique_pay_ref,
                            "date": date.today().isoformat(),
                            "timestamp": batch_timestamp
                        }).execute()
                        
                chat_intro = f"Hello! I submitted a special request for: {', '.join(req_names)}. My Reference Code is `{unique_pay_ref}`."
                supabase.table("messages").insert({
                    "sender": "Customer",
                    "customer_phone": cust_p.strip(),
                    "customer_name": cust_n.strip(),
                    "message": chat_intro,
                    "timestamp": get_now()
                }).execute()

                st.session_state.active_cust_name = cust_n.strip()
                st.session_state.active_cust_phone = cust_p.strip()
                st.session_state.request_items_temp = [{"item": "", "qty": 1}]
                st.session_state.cust_active_page = "💬 Live Chat & Receipt Center"
                st.success(f"Special request sent to chat! Reference: {unique_pay_ref}")
                st.rerun()

    # PAGE 3: LIVE CHAT & RECEIPT CENTER (HIGH SPEED SYNC)
    elif st.session_state.cust_active_page == "💬 Live Chat & Receipt Center":
        st.subheader("💬 Live Chat & Payment Receipt Center")
        
        st_autorefresh(interval=5000, limit=None, key="cust_chat_fast_sync")
        
        c_chat_name = st.text_input("Your Full Name", value=st.session_state.active_cust_name, key="cust_chat_name")
        c_chat_phone = normalize_phone(st.text_input("Your Phone Number", value=st.session_state.active_cust_phone, key="cust_chat_phone"))
        
        if c_chat_phone.strip():
            st.session_state.active_cust_name = c_chat_name.strip()
            st.session_state.active_cust_phone = c_chat_phone.strip()
            
            st.divider()
            st.markdown("### 💬 Chat Conversation *(Instant Sync)*")
            
            chat_res = supabase.table("messages").select("*").eq("customer_phone", c_chat_phone.strip()).order("id").execute()
            
            for m in chat_res.data:
                sender = m.get('sender', 'Customer')
                msg = m.get('message', '')
                proof = m.get('proof_url')
                
                if sender == "Customer":
                    st.markdown(f"👤 **You** *({m.get('timestamp','')})*:\n> {msg}")
                    if proof and isinstance(proof, str) and proof.startswith("http"):
                        st.image(proof, width=250, caption="Your Uploaded Proof")
                elif sender == "System":
                    st.markdown(f"🤖 **Receipt Notice** *({m.get('timestamp','')})*")
                    st.markdown(msg, unsafe_allow_html=True)
                else:
                    st.markdown(f"🏢 **{sender}** *({m.get('timestamp','')})*:\n> {msg}")
            
            st.divider()
            
            with st.form("customer_chat_form", clear_on_submit=True):
                cust_input_msg = st.text_input("Type message / reply here...", key="cust_chat_input")
                
                cust_proof_file = st.file_uploader("Upload Payment Receipt Screenshot", type=["png", "jpg", "jpeg", "webp"], key="cust_chat_proof")
                
                if st.form_submit_button("📤 Send Message / Upload Payment Proof"):
                    if cust_input_msg.strip() or cust_proof_file is not None:
                        proof_url = upload_image_to_cloudinary(cust_proof_file, folder="sammyreks_payment_proofs") if cust_proof_file else None
                        
                        full_msg = cust_input_msg.strip()
                        if proof_url:
                            full_msg += "\n[Payment Proof Image Attached]"
                            
                        supabase.table("messages").insert({
                            "sender": "Customer",
                            "customer_phone": c_chat_phone.strip(),
                            "customer_name": c_chat_name.strip() or "Customer",
                            "message": full_msg,
                            "proof_url": proof_url,
                            "timestamp": get_now()
                        }).execute()
                        
                        if proof_url:
                            supabase.table("orders").update({"status": "Payment Submitted - Pending Verification"}).eq("contact_phone", c_chat_phone.strip()).execute()
                            
                        st.success("Message sent!")
                        st.rerun()

    # PAGE 4: CUSTOMER SAVED RECEIPTS VAULT
    elif st.session_state.cust_active_page == "📜 My Saved Receipts":
        st.subheader("📜 My Saved Transaction Receipts")
        st.caption("Review your permanently archived bank-style transaction receipts here.")
        
        c_vault_phone = normalize_phone(st.text_input("Enter Your Phone Number to View Receipts", value=st.session_state.active_cust_phone, key="cust_vault_phone"))
        
        if c_vault_phone.strip():
            cust_receipts = supabase.table("saved_receipts").select("*").eq("customer_phone", c_vault_phone.strip()).order("id", desc=True).execute()
            
            if cust_receipts.data and len(cust_receipts.data) > 0:
                for cr in cust_receipts.data:
                    with st.expander(f"🧾 Receipt Ref: [{cr['payment_ref']}] — ₦{float(cr['grand_total']):,.2f} [{cr['timestamp']}]"):
                        try:
                            items_p = json.loads(cr['items_json'])
                            rows_h = "".join([f"<tr><td>{i.get('name')} ({i.get('qty')} x ₦{i.get('price',0):,.2f})</td><td style='text-align:right;'>₦{i.get('total',0):,.2f}</td></tr>" for i in items_p])
                        except Exception:
                            rows_h = f"<tr><td colspan='2'>{cr['items_json']}</td></tr>"

                        st.markdown(f"""
                        <div style="background:#fdfcf7; color:#111; padding:20px; border-radius:6px; border:1px solid #dcd6cd; font-family:'Courier New', Courier, monospace;">
                            <div style="text-align:center; border-bottom:1px dashed #333; padding-bottom:8px; margin-bottom:8px;">
                                <h4 style="margin:0;">{store_title.upper()}</h4>
                                <p style="margin:2px 0; font-size:0.75rem;">VERIFIED TRANSACTION RECEIPT</p>
                            </div>
                            <p style="margin:2px 0; font-size:0.8rem;"><b>Ref:</b> {cr['payment_ref']}</p>
                            <p style="margin:2px 0; font-size:0.8rem;"><b>Gateway:</b> {cr['payment_source']}</p>
                            <p style="margin:2px 0; font-size:0.8rem;"><b>Date:</b> {cr['timestamp']}</p>
                            <hr style="border:0; border-top:1px dashed #333;"/>
                            <table style="width:100%; font-size:0.85rem;">{rows_h}</table>
                            <hr style="border:0; border-top:1px dashed #333;"/>
                            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:1rem;">
                                <span>TOTAL PAID:</span>
                                <span>₦{float(cr['grand_total']):,.2f}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No saved receipts found for this phone number.")

st.sidebar.caption(f"{store_title} v18.3 | {date.today().year}")
