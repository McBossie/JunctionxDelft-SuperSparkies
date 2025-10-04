import streamlit as st
import pandas as pd
import numpy as np
import os

FILE_PATH = "/Users/chahid/projects/uber-copilot/data/data_sets.xlsx"

@st.cache_data
def load_data():
    df_orders = pd.read_excel(FILE_PATH, sheet_name='eats_orders')
    df_heatmap = pd.read_excel(FILE_PATH, sheet_name='heatmap')
    df_incentives = pd.read_excel(FILE_PATH, sheet_name='incentives_weekly')
    df_heatmap.rename(columns={
        'msg.predictions.hexagon_id_9': 'hexagon_id9',
        'msg.predictions.predicted_eph': 'predicted_eph'
    }, inplace=True)
    df_orders['tip_eur'] = pd.to_numeric(df_orders['tip_eur'], errors='coerce').fillna(0)
    df_orders['distance_km'] = pd.to_numeric(df_orders['distance_km'], errors='coerce').fillna(0)
    df_orders['duration_mins'] = pd.to_numeric(df_orders['duration_mins'], errors='coerce').fillna(0)
    df_orders['delivery_fee_eur'] = pd.to_numeric(df_orders['delivery_fee_eur'], errors='coerce').fillna(0)
    eph_lookup = df_heatmap.set_index('hexagon_id9')['predicted_eph'].to_dict()
    return df_orders, eph_lookup, df_incentives

def get_smart_advice(pickup_hex, base_delivery_fee, tip_eur, distance_km, duration_mins, eph_lookup):
    predicted_net_earnings = base_delivery_fee + tip_eur
    duration_hours = duration_mins / 60.0
    predicted_eph_trip = predicted_net_earnings / duration_hours if duration_hours > 0 else 0.0
    area_eph = eph_lookup.get(pickup_hex, 15.0)
    return {
        "Tip (€) from Excel": round(tip_eur, 2),
        "Predicted Net Earnings (€)": round(predicted_net_earnings, 2),
        "Predicted EPH (€/hr)": round(predicted_eph_trip, 2),
        "Area EPH (€/hr)": round(area_eph, 2),
        "Trip Distance (km)": round(distance_km, 2),
        "Predicted Total Trip (min)": round(duration_mins, 1),
    }


st.set_page_config(page_title="Uber Eats Merchant Order Analysis", page_icon="🍔", layout="centered")
st.title("Uber Eats Merchant Order Analysis")

df_orders, eph_lookup, df_incentives = load_data()

merchant_ids = df_orders['merchant_id'].unique()
merchant_id = st.selectbox("Select Merchant ID", merchant_ids)

merchant_orders = df_orders[df_orders['merchant_id'] == merchant_id].copy()
merchant_orders['start_time'] = pd.to_datetime(merchant_orders['start_time'])
merchant_orders = merchant_orders.sort_values(by='start_time', ascending=True).reset_index(drop=True)

if merchant_orders.empty:
    st.error(f"No orders found for merchant ID '{merchant_id}'.")
    st.stop()

order_idx = st.number_input(
    f"Select order index (0 to {len(merchant_orders)-1})", 
    min_value=0, max_value=len(merchant_orders)-1, value=0, step=1
)
selected_order = merchant_orders.iloc[order_idx]

st.subheader("Order Details")
st.write({
    "Order Start Time": selected_order['start_time'],
    "Pickup Hex": selected_order['pickup_hex_id9'],
    "Dropoff Hex": selected_order['drop_hex_id9'],
    "Base Delivery Fee (€)": selected_order['delivery_fee_eur'],
    "Distance (km)": selected_order['distance_km'],
    "Duration (min)": int(selected_order['duration_mins']),
    "Tip (€) from Excel": int(selected_order['tip_eur'])
})

advice = get_smart_advice(
    selected_order['pickup_hex_id9'],
    selected_order['delivery_fee_eur'],
    selected_order['tip_eur'],
    selected_order['distance_km'],
    selected_order['duration_mins'],
    eph_lookup
)

st.subheader("Predictive Order Analysis")
for k, v in advice.items():
    st.write(f"**{k}:** {v}")
