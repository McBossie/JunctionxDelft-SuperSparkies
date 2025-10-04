import pandas as pd
import numpy as np
import os

FILE_PATH = "/Users/chahid/projects/uber-copilot/data/data_sets.xlsx"

CANCELLATION_LOOKUP = {}
EPH_LOOKUP = {}
MEDIAN_TIP_PER_KM = 0.0
MEDIAN_OVERALL_TIP = 0.0
DF_INCENTIVES = pd.DataFrame()
DF_ORDERS = pd.DataFrame()

def load_and_preprocess_data():
    global DF_ORDERS, MEDIAN_OVERALL_TIP, MEDIAN_TIP_PER_KM
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return {}, {}, 0.0, 0.0, pd.DataFrame(), pd.DataFrame()
    try:
        print(f"Loading data from: {FILE_PATH}")
        df_cancellations = pd.read_excel(FILE_PATH, sheet_name='cancellation_rates')
        df_heatmap = pd.read_excel(FILE_PATH, sheet_name='heatmap')
        df_orders = pd.read_excel(FILE_PATH, sheet_name='eats_orders')
        df_incentives = pd.read_excel(FILE_PATH, sheet_name='incentives_weekly')
        DF_ORDERS = df_orders.copy()
        df_heatmap.rename(columns={
            'msg.predictions.hexagon_id_9': 'hexagon_id9',
            'msg.predictions.predicted_eph': 'predicted_eph'
        }, inplace=True)
        cancellation_lookup = df_cancellations.set_index('hexagon_id9')['cancellation_rate_pct'].to_dict()
        eph_lookup = df_heatmap.set_index('hexagon_id9')['predicted_eph'].to_dict()
        DF_ORDERS['tip_eur'] = pd.to_numeric(DF_ORDERS['tip_eur'], errors='coerce').fillna(0)
        DF_ORDERS['distance_km'] = pd.to_numeric(DF_ORDERS['distance_km'], errors='coerce').fillna(0)
        DF_ORDERS['duration_mins'] = pd.to_numeric(DF_ORDERS['duration_mins'], errors='coerce').fillna(0)
        DF_ORDERS['delivery_fee_eur'] = pd.to_numeric(DF_ORDERS['delivery_fee_eur'], errors='coerce').fillna(0)
        DF_ORDERS['tip_per_km'] = np.where(
            DF_ORDERS['distance_km'] > 0, 
            DF_ORDERS['tip_eur'] / DF_ORDERS['distance_km'], 
            0
        )
        median_tip_per_km = DF_ORDERS['tip_per_km'].replace([np.inf, -np.inf], np.nan).dropna().median()
        if pd.isna(median_tip_per_km): median_tip_per_km = 0.0
        median_overall_tip = DF_ORDERS['tip_eur'].median()
        if pd.isna(median_overall_tip): median_overall_tip = 0.0
        MEDIAN_OVERALL_TIP = median_overall_tip
        MEDIAN_TIP_PER_KM = median_tip_per_km
        print("Data loaded and lookup tables initialized successfully.")
        return cancellation_lookup, eph_lookup, median_tip_per_km, median_overall_tip, df_incentives, DF_ORDERS
    except Exception as e:
        print(f"Error loading data: {e}")
        return {}, {}, 0.0, 0.0, pd.DataFrame(), pd.DataFrame()

CANCELLATION_LOOKUP, EPH_LOOKUP, MEDIAN_TIP_PER_KM, MEDIAN_OVERALL_TIP, DF_INCENTIVES, DF_ORDERS = load_and_preprocess_data()

def simulate_order_for_merchant(merchant_id):
    if DF_ORDERS.empty:
        print("Error: Eats orders data is not available.")
        return None
    merchant_orders = DF_ORDERS[DF_ORDERS['merchant_id'] == merchant_id].copy()
    if merchant_orders.empty:
        print(f"Error: No orders found for merchant ID '{merchant_id}'.")
        return None
    merchant_orders['start_time'] = pd.to_datetime(merchant_orders['start_time'])
    print("\nAvailable orders for merchant", merchant_id)
    print(merchant_orders[['start_time', 'duration_mins', 'distance_km', 'pickup_hex_id9', 'drop_hex_id9', 'tip_eur']])
    order_idx = 0
    if len(merchant_orders) > 1:
        try:
            order_idx = int(input(f"Enter the index of the order to analyze (0 for first, up to {len(merchant_orders)-1}): ") or "0")
        except Exception:
            order_idx = 0
    selected_order = merchant_orders.iloc[order_idx]
    sim_params = {
        "pickup_hex": selected_order['pickup_hex_id9'],
        "dropoff_hex": selected_order['drop_hex_id9'],
        "base_delivery_fee": selected_order['delivery_fee_eur'],
        "distance_km": selected_order['distance_km'],
        "duration_mins": selected_order['duration_mins'],
        "actual_tip_eur": selected_order['tip_eur'],
        "start_time": selected_order['start_time']
    }
    for key in ['base_delivery_fee', 'distance_km', 'duration_mins', 'actual_tip_eur']:
        try:
            sim_params[key] = float(sim_params[key])
        except (ValueError, TypeError):
            sim_params[key] = 0.0
    return sim_params

