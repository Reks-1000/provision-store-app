import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import base64
from io import BytesIO
from PIL import Image

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

# AUTO-INITIALIZE DEFAULT ADMIN USER IF TABLE IS EMPTY
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
# 2. CORE UTILITY FUNCTIONS
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
            img.save(buffered, format="JPEG", quality=75)
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

# ==========================================
# 3. UI CONFIGURATION & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Reks Enterprise Ultimate", layout="wide", page_icon="🛍️")

if 'auth' not in st.session_state:
    st.session_state.auth = {"logged_in": False, "user": None, "role": None}

st.sidebar.title("🚀 Reks Pro Cloud Portal")
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
                        res = supabase.table("workers").select("role, name").ilike("name", user_input).eq("password", pass_input).execute()
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
                            check_user = supabase.table("workers").select("name").ilike("name", user_input).execute()
                            if not check_user.data:
                                st.error(f"User '{user_input}' does not exist in database.")
                            else:
                                st.error("Incorrect password.")
                    except Exception as e:
                        st.error(f"Login system error: {e}")
    view_mode = "CUSTOMER"
else:
    st.sidebar.success(f"Logged in: {st.session_state.auth['user']} ({st.session_state.auth['role']})")
    if st.sidebar.button("Logout"):
        st.session_state.auth = {"logged_in": False, "user": None, "role": None}
        st.rerun()
    view_mode = "STAFF"

