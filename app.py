import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

def run_query(query, params=(), is_select=True):
    with sqlite3.connect('provision_store.db') as conn:
        if is_select: return pd.read_sql_query(query, conn, params=params)
        else: conn.execute(query, params); conn.commit()

st.set_page_config(page_title="Reks Enterprise", layout="wide")
menu = st.sidebar.selectbox("COMMAND CENTER", ["🏠 Dashboard", "🛒 POS (Sell)", "📦 Inventory", "📓 Debtors Book"])

# --- 1. DASHBOARD (Notice when stock reduces to 3) ---
if menu == "🏠 Dashboard":
    st.title("Business Overview")
    
    # ALERT SYSTEM
    low_stock = run_query("SELECT product_name, stock_quantity, shelf_location FROM products WHERE stock_quantity <= 3")
    if not low_stock.empty:
        st.error("🚨 CRITICAL STOCK ALERT (3 or less remaining)")
        st.table(low_stock)

    # EXPIRY NOTICE
    st.subheader("📅 Near Expiry")
    expiry = run_query("SELECT product_name, expiry_date FROM products ORDER BY expiry_date ASC LIMIT 5")
    st.dataframe(expiry)

# --- 2. POS TRANSACTIONS ---
elif menu == "🛒 POS (Sell)":
    st.header("Point of Sale")
    items = run_query("SELECT product_name, selling_price, cost_price, stock_quantity FROM products")
    selection = st.selectbox("Select Product", items['product_name'])
    
    if selection:
        p_info = items[items['product_name'] == selection].iloc[0]
        qty = st.number_input("Quantity", min_value=1, max_value=int(p_info['stock_quantity']))
        
        if st.button("Complete Transaction"):
            total = p_info['selling_price'] * qty
            profit = (p_info['selling_price'] - p_info['cost_price']) * qty
            # Record Sale
            run_query("INSERT INTO pos_transactions (product_name, qty_sold, total_amount, profit) VALUES (?,?,?,?)",
                      (selection, qty, total, profit), is_select=False)
            # Update Stock
            run_query("UPDATE products SET stock_quantity = stock_quantity - ? WHERE product_name=?", (qty, selection), is_select=False)
            st.success(f"Sold! Total: ₦{total:,.2f}")

# --- 3. RECORD & SAVE UNLIMITED PRODUCTS ---
elif menu == "📦 Inventory":
    st.header("Warehouse Management")
    with st.form("inventory_form"):
        name = st.text_input("Product Name")
        cp = st.number_input("Cost Price")
        sp = st.number_input("Selling Price")
        loc = st.text_input("Shelf Location (e.g., A1, Back Row)")
        exp = st.date_input("Expiration Date")
        stk = st.number_input("Initial Stock Quantity")
        if st.form_submit_button("Save to Database"):
            run_query("INSERT OR REPLACE INTO products (product_name, cost_price, selling_price, shelf_location, expiry_date, stock_quantity) VALUES (?,?,?,?,?,?)",
                      (name, cp, sp, loc, exp, stk), is_select=False)
            st.success(f"{name} added to unlimited records!")

# --- 4. DEBTORS RECORD ---
elif menu == "📓 Debtors Book":
    st.header("Credit Records")
    with st.expander("Add New Debtor"):
        c_name = st.text_input("Customer Name")
        owed = st.number_input("Amount Owed")
        phone = st.text_input("Phone Number")
        if st.button("Save Debt"):
            run_query("INSERT INTO debtors (customer_name, amount_owed, phone_number, date_issued) VALUES (?,?,?,?)",
                      (c_name, owed, phone, datetime.now().date()), is_select=False)
    
    st.subheader("Current Debtors List")
    st.dataframe(run_query("SELECT * FROM debtors WHERE status='UNPAID'"))
