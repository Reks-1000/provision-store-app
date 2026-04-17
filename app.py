import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- DATABASE CONNECTION ---
def run_query(query, params=(), is_select=True):
    with sqlite3.connect('provision_store.db') as conn:
        if is_select:
            return pd.read_sql_query(query, conn, params=params)
        else:
            conn.execute(query, params)
            conn.commit()

# --- LOGIN SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Reks Enterprise Login")
    user = st.text_input("Username")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        # This checks the 'users' table we created in the setup
        res = run_query("SELECT * FROM users WHERE username=? AND password=?", (user, pw))
        if not res.empty:
            st.session_state.logged_in = True
            st.session_state.user_role = res['role'][0]
            st.rerun()
        else:
            st.error("Invalid Credentials")
    st.stop()

# --- APP INTERFACE ---
st.sidebar.title(f"Logged in as: {st.session_state.user_role}")
menu = st.sidebar.radio("Control Panel", ["📦 Sales Point", "📊 Owner Dashboard", "⚙️ Stock Management"])

if menu == "📦 Sales Point":
    st.header("Point of Sale")
    # Fetch products from your 1M database
    products = run_query("SELECT name FROM products")
    if products.empty:
        st.warning("Inventory is empty! Go to Stock Management to add items.")
    else:
        product_search = st.selectbox("Select Product", products['name'])
        qty = st.number_input("Quantity", min_value=1, value=1)
        
        if st.button("Complete Sale"):
            p_data = run_query("SELECT * FROM products WHERE name=?", (product_search,)).iloc[0]
            total = p_data['selling_price'] * qty
            profit = (p_data['selling_price'] - p_data['cost_price']) * qty
            
            # Record the sale with an Audit Trail
            run_query("INSERT INTO sales_log (product_name, quantity, total_amount, profit, worker_name) VALUES (?,?,?,?,?)",
                      (product_search, qty, total, profit, user), is_select=False)
            
            # Reduce stock
            run_query("UPDATE products SET stock_quantity = stock_quantity - ? WHERE name=?", (qty, product_search), is_select=False)
            st.success(f"Sale Recorded! Total: ₦{total:,.2f}")

elif menu == "📊 Owner Dashboard":
    if st.session_state.user_role != "Admin":
        st.error("Access Denied! Admins Only.")
    else:
        st.header("Financial Performance")
        sales = run_query("SELECT * FROM sales_log")
        if not sales.empty:
            c1, c2 = st.columns(2)
            c1.metric("Total Sales", f"₦{sales['total_amount'].sum():,.2f}")
            c2.metric("Total Profit", f"₦{sales['profit'].sum():,.2f}")
            st.subheader("Transaction History")
            st.dataframe(sales)
        else:
            st.info("No sales recorded yet.")

elif menu == "⚙️ Stock Management":
    st.header("Inventory Engine")
    with st.form("new_item"):
        name = st.text_input("Product Name")
        cp = st.number_input("Cost Price (₦)")
        sp = st.number_input("Selling Price (₦)")
        stock = st.number_input("Initial Quantity", value=100)
        if st.form_submit_button("Add to System"):
            run_query("INSERT INTO products (name, cost_price, selling_price, stock_quantity) VALUES (?,?,?,?)",
                      (name, cp, sp, stock), is_select=False)
            st.success(f"{name} added to inventory!")