# ==========================================
# 4. STAFF & CEO DASHBOARD (INTERNAL)
# ==========================================
if view_mode == "STAFF":
    role = st.session_state.auth["role"]
    user_logged = st.session_state.auth["user"]
    
    df_alert = fetch_dataframe("products")
    if not df_alert.empty:
        for _, row in df_alert.iterrows():
            if row.get('qty_cartons', 0) <= 3:
                st.warning(f"⚠️ LOW STOCK: {row['name']} has only {row['qty_cartons']} left.")
            if row.get('expiry') and row['expiry'] not in ["None", "", "NoneType"]:
                try:
                    exp_dt = datetime.strptime(row['expiry'], '%Y-%m-%d').date()
                    if exp_dt <= date.today():
                        st.error(f"❌ EXPIRED: {row['name']} reached its expiry date ({row['expiry']})!")
                except Exception:
                    pass

    menu = ["📊 Dashboard", "🛒 POS & Sales", "📦 Inventory", "📋 Orders/Requests", "💬 Customer Chats", "📓 Debtors", "⚙️ Settings"]
    if role == "CEO":
        menu += ["💸 Expenses", "👥 Workers"]
    
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
            res_pos = supabase.table("products").select("*").gt("qty_cartons", 0).execute()
            df_p_pos = pd.DataFrame(res_pos.data) if res_pos.data else pd.DataFrame()
        except Exception:
            df_p_pos = pd.DataFrame()
            
        if not df_p_pos.empty:
            col_pos1, col_pos2 = st.columns([2, 1])
            with col_pos1:
                sel_item = st.selectbox("Search & Select Item", df_p_pos['name'])
                p = df_p_pos[df_p_pos['name'] == sel_item].iloc[0]
                sale_unit = st.radio("Selling Unit", ["Carton", "Pack", "Retail Unit"])
                sale_qty = st.number_input("Quantity", min_value=1, value=1)
                c_name_pos = st.text_input("Customer Name")
                c_phone_pos = st.text_input("Customer Phone Number")
            with col_pos2:
                up = p['price_carton'] if sale_unit == "Carton" else (p['price_pack'] if sale_unit == "Pack" else p['price_retail'])
                grand_total = up * sale_qty
                st.subheader(f"Total: ₦{grand_total:,.2f}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🏁 Cash Sale", use_container_width=True):
                        packs_per_c = p.get('packs_per_carton', 1) or 1
                        units_per_p = p.get('units_per_pack', 1) or 1
                        
                        if sale_unit == "Carton":
                            uc = p['cost']
                            cartons_deducted = sale_qty
                        elif sale_unit == "Pack":
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
                        supabase.table("products").update({"qty_cartons": new_qty}).eq("name", sel_item).execute()
                            
                        st.success("Sale Recorded permanently!")
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
                            if sale_unit == "Carton":
                                cartons_deducted = sale_qty
                            elif sale_unit == "Pack":
                                cartons_deducted = sale_qty / packs_per_c
                            else:
                                cartons_deducted = sale_qty / (packs_per_c * units_per_p)
                                
                            new_qty = float(p['qty_cartons'] - cartons_deducted)
                            supabase.table("products").update({"qty_cartons": new_qty}).eq("name", sel_item).execute()
                                
                            st.warning(f"Debt logged for {c_name_pos}!")
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
            curr_data = {"name":"","cost":0.0,"price_carton":0.0,"price_pack":0.0,"price_retail":0.0,"qty_cartons":0,"packs_per_carton":1,"units_per_pack":1,"shelf":"","expiry":str(date.today()),"description":"","img_data":None,"video_url":"","video_data":None}
        
        st.write("📷 **Product Image Input**")
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
                    st.image(chosen_image, caption="Pasted Image Preview", width=120)
            except Exception:
                st.info("Paste from clipboard component not available.")

        st.divider()
        st.write("🎥 **Product Video Advert Input**")
        vid_file = st.file_uploader("Upload Direct MP4 Video File (Max 10MB)", type=["mp4", "mov", "webm"])

        with st.form("inventory_form"):
            # FLEXIBLE PACKAGING SELECTOR (Editable labels / unbundled items)
            st.info("💡 **Packaging Setup**: If your product is not sold in cartons, select your packaging type below or adjust the quantity labels.")
            pkg_mode = st.radio("Primary Packaging Unit", ["Standard Carton / Box", "Bundle / Pack Only", "Loose Pieces / Units Only"], horizontal=True)

            ca, cb, cc = st.columns(3)
            with ca:
                n_name = st.text_input("Product Name", value=str(curr_data['name'])).strip()
                n_cost = st.number_input("Cost Price (Per Main Unit)", value=float(curr_data.get('cost', 0.0)))
                n_shelf = st.text_input("Shelf Location", value=str(curr_data.get('shelf', '')))
            with cb:
                n_pc = st.number_input("Price (Per Carton / Main Unit)", value=float(curr_data.get('price_carton', 0.0)))
                n_pp = st.number_input("Price (Per Pack)", value=float(curr_data.get('price_pack', 0.0)))
                n_pr = st.number_input("Price (Retail / Single Unit)", value=float(curr_data.get('price_retail', 0.0)))
            with cc:
                n_stock = st.number_input("Total Stock Quantity", value=float(curr_data.get('qty_cartons', 0)))
                
                # Dynamic labels depending on packaging mode
                if pkg_mode == "Standard Carton / Box":
                    n_ppc = st.number_input("Packs per Carton", value=int(curr_data.get('packs_per_carton', 1)), min_value=1)
                    n_upp = st.number_input("Units per Pack", value=int(curr_data.get('units_per_pack', 1)), min_value=1)
                elif pkg_mode == "Bundle / Pack Only":
                    n_ppc = st.number_input("Packs / Bundle Count", value=int(curr_data.get('packs_per_carton', 1)), min_value=1)
                    n_upp = st.number_input("Units per Pack", value=int(curr_data.get('units_per_pack', 1)), min_value=1)
                else:
                    n_ppc = 1
                    n_upp = 1
                    st.caption("Unit-only mode: Packs & Units locked to 1.")
            
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
                            return 0.0 if (pd.isna(f) or f != f) else f
                        except Exception:
                            return 0.0

                    def safe_int(val):
                        try:
                            f = float(val)
                            return 0 if (pd.isna(f) or f != f) else int(f)
                        except Exception:
                            return 0

                    # Unicode safe encoding to handle emojis/symbols without crashing JSON
                    safe_name = str(n_name).encode('utf-8', 'ignore').decode('utf-8').strip()
                    safe_desc = str(n_desc).encode('utf-8', 'ignore').decode('utf-8').strip() if n_desc else ""

                    img_encoded = get_image_base64(chosen_image) if chosen_image else curr_data.get('img_data')
                    video_encoded = get_file_base64(vid_file) if vid_file else curr_data.get('video_data')
                    
                    prod_payload = {
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
                        "timestamp": get_now()
                    }
                    
                    try:
                        if action == "Update Existing Item":
                            supabase.table("products").update(prod_payload).eq("name", target).execute()
                            st.success(f"Updated '{safe_name}' successfully!")
                        else:
                            supabase.table("products").insert(prod_payload).execute()
                            st.success(f"Added '{safe_name}' to inventory!")
                        st.rerun()
                    except Exception as save_error:
                        if "duplicate key value" in str(save_error) or "23505" in str(save_error):
                            st.error(f"A product named '{safe_name}' already exists. Switch action to 'Update Existing Item' to edit it.")
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

    # TAB 3: ORDER LOG
    with tabs[3]:
        st.header("Order Log")
        df_order_list = fetch_dataframe("orders")
        if not df_order_list.empty:
            st.dataframe(df_order_list.sort_values('timestamp', ascending=False), use_container_width=True, hide_index=True)
        with st.expander("Update Status"):
            ord_id = st.number_input("Order ID", min_value=1, step=1)
            new_st = st.selectbox("Status", ["Pending", "In Progress", "Ready", "Delivered", "Cancelled"])
            if st.button("Update Status Now"):
                supabase.table("orders").update({"status": new_st}).eq("id", ord_id).execute()
                st.rerun()

    # TAB 4: CUSTOMER CHATS (STAFF SIDE)
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
            debt_p = st.text_input("Phone")
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
        st.header("⚙️ User Settings")
        st.subheader("Change Your Password")
        with st.form("change_pass_form"):
            old_p = st.text_input("Current Password", type="password")
            new_p = st.text_input("New Password", type="password")
            confirm_p = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Password"):
                verify = supabase.table("workers").select("*").ilike("name", user_logged).eq("password", old_p).execute()
                if not verify.data:
                    st.error("Current password is incorrect.")
                elif new_p != confirm_p:
                    st.error("New passwords do not match.")
                elif len(new_p) < 4:
                    st.error("Password too short.")
                else:
                    supabase.table("workers").update({"password": new_p}).ilike("name", user_logged).execute()
                    st.success("Password updated securely in cloud database!")

    # CEO TABS
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
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.subheader("Add New Worker")
                with st.form("worker_add"):
                    w_n = st.text_input("Worker Name")
                    w_r = st.selectbox("Role", ["Staff", "CEO"])
                    w_p = st.text_input("Set Password", type="password")
                    if st.form_submit_button("Create Account"):
                        try:
                            supabase.table("workers").insert({"name": w_n, "role": w_r, "password": w_p}).execute()
                            st.rerun()
                        except Exception:
                            st.error("Worker exists or entry error.")
            with col_w2:
                st.subheader("Reset Worker Password")
                with st.form("worker_reset"):
                    target_worker = st.selectbox("Select Worker", df_workers['name']) if not df_workers.empty else st.selectbox("Select Worker", ["None"])
                    new_reset_p = st.text_input("New Temporary Password", type="password")
                    if st.form_submit_button("Reset Password"):
                        supabase.table("workers").update({"password": new_reset_p}).ilike("name", target_worker).execute()
                        st.success("Password reset successfully.")

