import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="Enterprise Shop Manager", layout="wide")

# --- 1. THE FOUNDATION (The "Unique" Fix) ---
def initialize_system():
    conn = sqlite3.connect('provision_store.db')
    cursor = conn.cursor()
    
    # We create the table with 'UNIQUE' rule on 'name'
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, 
        stock_quantity INTEGER DEFAULT 0,
        cost_price REAL DEFAULT 0.0,
        selling_price REAL DEFAULT 0.0,
        shelf_location TEXT DEFAULT 'Not Set'
    )''')
    
    # High-speed Indexing for 1M+ rows
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_name ON products(name)")
    
    # Ensure other tables exist
    cursor.execute("CREATE TABLE IF NOT EXISTS sales_log (log_id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT, quantity_sold INTEGER, amount_earned REAL, sale_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS debtors (debtor_id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT, amount_owed REAL, phone_number TEXT, status TEXT DEFAULT 'Unpaid')")
    
    conn.commit()
    conn.close()

initialize_system()

# --- 2. TOOLS ---
def run_query(query, params=()):
    with sqlite3.connect('provision_store.db') as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def get_data(query, params=()):
    with sqlite3.connect('provision_store.db') as conn:
        return pd.read_sql_query(query, conn, params=params)

# --- 3. THE APP INTERFACE ---
st.sidebar.title("🏢 UNICROSS EEE")
menu = st.sidebar.radio("Navigation", ["📊 Dashboard", "🛒 Sales (POS)", "📥 Inventory Management", "💸 Debtor Ledger"])

if menu == "📊 Dashboard":
    st.header("Business Command Center")
    search = st.text_input("🔍 Search 1M+ Products...")
    if search:
        results = get_data("SELECT name, stock_quantity, cost_price, selling_price, shelf_location FROM products WHERE name LIKE ?", (f'%{search}%',))
        st.dataframe(results, use_container_width=True)

elif menu == "📥 Inventory Management":
    st.header("Stock Management")
    # clear_on_submit makes it ready for the NEXT product immediately
    with st.form("inventory_form", clear_on_submit=True):
        p_name = st.text_input("Product Name")
        p_qty = st.number_input("Total Quantity", min_value=0)
        p_cost = st.number_input("Cost Price (₦)")
        p_sell = st.number_input("Selling Price (₦)")
        p_loc = st.text_input("Shelf Location")
        
        if st.form_submit_button("Save/Update Product"):
            if p_name:
                run_query('''INSERT INTO products (name, stock_quantity, cost_price, selling_price, shelf_location) 
                             VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET 
                             stock_quantity=excluded.stock_quantity, cost_price=excluded.cost_price, 
                             selling_price=excluded.selling_price, shelf_location=excluded.shelf_location''', 
                          (p_name, p_qty, p_cost, p_sell, p_loc))
                st.success(f"✅ Record Saved: {p_name}")
                st.info("Form cleared. You can type the next product now!")
            else:
                st.error("Please enter a name.")

# (Keep the Sales and Debtors sections from the previous version)s