import streamlit as st
import pandas as pd
import sqlite3

# --- 1. THE DATABASE CONNECTION (THE MISSING WIRES) ---
def get_data(query, params=()):
    conn = sqlite3.connect('provision_store.db')
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# --- 2. THE NAVIGATION MENU ---
menu = st.sidebar.radio("Navigation", ["📊 Dashboard", "📈 Sales Reports", "📥 Inventory Management"])

# --- 3. DASHBOARD LOGIC ---
if menu == "📊 Dashboard":
    st.header("Business Command Center")
    
    st.subheader("⚠️ Low Stock Alerts")
    # This checks your DB for items running out
    low_stock = get_data("SELECT name, stock_quantity FROM products WHERE stock_quantity < 5")
    
    if not low_stock.empty:
        st.warning(f"You have {len(low_stock)} items running low!")
        st.dataframe(low_stock)
    else:
        st.success("All stock levels are healthy!")

    search = st.text_input("🔍 Search 1M+ Products...")
    if search:
        results = get_data("SELECT name, stock_quantity, selling_price FROM products WHERE name LIKE ?", (f'%{search}%',))
        st.table(results)

# --- 4. SALES REPORTS ---
elif menu == "📈 Sales Reports":
    st.header("Financial Performance")
    # This pulls your sales history
    sales_data = get_data("SELECT * FROM sales_log")
    st.metric("Total Transactions", len(sales_data))
    st.dataframe(sales_data)