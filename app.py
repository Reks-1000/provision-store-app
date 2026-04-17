import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. AUTO-REPAIR ENGINE (SELF-HEALING) ---
def init_db():
    with sqlite3.connect('provision_store.db') as conn:
        cursor = conn.cursor()
        # Create Products table
        cursor.execute('''CREATE TABLE IF NOT EXISTS products 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, 
             cost_price REAL, selling_price REAL, stock_quantity INTEGER)''')
        # Create Sales table
        cursor.execute('''CREATE TABLE IF NOT EXISTS sales_log 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT, 
             quantity INTEGER, total_amount REAL, profit REAL, 
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        # Create Admin User
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
            (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
        cursor.execute("INSERT OR IGNORE INTO users VALUES ('admin', 'reks123', 'Admin')")
        conn.commit()

init_db()

# --- 2. DATABASE HELPER ---
def run_query(query, params=(), is_select=True):
    with sqlite3.connect('provision_store.db') as conn:
        if is_select:
            return pd.read_sql_query(query, conn, params=params)
        else:
            conn.execute(query, params)
            conn.commit()

# --- 3. LOGIN INTERFACE ---
if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🛡️ Reks Enterprise System")
    user = st.text_input("Admin Username")
    pw = st.text_input("Password", type="password")
    if st.button("Unlock System"):
        res = run_query("SELECT * FROM users WHERE username=? AND password=?", (user, pw))
        if not res.empty:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Access Denied: Invalid Key")
    st.stop()

# --- 4. MAIN DASHBOARD ---
st.sidebar.title("Shop Control")
page = st.sidebar.selectbox("Navigate", ["🛒 Counter (Sales)", "📊 Financials", "📦 Warehouse"])

if page == "🛒 Counter (Sales)":
    st.header("Point of Sale")
    items = run_query("SELECT name FROM products")
    
    if items.empty:
        st.info("Your warehouse is empty. Add products in the 'Warehouse' tab.")
    else:
        selection = st.selectbox("Select Item", items['name'])
        qty = st.number_input("Quantity", min_value=1, value=1)
        
        if st.button("Confirm Sale"):
            p = run_query("SELECT * FROM products WHERE name=?", (selection,)).iloc[0]
            total = p['selling_price'] * qty
            profit = (p['selling_price'] - p['cost_price']) * qty
            
            # Update Database
            run_query("INSERT INTO sales_log (product_name, quantity, total_amount, profit) VALUES (?,?,?,?)",
                      (selection, qty, total, profit), is_select=False)
            run_query("UPDATE products SET stock_quantity = stock_quantity - ? WHERE name=?", (qty, selection), is_select=False)
            st.success(f"Sold! ₦{total:,.2f} recorded.")

elif page == "📊 Financials":
    st.header("Business Intelligence")
    sales = run_query("SELECT * FROM sales_log")
    
    col1, col2 = st.columns(2)
    col1.metric("Gross Revenue", f"₦{sales['total_amount'].sum():,.2f}")
    col2.metric("Net Profit", f"₦{sales['profit'].sum():,.2f}")
    
    st.subheader("Transaction History")
    st.dataframe(sales.sort_values('timestamp', ascending=False), use_container_width=True)

elif page == "📦 Warehouse":
    st.header("Stock Management")
    with st.form("add_stock"):
        n = st.text_input("Item Name")
        cp = st.number_input("Cost Price (₦)")
        sp = st.number_input("Selling Price (₦)")
        stk = st.number_input("Opening Stock", value=50)
        if st.form_submit_button("Load Item"):
            run_query("INSERT OR REPLACE INTO products (name, cost_price, selling_price, stock_quantity) VALUES (?,?,?,?)",
                      (n, cp, sp, stk), is_select=False)
            st.success(f"{n} is now live in the system!")