# ==========================================
# 5. CUSTOMER PORTAL
# ==========================================
else:
    st.title("🛒 Reks Customer Portal")
    c_tab1, c_tab2, c_tab3, c_tab4 = st.tabs(["🛍️ Shop Now", "📝 Special Request", "🔍 Track My Order", "💬 Chat with Us"])
    
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

    # TAB 4: CUSTOMER CHAT (CUSTOMER SIDE)
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

    # CUSTOMER SHOPPING SECTION
    with c_tab1:
        col_search1, col_search2 = st.columns([2, 1])
        with col_search1:
            search_query = st.text_input("🔍 Search for products...", placeholder="Enter product name...")
        with col_search2:
            st.write(f"Today's Date: {date.today()}")

        try:
            res_shop = supabase.table("products").select("*").gt("qty_cartons", 0).execute()
            df_shop = pd.DataFrame(res_shop.data) if res_shop.data else pd.DataFrame()
        except Exception:
            df_shop = pd.DataFrame()
            
        if search_query and not df_shop.empty:
            df_shop = df_shop[df_shop['name'].str.contains(search_query, case=False)]

        if not df_shop.empty:
            for index, s_row in df_shop.iterrows():
                with st.container():
                    col_img, col_info, col_order = st.columns([1, 2, 1.5])
                    with col_img:
                        img_bytes = display_image_base64(s_row.get('img_data'))
                        if img_bytes:
                            st.image(img_bytes, width=150)
                        else:
                            st.info("No Image")
                    with col_info:
                        st.subheader(s_row['name'])
                        st.write(s_row.get('description', ''))
                        st.caption(f"Location: {s_row.get('shelf', 'N/A')}")
                        
                        # IN-APP DIRECT VIDEO ADVERT PLAYER
                        has_direct_vid = s_row.get('video_data') and str(s_row['video_data']).strip() not in ["None", "", "nan"]
                        has_url_vid = s_row.get('video_url') and str(s_row['video_url']).strip() not in ["None", "", "nan"]

                        if has_direct_vid or has_url_vid:
                            with st.expander("🎥 Watch Product Video Advert"):
                                if has_direct_vid:
                                    vid_bytes = base64.b64decode(s_row['video_data'])
                                    st.video(vid_bytes)
                                elif has_url_vid:
                                    st.video(s_row['video_url'])
                                
                    with col_order:
                        unit_choice = st.selectbox("Select Unit", ["Retail", "Pack", "Carton"], key=f"unit_{s_row['id']}")
                        qty_choice = st.number_input("Qty", min_value=1, key=f"qty_{s_row['id']}")
                        
                        price = s_row['price_retail'] if unit_choice == "Retail" else (s_row['price_pack'] if unit_choice == "Pack" else s_row['price_carton'])
                        total_calc = price * qty_choice
                        
                        # POPOVER MODAL FOR PLACING ORDERS
                        with st.popover(f"🛒 Order - ₦{total_calc:,.2f}"):
                            st.subheader(f"Confirm Order for {s_row['name']}")
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
            st.warning("No products found.")

st.sidebar.caption(f"Reks Ultimate Cloud v5.0 | {date.today().year}")
