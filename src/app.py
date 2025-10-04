import streamlit as st
import pandas as pd
import random
from typing import Optional, Dict
from next_locdemo import load_data_from_excel, DemandPredictor, DecisionEngine, FATIGUE_HIGH_THRESHOLD, FATIGUE_CRITICAL_THRESHOLD, MOVE_ADVANTANTAGE_THRESHOLD

st.set_page_config(page_title="Uber Co-Pilot Advisor", layout="wide")

@st.cache_data(show_spinner=False)
def load_all_data():
    data = load_data_from_excel("../data/data_sets.xlsx")
    if data is None:
        st.error("Failed to load data. Please ensure the Excel file exists in '../data/data_sets.xlsx'.")
        st.stop()
    return data

def sample_candidate_locations(heatmap_df: pd.DataFrame, current_hex: str, sample_size: int = 5) -> Dict[str, Dict[str, float]]:
    candidate_locations = {current_hex: {"distance_km": 0, "travel_time_mins": 0}}
    sampled = heatmap_df["msg.predictions.hexagon_id_9"].drop_duplicates().sample(sample_size + 3, random_state=42).tolist()
    count = 0
    for loc in sampled:
        if loc != current_hex and count < sample_size:
            dist = random.uniform(1.0, 5.0)
            time = dist * 2.5
            candidate_locations[loc] = {"distance_km": dist, "travel_time_mins": time}
            count += 1
    return candidate_locations

def compute_fatigue(hours_online: float, jobs_completed: int) -> float:
    # replicate the fatigue calculation logic from DecisionEngine
    MAX_HOURS_CONTINUOUS = 5
    hour_fatigue = min(1.0, (hours_online / MAX_HOURS_CONTINUOUS))
    job_fatigue = min(1.0, (jobs_completed / 50))
    return min(1.0, (hour_fatigue * 0.7) + (job_fatigue * 0.3))

def main():
    st.title("Uber Co-Pilot Advisor")
    data = load_all_data()

    earners_df = data["earners"]
    rides_trips_df = data["rides_trips"]
    heatmap_df = data["heatmap"]

    predictor = DemandPredictor(heatmap_df)
    engine = DecisionEngine(predictor=predictor, rides_trips_data=rides_trips_df)

    st.sidebar.header("Driver & Shift Settings")

    # Driver selection
    driver_options = earners_df['earner_id'].tolist()
    selected_driver = st.sidebar.selectbox("Select Driver ID", options=driver_options)

    driver_info = earners_df[earners_df['earner_id'] == selected_driver].iloc[0]

    # Time selection (latest or custom)
    # For simplicity, we simulate hours_online and jobs_completed
    time_mode = st.sidebar.radio("Hours Online / Jobs Completed Input Mode", options=["Simulated", "Custom"])

    if time_mode == "Simulated":
        hours_online = random.uniform(1, 4)
        jobs_completed = random.randint(2, 8)
    else:
        hours_online = st.sidebar.number_input("Hours Online So Far", min_value=0.0, max_value=24.0, value=2.0, step=0.1)
        jobs_completed = st.sidebar.number_input("Jobs Completed So Far", min_value=0, max_value=100, value=3, step=1)

    # Hours to drive remaining
    hours_to_drive = st.sidebar.number_input("Hours Remaining to Drive", min_value=0.1, max_value=12.0, value=2.0, step=0.1)
    time_remaining_mins = hours_to_drive * 60

    # Current location hex input
    current_hex = st.sidebar.text_input("Current Location Hex ID", value=random.choice(heatmap_df["msg.predictions.hexagon_id_9"].drop_duplicates().tolist())).strip()

    if current_hex not in heatmap_df["msg.predictions.hexagon_id_9"].values:
        st.sidebar.warning("Current hex ID not found in heatmap data. Please enter a valid hex ID.")
        st.stop()

    # Sample candidate locations
    candidate_locations = sample_candidate_locations(heatmap_df, current_hex, sample_size=5)

    # Active quest detection (optional)
    # For simplicity, no active quest integration here.

    recommendation, details = engine.get_recommendation(
        current_location=current_hex,
        city_id=driver_info['home_city_id'],
        fuel_type=driver_info['fuel_type'],
        hours_online=hours_online,
        jobs_completed=jobs_completed,
        time_remaining_in_shift_mins=int(time_remaining_mins),
        candidate_locations=candidate_locations,
        active_quest=None
    )

    fatigue_level = details.get("fatigue_level", compute_fatigue(hours_online, jobs_completed))
    base_eph = None
    effective_eph = None
    current_loc_data = None
    best_option = None

    ranked_options = details.get("ranked_options", [])
    if ranked_options:
        current_loc_data = next((opt for opt in ranked_options if opt["location"] == current_hex), None)
        best_option = ranked_options[0]
        if current_loc_data:
            base_eph = current_loc_data.get("raw_eph", None)
            effective_eph = current_loc_data.get("effective_eph", None)

    # Layout: Metrics on top, recommendation card below
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Hours Online", f"{hours_online:.1f}")
    col2.metric("Jobs Completed", f"{jobs_completed}")
    col3.metric("Fatigue Level", f"{fatigue_level:.2f}")
    col4.metric("Current Hex", current_hex)
    col5.metric("Base EPH", f"${base_eph:.2f}" if base_eph is not None else "N/A")

    if effective_eph is not None:
        st.metric("Effective EPH (Current Location)", f"${effective_eph:.2f}")

    # Recommendation card with color-coded status
    def recommendation_color(rec_text: str) -> str:
        rec_lower = rec_text.lower()
        if "critical" in rec_lower or "break" in rec_lower:
            return "red"
        elif "move to" in rec_lower:
            return "green"
        else:
            return "orange"

    rec_color = recommendation_color(recommendation)

    st.markdown(f"## Recommendation")
    st.markdown(f"<div style='padding: 1rem; border-radius: 8px; background-color: {rec_color}; color: white; font-size: 1.2rem;'>{recommendation}</div>", unsafe_allow_html=True)

    if best_option and best_option["location"] != current_hex and rec_color == "green":
        st.markdown("### Best Hotspot Details")
        st.write(f"**Hex ID:** {best_option['location']}")
        st.write(f"Distance: {best_option['distance_km']:.2f} km")
        st.write(f"Travel Time: {best_option['travel_time_mins']:.1f} min")
        st.write(f"Raw EPH: ${best_option['raw_eph']:.2f}")
        st.write(f"Effective EPH: ${best_option['effective_eph']:.2f}")
        if "final_score" in best_option:
            st.write(f"Final Score: {best_option['final_score']:.2f}")

    # Show candidate locations table with hex codes only
    if ranked_options:
        st.markdown("### Candidate Locations Analyzed")
        df_opts = pd.DataFrame(ranked_options)
        df_opts_display = df_opts[["location", "distance_km", "travel_time_mins", "raw_eph", "effective_eph", "final_score"]]
        df_opts_display = df_opts_display.rename(columns={
            "location": "Hex ID",
            "distance_km": "Distance (km)",
            "travel_time_mins": "Travel Time (min)",
            "raw_eph": "Raw EPH ($/hr)",
            "effective_eph": "Effective EPH ($/hr)",
            "final_score": "Final Score"
        })
        st.dataframe(df_opts_display.style.format({
            "Distance (km)": "{:.2f}",
            "Travel Time (min)": "{:.1f}",
            "Raw EPH ($/hr)": "${:.2f}",
            "Effective EPH ($/hr)": "${:.2f}",
            "Final Score": "{:.2f}"
        }), use_container_width=True)

if __name__ == "__main__":
    main()
