import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional

# --- Configuration Constants ---
# Profitability Analysis
MOVE_ADVANTAGE_THRESHOLD = 1.25  # A new location must be at least 25% better to justify a move.
# REMOVED: AVG_FARE_PER_TRIP is now calculated dynamically.

# Fuel Costs
FUEL_TYPE_COSTS_PER_KM = {
    "gas": 0.35,
    "hybrid": 0.25,
    "EV": 0.15,
    "unknown": 0.30
}

# Personalization Filters
FATIGUE_HIGH_THRESHOLD = 0.6
FATIGUE_CRITICAL_THRESHOLD = 0.8
max_hours_nonstop = 5


class DemandPredictor:
    """
    A mock AI model to predict Earnings Per Hour (EPH) for different locations.
    """
    def __init__(self, heatmap_data: pd.DataFrame):
        self._eph_predictions = pd.Series(
            heatmap_data["msg.predictions.predicted_eph"].values,   # extracts the eph from the heatmap (values of dictionary)
            index=heatmap_data["msg.predictions.hexagon_id_9"]      # extracts the location from heatmap (keys of dictionary)
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
        
        self.predictor = predictor #innitilize value for predictor
        
        self.avg_fare_by_city = rides_trips_data.groupby('city_id')['fare_amount'].mean().to_dict() # ??? 

    def _compute_fatigue(self, hours_online: float, jobs_completed: int) -> float:

        hour_fatigue = min(1.0, (hours_online / max_hours_nonstop))
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
        desired_end_location: Optional[str] = None,) -> Tuple[str, Dict]:
        
        """
        Generates the best next move for a driver by running the full decision algorithm.
        """
        # 1. CALCULATE DRIVER'S CURRENT STATE
        fatigue_level = self._compute_fatigue(hours_online, jobs_completed)
        details = {
            "fatigue_level": round(fatigue_level, 2),
            "hours_online": hours_online,
            "time_remaining_mins": time_remaining_in_shift_mins,
            "active_quest": active_quest
        }

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
            
            options.append({
                "location": loc, "distance_km": dist_km, "travel_time_mins": travel_time_mins,
                "raw_eph": raw_eph, "effective_eph": effective_eph
            })

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
                    # MODIFIED: Look up the city-specific average fare. Fallback to 15 if city is unknown.
                    avg_fare = self.avg_fare_by_city.get(city_id, 15.0)
                    estimated_trip_rate = option["raw_eph"] / avg_fare
                    
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

        if improvement_ratio >= MOVE_ADVANTAGE_THRESHOLD:
            increase = best_option['final_score'] - current_option['final_score']
            return (f"Move to {best_option['location']} (~{best_option['travel_time_mins']:.0f} min drive). Potential for ${increase:.2f}/hr more.", details)
        else:
            return (f"Stay at {current_location}. Moving to {best_option['location']} is not a significant improvement right now.", details)


def main():
    """Example usage of the DecisionEngine to simulate different driver scenarios."""
    # --- 1. Load and Prepare Data ---
    heatmap_df = pd.DataFrame({
        "msg.predictions.hexagon_id_9": ["Delft Station", "Delft Markt", "TU Delft", "IKEA", "The Hague HS", "Home"],
        "msg.predictions.predicted_eph": [32.50, 28.00, 25.00, 22.00, 35.00, 15.00]
    })
    
    # MODIFIED: A richer earners_df with home city
    earners_df = pd.DataFrame({
        'earner_id': ['E-FRESH', 'E-TIRED', 'E-QUEST'],
        'fuel_type': ['gas', 'hybrid', 'EV'],
        'home_city_id': [1, 1, 2] # Added city context
    })

    # MODIFIED: Sample rides_trips data to calculate average fare
    rides_trips_df = pd.DataFrame({
        'city_id': [1, 1, 1, 2, 2, 2],
        'fare_amount': [12.50, 18.00, 14.50, 22.00, 25.50, 23.00]
        # City 1 avg fare = 15.0
        # City 2 avg fare = 23.5
    })
    
    # --- 2. Initialize AI and Engine ---
    predictor = DemandPredictor(heatmap_data=heatmap_df)
    # MODIFIED: Pass the rides_trips data to the engine
    engine = DecisionEngine(predictor=predictor, rides_trips_data=rides_trips_df)
    
    # --- 3. Run Scenarios ---
    
    print("\n--- Scenario 1: Fresh driver (gas car), no quest ---")
    driver_id = "E-FRESH"
    driver_info = earners_df[earners_df['earner_id'] == driver_id].iloc[0]
    recommendation, _ = engine.get_recommendation(
        current_location="IKEA", city_id=driver_info['home_city_id'], fuel_type=driver_info['fuel_type'], 
        hours_online=1.5, jobs_completed=3, time_remaining_in_shift_mins=360,
        candidate_locations={
            "IKEA": {"distance_km": 0, "travel_time_mins": 0}, "Delft Station": {"distance_km": 3.0, "travel_time_mins": 8},
            "Delft Markt": {"distance_km": 4.5, "travel_time_mins": 12}, "TU Delft": {"distance_km": 2.5, "travel_time_mins": 7}
        }
    )
    print(f"Recommendation: {recommendation}")

    print("\n--- Scenario 2: Tired driver (hybrid car), end of shift ---")
    driver_id = "E-TIRED"
    driver_info = earners_df[earners_df['earner_id'] == driver_id].iloc[0]
    recommendation, _ = engine.get_recommendation(
        current_location="Delft Markt", city_id=driver_info['home_city_id'], fuel_type=driver_info['fuel_type'],
        hours_online=6.5, jobs_completed=15, time_remaining_in_shift_mins=60,
        candidate_locations={
            "Delft Markt": {"distance_km": 0, "travel_time_mins": 0}, "Delft Station": {"distance_km": 1.0, "travel_time_mins": 4},
            "TU Delft": {"distance_km": 2.0, "travel_time_mins": 6}, "IKEA": {"distance_km": 4.5, "travel_time_mins": 11}
        }
    )
    print(f"Recommendation: {recommendation}")

    print("\n--- Scenario 3: Quest bonus active (EV car) ---")
    driver_id = "E-QUEST"
    driver_info = earners_df[earners_df['earner_id'] == driver_id].iloc[0]
    active_quest = {
        "type": "trip_count", "target": 40, "progress": 32,
        "deadline_hours": 8, "reward": 50
    }
    recommendation, _ = engine.get_recommendation(
        current_location="IKEA", city_id=driver_info['home_city_id'], fuel_type=driver_info['fuel_type'],
        hours_online=2.0, jobs_completed=5, time_remaining_in_shift_mins=300,
        candidate_locations={
            "IKEA": {"distance_km": 0, "travel_time_mins": 0}, "Delft Station": {"distance_km": 3.0, "travel_time_mins": 8},
            "Delft Markt": {"distance_km": 4.5, "travel_time_mins": 12}
        },
        active_quest=active_quest
    )
    print(f"Recommendation: {recommendation}")

if __name__ == "__main__":
    main()

