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
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api

# ==========================================
# 1. DATABASE & STORAGE INITIALIZATION
# ==========================================
@st.cache_resource
def init_connection():
    url = os.getenv("SUPABASE_URL") or (st.secrets["SUPABASE_URL"] if "SUPABASE_URL" in st.secrets else None)
    key = os.getenv("SUPABASE_KEY") or (st.secrets["SUPABASE_KEY"] if "SUPABASE_KEY" in st.secrets else None)
    
    if not url or not key:
        st.error("Database credentials missing! Please configure SUPABASE_URL and SUPABASE_KEY.")
        st.stop()
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()

# Initialize Cloudinary Configuration
try:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME") or (st.secrets["CLOUDINARY_CLOUD_NAME"] if "CLOUDINARY_CLOUD_NAME" in st.secrets else None),
        api_key=os.getenv("CLOUDINARY_API_KEY") or (st.secrets["CLOUDINARY_API_KEY"] if "CLOUDINARY_API_KEY" in st.secrets else None),
        api_secret=os.getenv("CLOUDINARY_API_SECRET") or (st.secrets["CLOUDINARY_API_SECRET"] if "CLOUDINARY_API_SECRET" in st.secrets else None),
        secure=True
    )
except Exception as e:
    st.error(f"Cloudinary configuration missing! Error: {e}")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit() or c == '+').strip()

# ==========================================
# 2. HIGH-PERFORMANCE CACHED DATA LAYER
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_dataframe_cached(table_name):
    """Caches table data in memory for 5 minutes to eliminate network lag on clicks."""
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def fetch_dataframe_fresh(table_name):
    """Bypasses cache when instant fresh data is strictly required after an update."""
    try:
        response = supabase.table(table_name).select("*").execute()
        if response.data and len(response.data) > 0:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

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
                file_bytes, folder=folder, resource_type="image",
                transformation=[{"width": 600, "height": 600, "crop": "limit"}, {"quality": "auto", "fetch_format": "auto"}]
            )
            return upload_result.get("secure_url")
        except Exception as e:
            st.error(f"Cloudinary upload error: {e}")
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
    return f"https://wa.me/{clean_phone}?text={encoded_msg}" if clean_phone else f"https://wa.me/?text={encoded_msg}"

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sanitize_payload(payload):
    cleaned = {}
    for k, v in payload.items():
        if v is None:
            cleaned[k] = 0 if k in ['qty_cartons', 'packs_per_carton', 'units_per_pack'] else (0.0 if k in ['cost', 'price_carton', 'price_pack', 'price_retail'] else "")
        elif isinstance(v, float):
            cleaned[k] = 0.0 if (math.isnan(v) or math.isinf(v) or pd.isna(v)) and k in ['cost', 'price_carton', 'price_pack', 'price_retail'] else v
        else:
            cleaned[k] = v
    return cleaned