def get_smart_advice(pickup_hex, dropoff_hex, base_delivery_fee, distance_km, duration_mins):
    cancellation_risk = CANCELLATION_LOOKUP.get(dropoff_hex, 0.0)
    risk_level = "Low"
    if cancellation_risk >= 7.0:
        risk_level = "HIGH"
    elif cancellation_risk >= 5.0:
        risk_level = "Medium"
    if MEDIAN_TIP_PER_KM > 0.1:
        predicted_tip = distance_km * MEDIAN_TIP_PER_KM
        tip_model_used = "Distance-Based"
    else:
        predicted_tip = MEDIAN_OVERALL_TIP
        tip_model_used = "Median Overall"
    predicted_net_earnings = base_delivery_fee + predicted_tip
    duration_hours = duration_mins / 60.0
    predicted_eph_trip = predicted_net_earnings / duration_hours if duration_hours > 0 else 0.0
    area_eph = EPH_LOOKUP.get(pickup_hex, 15.0)
    return {
        "cancellation_risk_pct": round(cancellation_risk, 2),
        "risk_level": risk_level,
        "predicted_tip_eur": round(predicted_tip, 2),
        "predicted_net_earnings_eur": round(predicted_net_earnings, 2),
        "predicted_eph_trip": round(predicted_eph_trip, 2),
        "area_eph": round(area_eph, 2),
        "tip_per_km_model": round(MEDIAN_TIP_PER_KM, 3),
        "tip_model_used": tip_model_used,
        "trip_distance_km": round(distance_km, 2),
        "predicted_total_trip_mins": round(duration_mins, 1),
    }

def check_quest_status(earner_id="E10300"):
    if DF_INCENTIVES.empty:
        return "Warning: incentives_weekly data is missing. Cannot check Quest status."
    try:
        earner_quests = DF_INCENTIVES[
            (DF_INCENTIVES['earner_id'] == earner_id) & 
            (DF_INCENTIVES['program'] == 'eats_quest') & 
            (DF_INCENTIVES['achieved'] == False)
        ]
        if earner_quests.empty:
            return "No active quest found or quest already achieved. Focus on general EPH."
        quest = earner_quests.sort_values(by='week', ascending=False).iloc[0]
        target = int(quest['target_jobs'])
        completed = int(quest['completed_jobs'])
        bonus = quest['bonus_eur']
        needed = target - completed
        if needed > 0 and needed <= 5:
            return f"URGENT: Only {needed:.0f} jobs needed to hit {target:.0f} target and earn a €{bonus:.0f} bonus! Prioritize acceptance."
        elif needed > 5:
            return f"Quest Progress: {completed:.0f}/{target:.0f} jobs completed. Keep pushing for the €{bonus:.0f} bonus."
        else:
            return "No active quest found or quest already achieved. Focus on general EPH."
    except Exception as e:
        return f"Warning: Could not process Quest data. Error: {e}"

if __name__ == '__main__':
    print("--- Uber Eats Merchant Order Analysis ---")
    merchant_id_input = input("Enter Merchant ID (e.g., M107, M507, M201): ").strip().upper() or 'M107'
    order_params = simulate_order_for_merchant(merchant_id_input)
    if order_params:
        print("\n--- Extracted Order Parameters for Simulation ---")
        print(f"Merchant ID: {merchant_id_input}")
        print(f"Pickup Hex: {order_params['pickup_hex']}")
        print(f"Dropoff Hex: {order_params['dropoff_hex']}")
        print(f"Base Delivery Fee (Guaranteed): €{order_params['base_delivery_fee']:.2f}")
        print(f"Distance: {order_params['distance_km']:.2f} km")
        print(f"Duration (Estimated Delivery Time): {order_params['duration_mins']:.1f} mins")
        print(f"Order Start Time: {order_params['start_time']}")
        print(f"Historical Tip (for this order): €{order_params['actual_tip_eur']:.2f}")
        print("-------------------------------------------------")
        advice = get_smart_advice(
            order_params['pickup_hex'], 
            order_params['dropoff_hex'], 
            order_params['base_delivery_fee'], 
            order_params['distance_km'], 
            order_params['duration_mins']
        )
        print("\n--- Predictive Order Analysis ---")
        for key, value in advice.items():
            print(f"- {key.replace('_', ' ').title()}: {value}")
        print(f"\nEstimated Time to Complete Delivery: {order_params['duration_mins']:.1f} minutes")
        print(f"\nQuest Status (E10300): {check_quest_status(earner_id='E10300')}")
    else:
        print(f"Analysis aborted. Could not find or process an order for merchant '{merchant_id_input}'.")