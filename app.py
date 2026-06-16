import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import base64
from io import BytesIO

# ==========================================
# 1. DATABASE SYSTEM & INITIALIZATION
# ==========================================
def init_db():
    # Changed to v5 to allow the new 'items_bought' column to be created without errors
    conn = sqlite3.connect('reks_ultimate_v5.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT UNIQUE, 
        cost REAL, 
        price_carton REAL, 
        price_pack REAL, 
        price_retail REAL,
        qty_cartons INTEGER, 
        packs_per_carton INTEGER, 
        units_per_pack INTEGER,
        shelf TEXT, 
        expiry TEXT, 
        img_data TEXT, 
        description TEXT, 
        timestamp TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        item TEXT, 
        unit_type TEXT, 
        qty INTEGER, 
        total REAL, 
        profit REAL, 
        date TEXT, 
        timestamp TEXT, 
        worker TEXT, 
        customer_name TEXT,
        customer_phone TEXT)''')
        
    # UPDATED: Added items_bought column for evidence
    cursor.execute('''CREATE TABLE IF NOT EXISTS debtors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        customer TEXT, 
        amount REAL, 
        items_bought TEXT, 
        phone TEXT, 
        date TEXT, 
        timestamp TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        category TEXT, 
        amount REAL, 
        note TEXT, 
        date TEXT, 
        timestamp TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        customer TEXT, 
        item TEXT, 
        qty INTEGER, 
        status TEXT DEFAULT 'Pending', 
        contact_phone TEXT,
        total_price REAL,
        date TEXT, 
        timestamp TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT UNIQUE, 
        role TEXT, 
        password TEXT)''')
    
    # SAFETY CHECK: try/except prevents the app from crashing on start
    try:
        cursor.execute("SELECT * FROM workers WHERE name = 'Admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO workers (name, role, password) VALUES (?,?,?)", ("Admin", "CEO", "1234"))
        conn.commit()
    except:
        pass
        
    return conn

conn = init_db()

# ==========================================
# 2. CORE UTILITY FUNCTIONS
# ==========================================
def get_image_base64(uploaded_file):
    if uploaded_file is not None:
        return base64.b64encode(uploaded_file.read()).decode()
    return None

def display_image_base64(base64_str):
    if base64_str:
        try:
            return base64.b64decode(base64_str)
        except:
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

st.sidebar.title("🚀 Reks Pro Portal")
st.sidebar.markdown("---")

if not st.session_state.auth["logged_in"]:
    auth_mode = st.sidebar.selectbox("Choose Portal", ["🛍️ Customer Shop", "🔑 Staff/Admin Login"])
    if auth_mode == "🔑 Staff/Admin Login":
        with st.sidebar.form("login_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                res = pd.read_sql_query("SELECT role FROM workers WHERE name=? AND password=?", conn, params=(user_input, pass_input))
                if not res.empty:
                    st.session_state.auth = {"logged_in": True, "user": user_input, "role": res.iloc[0]['role']}
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")
    view_mode = "CUSTOMER"
else:
    st.sidebar.success(f"Logged in: {st.session_state.auth['user']}")
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
    
    df_alert = pd.read_sql_query("SELECT name, qty_cartons, expiry FROM products", conn)
    for _, row in df_alert.iterrows():
        if row['qty_cartons'] <= 3:
            st.warning(f"⚠️ LOW STOCK: {row['name']} has only {row['qty_cartons']} left.")
        if row['expiry'] and row['expiry'] not in ["None", "", "NoneType"]:
            try:
                exp_dt = datetime.strptime(row['expiry'], '%Y-%m-%d').date()
                if exp_dt <= date.today():
                    st.error(f"❌ EXPIRED: {row['name']} has reached its expiry date ({row['expiry']})!")
            except: pass

    menu = ["📊 Dashboard", "🛒 POS & Sales", "📦 Inventory", "📋 Orders/Requests", "📓 Debtors", "⚙️ Settings"]
    if role == "CEO":
        menu += ["💸 Expenses", "👥 Workers"]
    
    tabs = st.tabs(menu)

    with tabs[0]:
        st.header("Business Analytics")
        df_s = pd.read_sql_query("SELECT * FROM sales", conn)
        df_e = pd.read_sql_query("SELECT * FROM expenses", conn)
        c1, c2, c3, c4 = st.columns(4)
        total_rev = df_s['total'].sum() if not df_s.empty else 0
        total_prof = df_s['profit'].sum() if not df_s.empty else 0
        total_exp = df_e['amount'].sum() if not df_e.empty else 0
        c1.metric("Total Revenue", f"₦{total_rev:,.2f}")
        c2.metric("Total Profit", f"₦{total_prof:,.2f}")
        c3.metric("Total Expenses", f"₦{total_exp:,.2f}")
        c4.metric("Net Cashflow", f"₦{(total_prof - total_exp):,.2f}")
        st.divider()
        st.dataframe(df_s.sort_values('timestamp', ascending=False), use_container_width=True)

    with tabs[1]:
        st.header("New Sale Transaction")
        df_p_pos = pd.read_sql_query("SELECT * FROM products WHERE qty_cartons > 0", conn)
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
                        if sale_unit == "Carton": uc = p['cost']
                        elif sale_unit == "Pack": uc = p['cost'] / p['packs_per_carton']
                        else: uc = (p['cost'] / p['packs_per_carton']) / p['units_per_pack']
                        profit_final = grand_total - (uc * sale_qty)
                        conn.execute("INSERT INTO sales (item, unit_type, qty, total, profit, date, timestamp, worker, customer_name, customer_phone) VALUES (?,?,?,?,?,?,?,?,?,?)", 
                                     (sel_item, sale_unit, sale_qty, grand_total, profit_final, date.today().isoformat(), get_now(), user_logged, c_name_pos, c_phone_pos))
                        if sale_unit == "Carton":
                            conn.execute("UPDATE products SET qty_cartons = qty_cartons - ? WHERE name = ?", (sale_qty, sel_item))
                        conn.commit()
                        st.success("Sale Recorded!")
                        st.rerun()
                
                with col_btn2:
                    if st.button("📓 Record Debt", use_container_width=True):
                        if not c_name_pos:
                            st.error("Customer name required for Debt Evidence!")
                        else:
                            evidence = f"{sale_qty} {sale_unit}(s) of {sel_item}"
                            conn.execute("INSERT INTO debtors (customer, amount, items_bought, phone, date, timestamp) VALUES (?,?,?,?,?,?)", 
                                         (c_name_pos, grand_total, evidence, c_phone_pos, date.today().isoformat(), get_now()))
                            if sale_unit == "Carton":
                                conn.execute("UPDATE products SET qty_cartons = qty_cartons - ? WHERE name = ?", (sale_qty, sel_item))
                            conn.commit()
                            st.warning(f"Debt logged for {c_name_pos}!")
                            st.rerun()

    with tabs[2]:
        st.header("📦 Stock & Warehouse Control")
        df_inv = pd.read_sql_query("SELECT * FROM products", conn)
        
        # Display table - Hide the long 'img_data' column for a cleaner phone view
        st.dataframe(df_inv.drop(columns=['img_data']) if 'img_data' in df_inv.columns else df_inv, use_container_width=True)
        st.divider()
        
        # --- PART 1: ADD OR UPDATE ---
        st.subheader("📝 Add / Update Item")
        action = st.radio("Action", ["Add New Item", "Update Existing Item"], horizontal=True)
        
        if action == "Update Existing Item" and not df_inv.empty:
            target = st.selectbox("Select Item to Update", df_inv['name'])
            curr_data = df_inv[df_inv['name'] == target].iloc[0]
        else:
            curr_data = {"name":"","cost":0.0,"price_carton":0.0,"price_pack":0.0,"price_retail":0.0,"qty_cartons":0,"packs_per_carton":1,"units_per_pack":1,"shelf":"","expiry":str(date.today()),"description":"","img_data":None}
        
        with st.form("inventory_form"):
            ca, cb, cc = st.columns(3)
            with ca:
                n_name = st.text_input("Product Name", value=curr_data['name'])
                n_cost = st.number_input("Cost per Carton", value=float(curr_data['cost']))
                n_shelf = st.text_input("Shelf Location", value=curr_data['shelf'])
            with cb:
                n_pc = st.number_input("Price/Carton", value=float(curr_data['price_carton']))
                n_pp = st.number_input("Price/Pack", value=float(curr_data['price_pack']))
                n_pr = st.number_input("Price/Retail", value=float(curr_data['price_retail']))
            with cc:
                n_stock = st.number_input("Stock (Cartons)", value=int(curr_data['qty_cartons']))
                n_ppc = st.number_input("Packs/Carton", value=int(curr_data['packs_per_carton']))
                n_upp = st.number_input("Units/Pack", value=int(curr_data['units_per_pack']))
            
            n_exp = st.date_input("Expiry Date", value=datetime.strptime(curr_data['expiry'], '%Y-%m-%d').date())
            n_desc = st.text_area("Product Description", value=curr_data['description'])
            n_file = st.file_uploader("Upload Product Photo")
            
            if st.form_submit_button("💾 Save Product Data"):
                img_encoded = get_image_base64(n_file) if n_file else curr_data['img_data']
                conn.execute("""INSERT OR REPLACE INTO products (name, cost, price_carton, price_pack, price_retail, qty_cartons, packs_per_carton, units_per_pack, shelf, expiry, img_data, description, timestamp) 
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (n_name, n_cost, n_pc, n_pp, n_pr, n_stock, n_ppc, n_upp, n_shelf, str(n_exp), img_encoded, n_desc, get_now()))
                conn.commit()
                st.success("Inventory Updated!")
                st.rerun()

        # --- PART 2: DELETE PRODUCT (NEW FEATURE) ---
        st.divider()
        if not df_inv.empty:
            st.subheader("🗑️ Delete Unwanted Product")
            with st.expander("⚠️ Click here to delete a product permanently"):
                delete_target = st.selectbox("Select Item to PERMANENTLY Delete", df_inv['name'], key="del_box")
                st.error(f"Warning: Deleting '{delete_target}' cannot be undone!")
                if st.button(f"Confirm Delete: {delete_target}"):
                    conn.execute("DELETE FROM products WHERE name = ?", (delete_target,))
                    conn.commit()
                    st.success(f"'{delete_target}' has been removed from inventory.")
                    st.rerun()

    with tabs[3]:
        st.header("Order Log")
        df_order_list = pd.read_sql_query("SELECT * FROM orders", conn)
        st.dataframe(df_order_list.sort_values('timestamp', ascending=False), use_container_width=True)
        with st.expander("Update Status"):
            ord_id = st.number_input("Order ID", min_value=1)
            new_st = st.selectbox("Status", ["Pending", "In Progress", "Ready", "Delivered", "Cancelled"])
            if st.button("Update Status Now"):
                conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_st, ord_id))
                conn.commit()
                st.rerun()

    with tabs[4]:
        st.header("📓 Debtors Management")
        
        # 1. FETCH AND DISPLAY DEBTORS
        df_debtors = pd.read_sql_query("SELECT id, customer, items_bought, amount, phone, date FROM debtors", conn)
        st.dataframe(df_debtors, use_container_width=True)
        st.divider()

        # 2. EDIT / CLEAR DEBT SECTION
        if not df_debtors.empty:
            st.subheader("📝 Update or Clear a Debt")
            col_ed1, col_ed2 = st.columns(2)
            
            with col_ed1:
                # Select the ID of the debtor you want to change
                selected_id = st.selectbox("Select Debt ID to Update", df_debtors['id'])
                debt_to_edit = df_debtors[df_debtors['id'] == selected_id].iloc[0]
                
            with col_ed2:
                edit_action = st.radio("What do you want to do?", ["Update Amount", "Mark as Fully Paid (Delete)"])

            if edit_action == "Update Amount":
                with st.form("update_debt_form"):
                    new_amount = st.number_input("New Balance (₦)", value=float(debt_to_edit['amount']))
                    if st.form_submit_button("Update Balance"):
                        conn.execute("UPDATE debtors SET amount = ? WHERE id = ?", (new_amount, selected_id))
                        conn.commit()
                        st.success(f"Balance updated for {debt_to_edit['customer']}!")
                        st.rerun()
            
            else: # Mark as Fully Paid
                if st.button(f"🗑️ Confirm: Clear all debt for {debt_to_edit['customer']}"):
                    conn.execute("DELETE FROM debtors WHERE id = ?", (selected_id,))
                    conn.commit()
                    st.success(f"Debt for {debt_to_edit['customer']} has been cleared!")
                    st.rerun()
        
        st.divider()
        
        # 3. ADD NEW DEBT SECTION (Existing feature)
        st.subheader("➕ Log New Debt")
        with st.form("debt_form"):
            debt_c = st.text_input("Customer Name")
            debt_p = st.text_input("Phone")
            debt_i = st.text_area("Evidence (Items Bought)")
            debt_a = st.number_input("Amount (₦)", 0.0)
            
            if st.form_submit_button("Log New Debt"):
                if debt_c and debt_a > 0:
                    conn.execute("INSERT INTO debtors (customer, amount, items_bought, phone, date, timestamp) VALUES (?,?,?,?,?,?)", 
                                 (debt_c, debt_a, debt_i, debt_p, date.today().isoformat(), get_now()))
                    conn.commit()
                    st.success("New debt logged.")
                    st.rerun()
                else:
                    st.error("Name and Amount are required.")

    with tabs[5]:
        st.header("⚙️ User Settings")
        st.subheader("Change Your Password")
        with st.form("change_pass_form"):
            old_p = st.text_input("Current Password", type="password")
            new_p = st.text_input("New Password", type="password")
            confirm_p = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Password"):
                verify = pd.read_sql_query("SELECT * FROM workers WHERE name=? AND password=?", conn, params=(user_logged, old_p))
                if verify.empty:
                    st.error("Current password is incorrect.")
                elif new_p != confirm_p:
                    st.error("New passwords do not match.")
                elif len(new_p) < 4:
                    st.error("Password too short (min 4 characters).")
                else:
                    conn.execute("UPDATE workers SET password=? WHERE name=?", (new_p, user_logged))
                    conn.commit()
                    st.success("Password updated successfully!")

    if role == "CEO":
        with tabs[6]:
            st.header("Expenditure Log")
            st.dataframe(pd.read_sql_query("SELECT * FROM expenses", conn), use_container_width=True)
            with st.form("expense_entry"):
                ex_cat, ex_val, ex_note = st.selectbox("Category", ["Salaries", "Rent", "Utility", "Stocking", "Fuel", "Other"]), st.number_input("Amount", 0.0), st.text_input("Note")
                if st.form_submit_button("Record Expense"):
                    conn.execute("INSERT INTO expenses (category, amount, note, date, timestamp) VALUES (?,?,?,?,?)", (ex_cat, ex_val, ex_note, date.today().isoformat(), get_now()))
                    conn.commit(); st.rerun()

        with tabs[7]:
            st.header("Staff Management")
            df_workers = pd.read_sql_query("SELECT id, name, role FROM workers", conn)
            st.dataframe(df_workers, use_container_width=True)
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.subheader("Add New Worker")
                with st.form("worker_add"):
                    w_n, w_r, w_p = st.text_input("Worker Name"), st.selectbox("Role", ["Staff", "CEO"]), st.text_input("Set Password", type="password")
                    if st.form_submit_button("Create Account"):
                        try:
                            conn.execute("INSERT INTO workers (name, role, password) VALUES (?,?,?)", (w_n, w_r, w_p))
                            conn.commit(); st.rerun()
                        except: st.error("Worker exists.")
            with col_w2:
                st.subheader("Reset Worker Password")
                with st.form("worker_reset"):
                    target_worker = st.selectbox("Select Worker", df_workers['name'])
                    new_reset_p = st.text_input("New Temporary Password", type="password")
                    if st.form_submit_button("Reset Password"):
                        conn.execute("UPDATE workers SET password=? WHERE name=?", (new_reset_p, target_worker))
                        conn.commit()
                        st.success(f"Password for {target_worker} reset successfully.")

# ==========================================
# 5. CUSTOMER PORTAL
# ==========================================
else:
    st.title("🛒 Reks Customer Portal")
    c_tab1, c_tab2, c_tab3 = st.tabs(["🛍️ Shop Now", "📝 Special Request", "🔍 Track My Order"])
    
    with c_tab2:
        st.subheader("Can't find what you need?")
        with st.form("custom_order_form", clear_on_submit=True):
            cust_n = st.text_input("Your Full Name")
            cust_p = st.text_input("Your Phone Number")
            cust_i = st.text_input("Item Requested")
            cust_q = st.number_input("Quantity Needed", min_value=1)
            if st.form_submit_button("🚀 Submit Request"):
                if cust_n and cust_i and cust_p:
                    conn.execute("INSERT INTO orders (customer, item, qty, status, contact_phone, date, timestamp) VALUES (?,?,?,?,?,?,?)", 
                                 (cust_n, f"SPECIAL: {cust_i}", cust_q, "Pending", cust_p, date.today().isoformat(), get_now()))
                    conn.commit()
                    st.success("✅ Request logged! We will contact you soon.")
                else: st.error("Please fill all fields.")

    with c_tab3:
        st.subheader("Check your order status")
        track_phone = st.text_input("Enter the Phone Number used to order")
        if track_phone:
            track_df = pd.read_sql_query("SELECT item, qty, status, date FROM orders WHERE contact_phone = ?", conn, params=(track_phone,))
            if not track_df.empty:
                st.table(track_df)
            else:
                st.info("No orders found for this number.")

    with c_tab1:
        col_search1, col_search2 = st.columns([2, 1])
        with col_search1:
            search_query = st.text_input("🔍 Search for products...", placeholder="Enter product name...")
        with col_search2:
            st.write(f"Today's Date: {date.today()}")

        df_shop = pd.read_sql_query("SELECT * FROM products WHERE qty_cartons > 0", conn)
        if search_query:
            df_shop = df_shop[df_shop['name'].str.contains(search_query, case=False)]

        if not df_shop.empty:
            for index, s_row in df_shop.iterrows():
                with st.container():
                    col_img, col_info, col_order = st.columns([1, 2, 1.5])
                    with col_img:
                        img_bytes = display_image_base64(s_row['img_data'])
                        if img_bytes: st.image(img_bytes, width=150)
                        else: st.info("No Image")
                    with col_info:
                        st.subheader(s_row['name'])
                        st.write(s_row['description'])
                        st.caption(f"Location: {s_row['shelf']}")
                    with col_order:
                        unit_choice = st.selectbox("Select Unit", ["Retail", "Pack", "Carton"], key=f"unit_{s_row['id']}")
                        qty_choice = st.number_input("Qty", min_value=1, key=f"qty_{s_row['id']}")
                        price = s_row['price_retail'] if unit_choice == "Retail" else (s_row['price_pack'] if unit_choice == "Pack" else s_row['price_carton'])
                        total_calc = price * qty_choice
                        if st.button(f"🛒 Order - ₦{total_calc:,.2f}", key=f"btn_{s_row['id']}"):
                            st.warning("Final Step: Enter your details below to confirm.")
                            with st.form(f"confirm_{s_row['id']}"):
                                c_phone = st.text_input("Phone Number")
                                c_name = st.text_input("Name")
                                if st.form_submit_button("Confirm Order"):
                                    conn.execute("INSERT INTO orders (customer, item, qty, status, contact_phone, total_price, date, timestamp) VALUES (?,?,?,?,?,?,?,?)", 
                                                 (c_name, f"{s_row['name']} ({unit_choice})", qty_choice, "Order Placed", c_phone, total_calc, date.today().isoformat(), get_now()))
                                    conn.commit()
                                    st.success(f"✅ Success! Your order for {s_row['name']} has been sent.")
                    st.divider()
        else:
            st.warning("No products found.")

st.sidebar.caption(f"Reks Ultimate v5.0 | {date.today().year}")



can you update the image upload to copy and paste rather than upload from file alone