# ==========================================
# 3. UI CONFIGURATION & FINTECH STYLING
# ==========================================
st.set_page_config(page_title="Sammyreks Business Center", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
        .stButton>button {
            font-size: 1.1rem !important;
            font-weight: bold !important;
            padding: 10px 14px !important;
            border-radius: 8px !important;
            background-color: #0d47a1;
            color: white;
            border: none;
            width: 100%;
        }
        .stButton>button:hover {
            background-color: #1565c0;
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
                if user_input.lower() == "admin" and pass_input == "Sammyreks2026!":
                    st.session_state.auth = {"logged_in": True, "user": "admin", "role": "CEO"}
                    st.success("Welcome back, admin!")
                    st.rerun()
                else:
                    try:
                        hashed_attempt = hash_password(pass_input)
                        res = supabase.table("workers").select("role, name").ilike("name", user_input).eq("password", hashed_attempt).limit(1).execute()
                        if res.data and len(res.data) > 0:
                            matched_user = res.data[0]
                            st.session_state.auth = {"logged_in": True, "user": matched_user['name'], "role": matched_user['role']}
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
        "📊 Dashboard", "💳 POS & Sales", "📦 Inventory", 
        "💬 Live Chat", "📜 Vault", "📓 Debtors", "⚙️ Settings", "💸 Expenses", "👥 Workers"
    ]
    tabs = st.tabs(tab_titles)

    # TAB 0: DASHBOARD
    with tabs[0]:
        st.header("📊 Business Analytics")
        df_s = fetch_dataframe_cached("sales")
        df_e = fetch_dataframe_cached("expenses")
        
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
                
                sale_unit = st.radio("Selling Unit", [m_label, p_label, r_label], key="pos_sale_unit", horizontal=True)
                sale_qty = st.number_input("Quantity", min_value=1, value=1, key="pos_sale_qty")
                c_name_pos = st.text_input("Customer Name", key="pos_cust_name")
                c_phone_pos = normalize_phone(st.text_input("Customer Phone Number", key="pos_cust_phone"))
                pay_source_pos = st.selectbox("Payment Gateway", ["Moniepoint MFB", "OPay", "Access Bank", "Cash", "Transfer"], key="pos_pay_source")
            with col_pos2:
                up = p['price_carton'] if sale_unit == m_label else (p['price_pack'] if sale_unit == p_label else p['price_retail'])
                grand_total = up * sale_qty
                st.subheader(f"Total: ₦{grand_total:,.2f}")
                
                if st.button("🏁 Process Sale & Save Receipt", use_container_width=True, key="pos_cash_btn"):
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
                        "payment_ref": pos_ref, "customer_name": c_name_pos or "Walk-in Customer",
                        "customer_phone": c_phone_pos or "N/A", "items_json": json.dumps(sold_item_entry),
                        "grand_total": float(grand_total), "payment_source": pay_source_pos,
                        "cashier": user_logged, "timestamp": get_now()
                    }).execute()

                    supabase.table("sales").insert({
                        "item": f"{sel_item} ({sale_qty} {sale_unit})", "unit_type": sale_unit, "qty": int(sale_qty),
                        "total": float(grand_total), "profit": float(profit_final), "date": date.today().isoformat(),
                        "timestamp": get_now(), "worker": user_logged, "customer_name": c_name_pos, "customer_phone": c_phone_pos,
                        "payment_source": pay_source_pos, "payment_ref": pos_ref
                    }).execute()
                    
                    new_qty = float(p['qty_cartons'] - cartons_deducted)
                    supabase.table("products").update({"qty_cartons": new_qty}).eq("id", int(p['id'])).execute()
                    st.cache_data.clear()
                        
                    st.session_state.last_receipt = {
                        "type": "Official Sales Receipt", "customer": c_name_pos or "Walk-in Customer",
                        "phone": c_phone_pos or "N/A", "date": get_now(), "sold_items": sold_item_entry,
                        "grand_total": grand_total, "cashier": user_logged, "payment_source": pay_source_pos, "payment_ref": pos_ref
                    }
                    st.success("Sale Recorded Successfully!")
                    st.rerun()

        if st.session_state.last_receipt:
            st.markdown("---")
            rec = st.session_state.last_receipt
            sold_items_list = rec.get('sold_items', [])
            receipt_rows = "".join([f"<tr><td><b>{i.get('name')}</b> ({i.get('qty')} {i.get('unit')})</td><td style='text-align:right;'>₦{i.get('total'):,.2f}</td></tr>" for i in sold_items_list])
            
            st.markdown(f"""
            <div style="background:#fdfcf7; color:#111; padding:20px; border:1px solid #dcd6cd; font-family:'Courier New', monospace; max-width:400px; margin:auto;">
                <h3 style="text-align:center; margin:0;">{store_title.upper()}</h3>
                <p style="text-align:center; font-size:0.75rem;">REF: {rec.get('payment_ref')}</p>
                <hr style="border-top:1px dashed #333;"/>
                <table style="width:100%; font-size:0.85rem;">{receipt_rows}</table>
                <hr style="border-top:1px dashed #333;"/>
                <div style="display:flex; justify-content:space-between; font-weight:bold;">
                    <span>TOTAL:</span><span>₦{rec.get('grand_total'):,.2f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            wa_url = generate_whatsapp_link(rec.get('phone'), rec.get('type'), rec.get('customer'), sold_items_list, rec.get('grand_total'))
            st.markdown(f'<a href="{wa_url}" target="_blank"><button style="background-color:#25d366; color:white; padding:10px; border:none; border-radius:8px; font-weight:bold; width:100%; margin-top:10px;">💬 Send Receipt via WhatsApp</button></a>', unsafe_allow_html=True)
            if st.button("Close Receipt"):
                st.session_state.last_receipt = None
                st.rerun()

    # TAB 2: INVENTORY
    with tabs[2]:
        st.header("📦 Inventory Control")
        df_inv = fetch_dataframe_cached("products")
        if not df_inv.empty:
            st.dataframe(df_inv.drop(columns=['img_data'], errors='ignore'), use_container_width=True, hide_index=True)

    # TAB 3: LIVE CHATS
    with tabs[3]:
        st.header("💬 Live Customer Chats")
        res_msg = supabase.table("messages").select("customer_phone, customer_name").execute()
        if res_msg.data:
            threads = {f"{m.get('customer_name')} ({m.get('customer_phone')})": m.get('customer_phone') for m in res_msg.data if m.get('customer_phone')}
            if threads:
                sel_th = st.selectbox("Select Chat Thread", list(threads.keys()))
                ph = threads[sel_th]
                msgs = supabase.table("messages").select("*").eq("customer_phone", ph).order("id").execute()
                for m in msgs.data:
                    st.markdown(f"**{m.get('sender')}**: {m.get('message')}")
                
                with st.form("staff_chat_reply"):
                    reply = st.text_input("Reply message...")
                    if st.form_submit_button("Send"):
                        if reply:
                            supabase.table("messages").insert({"sender": f"Staff ({user_logged})", "customer_phone": ph, "customer_name": sel_th.split(" (")[0], "message": reply, "timestamp": get_now()}).execute()
                            st.rerun()

    # TAB 4: VAULT
    with tabs[4]:
        st.header("📜 Saved Receipts Vault")
        df_v = fetch_dataframe_fresh("saved_receipts")
        if not df_v.empty:
            st.dataframe(df_v, use_container_width=True, hide_index=True)

    # TAB 5: DEBTORS
    with tabs[5]:
        st.header("📓 Debtors Management")
        df_d = fetch_dataframe_fresh("debtors")
        if not df_d.empty:
            st.dataframe(df_d, use_container_width=True, hide_index=True)

    # TAB 6: SETTINGS
    with tabs[6]:
        st.header("⚙️ Settings")

    # TAB 7: EXPENSES
    with tabs[7]:
        st.header("💸 Expenses")

    # TAB 8: WORKERS
    with tabs[8]:
        st.header("👥 Workers Management")

# ==========================================
# 5. CUSTOMER SHOP PORTAL
# ==========================================
else:
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #0d47a1, #1565c0); padding: 18px; border-radius: 12px; color: white; text-align: center; margin-bottom: 15px;">
            <h1 style="margin:0; font-size: 1.8rem;">⚡ {store_title}</h1>
            <p style="margin: 4px 0 0 0;">Fast Mobile Fintech Shop</p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🛒 Shop & Cart", use_container_width=True):
            st.session_state.cust_active_page = "Shop"
            st.rerun()
    with c2:
        if st.button("💬 Live Chat", use_container_width=True):
            st.session_state.cust_active_page = "Chat"
            st.rerun()

    cart_total = sum([i['total_price'] for i in st.session_state.cart])

    if st.session_state.cust_active_page == "Shop":
        st.info(f"🛒 Cart Items: {len(st.session_state.cart)} | Total: ₦{cart_total:,.2f}")
        if len(st.session_state.cart) > 0:
            with st.form("checkout_form"):
                c_name = st.text_input("Full Name", value=st.session_state.active_cust_name)
                c_phone = normalize_phone(st.text_input("Phone Number", value=st.session_state.active_cust_phone))
                if st.form_submit_button("🚀 Submit Order"):
                    if c_name and c_phone:
                        st.session_state.active_cust_name = c_name
                        st.session_state.active_cust_phone = c_phone
                        ref = f"SRK-{random.randint(1000,9999)}"
                        for item in st.session_state.cart:
                            supabase.table("orders").insert({
                                "customer": c_name, "item": item['name'], "qty": item['qty'],
                                "status": "Pending", "contact_phone": c_phone, "total_price": item['total_price'],
                                "payment_ref": ref, "date": date.today().isoformat(), "timestamp": get_now()
                            }).execute()
                        st.session_state.cart = []
                        st.success(f"Order sent! Ref: {ref}")
                        st.rerun()

        df_shop = fetch_dataframe_cached("products")
        if not df_shop.empty:
            search = st.text_input("🔍 Search products...")
            if search:
                df_shop = df_shop[df_shop['name'].str.contains(search, case=False)]
            for _, row in df_shop.iterrows():
                col_i, col_d = st.columns([1, 2])
                with col_i:
                    if row.get('img_data'):
                        st.image(row['img_data'], width=90)
                with col_d:
                    st.write(f"**{row['name']}**")
                    price = row['price_retail']
                    st.write(f"₦{price:,.2f}")
                    if st.button("Add to Cart", key=f"add_{row['id']}"):
                        st.session_state.cart.append({"name": row['name'], "qty": 1, "total_price": price})
                        st.success("Added!")
                        st.rerun()
                st.divider()

    elif st.session_state.cust_active_page == "Chat":
        st.subheader("Live Support Chat")
        phone = normalize_phone(st.text_input("Enter Phone Number", value=st.session_state.active_cust_phone))
        if phone:
            st.session_state.active_cust_phone = phone
            msgs = supabase.table("messages").select("*").eq("customer_phone", phone).execute()
            for m in msgs.data:
                st.markdown(f"**{m.get('sender')}**: {m.get('message')}")
            with st.form("cust_msg", clear_on_submit=True):
                txt = st.text_input("Type message...")
                if st.form_submit_button("Send"):
                    if txt:
                        supabase.table("messages").insert({"sender": "Customer", "customer_phone": phone, "message": txt, "timestamp": get_now()}).execute()
                        st.rerun()
