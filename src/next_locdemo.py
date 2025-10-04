import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional
import random
# NEW DEPENDENCY: geopy is used for converting coordinates to addresses.
# Install it by running: pip install geopy
from geopy.geocoders import Nominatim

# --- Configuration Constants ---
# Profitability Analysis
MOVE_ADVANTANTAGE_THRESHOLD = 1.25
# Fuel Costs
FUEL_TYPE_COSTS_PER_KM = { "gas": 0.35, "hybrid": 0.25, "EV": 0.15, "unknown": 0.30 }
# Personalization Filters
FATIGUE_HIGH_THRESHOLD = 0.6
FATIGUE_CRITICAL_THRESHOLD = 0.8
MAX_HOURS_CONTINUOUS = 5

# --- Helper Functions for Location Conversion ---

def latlon_to_location(lat: float, lon: float) -> str:
    """Converts latitude and longitude to a readable address string."""
    try:
        geolocator = Nominatim(user_agent="uber_copilot_advisor")
        # zoom=15 gives a street-level address, zoom=14 is more like a neighborhood.
        location = geolocator.reverse((lat, lon), language="en", zoom=15)
        return location.address if location else "Unknown location"
    except Exception:
        # Handle potential network errors or timeouts from the geocoding service.
        return "Geocoding service unavailable"

def get_location_from_hex(hex_id: str, mapping: pd.DataFrame) -> str:
    """Looks up a hex_id in the mapping and returns a readable location name."""
    if hex_id not in mapping.index:
        return hex_id # Return the ID itself if not found
    
    lat, lon = mapping.loc[hex_id, ["lat", "lon"]]
    return latlon_to_location(lat, lon)


class DemandPredictor:
    """
    A mock AI model to predict Earnings Per Hour (EPH) for different locations.
    """
    def __init__(self, heatmap_data: pd.DataFrame):
        self._eph_predictions = pd.Series(
            heatmap_data["msg.predictions.predicted_eph"].values,
            index=heatmap_data["msg.predictions.hexagon_id_9"]
        ).to_dict()

    def predict_eph(self, locations: List[str]) -> Dict[str, float]:
        """Predicts the EPH for a given list of locations."""
        return {loc: self._eph_predictions.get(loc, 10.0) for loc in locations}

class DecisionEngine:
    """
    The core logic engine that synthesizes AI predictions with driver-specific
    data to provide personalized and strategic recommendations.
    """
    def __init__(self, predictor: DemandPredictor, rides_trips_data: pd.DataFrame):
        """
        Initializes the DecisionEngine.
        """
        self.predictor = predictor
        # Calculate the average fare per city from the provided trip data.
        self.avg_fare_by_city = rides_trips_data.groupby('city_id')['fare_amount'].mean().to_dict()

    def _compute_fatigue(self, hours_online: float, jobs_completed: int) -> float:
        """
        Calculates a fatigue score from 0 (fresh) to 1 (exhausted).
        """
        hour_fatigue = min(1.0, (hours_online / MAX_HOURS_CONTINUOUS))
        job_fatigue = min(1.0, (jobs_completed / 50))
        return min(1.0, (hour_fatigue * 0.7) + (job_fatigue * 0.3))

    def get_recommendation(
        self,
        current_location: str,
        city_id: int,
        fuel_type: str,
        hours_online: float,
        jobs_completed: int,
        time_remaining_in_shift_mins: int,
        candidate_locations: Optional[Dict[str, Dict[str, float]]] = None,
        desired_end_location: Optional[str] = None,
        active_quest: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        Generates the best next move for a driver by running the full decision algorithm.
        """
        # 1. CALCULATE DRIVER'S CURRENT STATE
        fatigue_level = self._compute_fatigue(hours_online, jobs_completed)
        details = { "fatigue_level": round(fatigue_level, 2), "hours_online": hours_online, "time_remaining_mins": time_remaining_in_shift_mins, "active_quest": active_quest }

        # Safety override
        if fatigue_level >= FATIGUE_CRITICAL_THRESHOLD:
            return ("CRITICAL: Take a break. Your fatigue level is too high for safe driving.", details)
        if hours_online > MAX_HOURS_CONTINUOUS:
             return (f"Take a break. You've been driving for {hours_online:.1f} hours straight.", details)

        # 2. PREDICTIVE DEMAND & PROFITABILITY ANALYSIS
        if not candidate_locations:
            candidate_locations = {current_location: {"distance_km": 0, "travel_time_mins": 0}}

        predicted_eph = self.predictor.predict_eph(list(candidate_locations.keys()))
        details["predicted_eph"] = predicted_eph

        options = []
        for loc, details_loc in candidate_locations.items():
            travel_time_mins = details_loc["travel_time_mins"]
            dist_km = details_loc["distance_km"]
            
            if travel_time_mins >= time_remaining_in_shift_mins:
                continue

            vehicle_cost_per_km = FUEL_TYPE_COSTS_PER_KM.get(fuel_type, 0.30)
            raw_eph = predicted_eph.get(loc, 10.0)
            time_efficiency_multiplier = 60 / (60 + travel_time_mins)
            travel_cost_hourly = (dist_km * vehicle_cost_per_km) * (60 / (travel_time_mins + 1)) if travel_time_mins > 0 else 0
            effective_eph = (raw_eph * time_efficiency_multiplier) - travel_cost_hourly
            
            options.append({ "location": loc, "distance_km": dist_km, "travel_time_mins": travel_time_mins, "raw_eph": raw_eph, "effective_eph": effective_eph })

        if not options:
            return ("Stay put. No viable alternative locations found within your shift time.", details)

        # 3. PERSONALIZED GOAL ALIGNMENT
        for option in options:
            score = option["effective_eph"]
            
            if fatigue_level > FATIGUE_HIGH_THRESHOLD:
                score -= (option["travel_time_mins"] * 0.1) * (fatigue_level - FATIGUE_HIGH_THRESHOLD)
            
            if active_quest:
                trips_needed = active_quest["target"] - active_quest["progress"]
                if trips_needed > 0 and active_quest["deadline_hours"] > 0:
                    required_rate = trips_needed / active_quest["deadline_hours"]
                    avg_fare = self.avg_fare_by_city.get(city_id, 15.0)
                    # A location with a higher EPH is assumed to offer more frequent trips.
                    estimated_trip_rate = option["raw_eph"] / avg_fare if avg_fare > 0 else 0
                    
                    if estimated_trip_rate >= required_rate:
                        quest_bonus_value = active_quest["reward"] / active_quest["target"]
                        score += quest_bonus_value

            option["final_score"] = score
        
        ranked_options = sorted(options, key=lambda x: x["final_score"], reverse=True)
        details["ranked_options"] = ranked_options
        
        best_option = ranked_options[0]
        current_option = next((opt for opt in ranked_options if opt["location"] == current_location), best_option)

        # 4. FINAL RECOMMENDATION LOGIC
        if best_option["location"] == current_location:
            return (f"Stay at {current_location}. It's currently your best option.", details)
            
        improvement_ratio = best_option["final_score"] / current_option["final_score"] if current_option["final_score"] > 0 else float('inf')
        details["improvement_ratio"] = round(improvement_ratio, 2)

        if improvement_ratio >= MOVE_ADVANTANTAGE_THRESHOLD:
            increase = best_option['final_score'] - current_option['final_score']
            return (f"Move to {best_option['location']} (~{best_option['travel_time_mins']:.0f} min drive). Potential for ${increase:.2f}/hr more.", details)
        else:
            return (f"Stay at {current_location}. Moving to {best_option['location']} is not a significant improvement right now.", details)

def load_data_from_excel(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    Loads all necessary sheets from the specified Excel file into a dictionary of DataFrames.
    """
    try:
        # Load multiple sheets from the single Excel file.
        earners_df = pd.read_excel(file_path, sheet_name="earners")
        rides_trips_df = pd.read_excel(file_path, sheet_name="rides_trips")
        heatmap_df = pd.read_excel(file_path, sheet_name="heatmap")
        incentives_df = pd.read_excel(file_path, sheet_name="incentives_weekly")
        merchants_df = pd.read_excel(file_path, sheet_name="merchants")
        return {
            "earners": earners_df,
            "rides_trips": rides_trips_df,
            "heatmap": heatmap_df,
            "incentives_weekly": incentives_df,
            "merchants": merchants_df
        }
    except FileNotFoundError:
        print(f"Error: The file was not found at '{file_path}'")
        print("Please ensure your Excel file is in the 'data' directory and named 'data_sets.xlsx'.")
        return None
    except Exception as e:
        print(f"An error occurred while reading the Excel file: {e}")
        return None

def main():
    """
    Interactive main function to simulate a real-time recommendation for a driver.
    """
    # --- 1. Load and Prepare Data from Excel file ---
    excel_file_path = "data/data_sets.xlsx"
    all_data = load_data_from_excel(excel_file_path)
    
    if not all_data:
        return

    earners_df = all_data["earners"]
    rides_trips_df = all_data["rides_trips"]
    heatmap_df = all_data["heatmap"]
    incentives_df = all_data["incentives_weekly"]
    merchants_df = all_data["merchants"]
    
    # Build a comprehensive hex_id to lat/lon mapping from multiple sources.
    print("Building location mapping...")
    merchant_locs = merchants_df[["hex_id9", "lat", "lon"]].copy()
    ride_pickup_locs = rides_trips_df[["pickup_hex_id9", "pickup_lat", "pickup_lon"]].copy()
    ride_pickup_locs.columns = ["hex_id9", "lat", "lon"]
    ride_dropoff_locs = rides_trips_df[["drop_hex_id9", "drop_lat", "drop_lon"]].copy()
    ride_dropoff_locs.columns = ["hex_id9", "lat", "lon"]
    
    hex_mapping = pd.concat([merchant_locs, ride_pickup_locs, ride_dropoff_locs]).drop_duplicates(subset=["hex_id9"]).set_index("hex_id9")
    print("Location mapping complete.")


    # --- 2. Initialize AI and Engine ---
    predictor = DemandPredictor(heatmap_data=heatmap_df)
    engine = DecisionEngine(predictor=predictor, rides_trips_data=rides_trips_df)
    
    # --- 3. Get Real-Time Inputs from the User ---
    print("\n--- Uber Co-Pilot: Real-Time Recommendation ---")
    
    while True:
        driver_id = input("Enter your Driver ID (e.g., E10000): ").strip()
        if driver_id in earners_df['earner_id'].values:
            driver_info = earners_df[earners_df['earner_id'] == driver_id].iloc[0]
            break
        else:
            print("Driver ID not found. Please try again.")
    
    current_week = '2023-W14'
    print(f"\nChecking for active quests for week {current_week}...")
    active_quest = None

    quest_info = incentives_df[
        (incentives_df['earner_id'] == driver_id) & (incentives_df['week'] == current_week) & (incentives_df['achieved'] == False)
    ]

    if not quest_info.empty:
        quest_row = quest_info.iloc[0]
        active_quest = { "type": "trip_count", "target": quest_row['target_jobs'], "progress": quest_row['completed_jobs'], "deadline_hours": 48, "reward": quest_row['bonus_eur'] }
        print(f"Active Quest Found: Complete {quest_row['target_jobs']} trips for a €{quest_row['bonus_eur']} bonus. (Progress: {quest_row['completed_jobs']}/{quest_row['target_jobs']})")
    else:
        print("No active quest found for this week.")

    while True:
        try:
            hours_to_drive = float(input("\nHow many more hours do you want to drive? "))
            if hours_to_drive > 0:
                time_remaining_mins = hours_to_drive * 60
                break
            else:
                print("Please enter a positive number of hours.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    # MODIFIED: Get current location via free-text input and on-demand conversion.
    print("\nSome available locations include 'Amsterdam Centraal', 'TU Delft', 'Utrecht Centraal'")
    while True:
        user_input_location = input("Enter your approximate current location: ").strip().lower()
        found_location = False
        # Search through all known hexes for a match.
        for hex_id in hex_mapping.index:
            # Convert hex to readable name on the fly.
            readable_name = get_location_from_hex(hex_id, hex_mapping)
            if user_input_location in readable_name.lower():
                current_loc_hex = hex_id
                print(f"--> Location matched: {readable_name}")
                found_location = True
                break
        if found_location:
            break
        else:
            print("Location not found in our data. Please try a more general name (e.g., a street or neighborhood).")
    
    # --- 6. Simulate Driver State & Run Engine ---
    hours_online_sim = random.uniform(1, 4)
    jobs_completed_sim = random.randint(2, 8)
    
    print("\n--- Generating Recommendation ---")
    print(f"Simulating driver state: {hours_online_sim:.1f} hours online, {jobs_completed_sim} jobs completed.")
    
    candidate_locations = { current_loc_hex: {"distance_km": 0, "travel_time_mins": 0} }
    for loc in heatmap_df.sample(3)["msg.predictions.hexagon_id_9"]:
         if loc != current_loc_hex:
            dist = random.uniform(1.0, 5.0)
            time = dist * 2.5
            candidate_locations[loc] = {"distance_km": dist, "travel_time_mins": time}

    recommendation, details = engine.get_recommendation(
        current_location=current_loc_hex,
        city_id=driver_info['home_city_id'],
        fuel_type=driver_info['fuel_type'],
        hours_online=hours_online_sim,
        jobs_completed=jobs_completed_sim,
        time_remaining_in_shift_mins=time_remaining_mins,
        candidate_locations=candidate_locations,
        active_quest=active_quest
    )

    # --- 7. Display Result with Readable Names ---
    readable_recommendation = recommendation
    all_hex_ids = list(candidate_locations.keys())
    for hex_id in all_hex_ids:
        if hex_id in readable_recommendation:
            readable_loc = get_location_from_hex(hex_id, hex_mapping)
            readable_recommendation = readable_recommendation.replace(hex_id, f"'{readable_loc}'")
            
    print("\n=====================================")
    print(f"Recommendation for {driver_id}:")
    print(f"► {readable_recommendation}")
    print("=====================================")
    print(f"Fatigue Level: {details.get('fatigue_level', 'N/A')}")
    if details.get('ranked_options'):
        print("\nTop Options Analyzed:")
        for opt in details['ranked_options']:
            loc_name = get_location_from_hex(opt['location'], hex_mapping)
            print(f"  - {loc_name}: Score={opt['final_score']:.2f} (Effective EPH: ${opt['effective_eph']:.2f})")

if __name__ == "__main__":
    main()

