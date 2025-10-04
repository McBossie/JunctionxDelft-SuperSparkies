# DecisionEngine, DemandPredictor, and constants from next_locdemo.py
import pandas as pd
import random
from typing import Optional, Dict, List, Tuple

MOVE_ADVANTANTAGE_THRESHOLD = 1.25
FUEL_TYPE_COSTS_PER_KM = { "gas": 0.35, "hybrid": 0.25, "EV": 0.15, "unknown": 0.30 }
FATIGUE_HIGH_THRESHOLD = 0.6
FATIGUE_CRITICAL_THRESHOLD = 0.8
MAX_HOURS_CONTINUOUS = 5

class DemandPredictor:
    def __init__(self, heatmap_data: pd.DataFrame):
        self._eph_predictions = pd.Series(
            heatmap_data["msg.predictions.predicted_eph"].values,
            index=heatmap_data["msg.predictions.hexagon_id_9"]
        ).to_dict()
    def predict_eph(self, locations: List[str]) -> Dict[str, float]:
        return {loc: self._eph_predictions.get(loc, 10.0) for loc in locations}

class DecisionEngine:
    def __init__(self, predictor: DemandPredictor, rides_trips_data: pd.DataFrame):
        self.predictor = predictor
        self.avg_fare_by_city = rides_trips_data.groupby('city_id')['fare_amount'].mean().to_dict()
    def _compute_fatigue(self, hours_online: float, jobs_completed: int) -> float:
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
            active_quest: Optional[Dict] = None,
            surge_by_hour: Optional[pd.DataFrame] = None,
            current_hour: Optional[int] = None
        ) -> Tuple[str, Dict]:

            fatigue_level = self._compute_fatigue(hours_online, jobs_completed)
            details = {
                "fatigue_level": round(fatigue_level, 2),
                "hours_online": hours_online,
                "time_remaining_mins": time_remaining_in_shift_mins,
                "active_quest": active_quest
            }

            if fatigue_level >= FATIGUE_CRITICAL_THRESHOLD:
                return ("CRITICAL: Take a break. Your fatigue level is too high for safe driving.", details)
            if hours_online > MAX_HOURS_CONTINUOUS:
                return (f"Take a break. You've been driving for {hours_online:.1f} hours straight.", details)

            if not candidate_locations:
                candidate_locations = {current_location: {"distance_km": 0, "travel_time_mins": 0}}

            predicted_eph = self.predictor.predict_eph(list(candidate_locations.keys()))
            details["predicted_eph"] = predicted_eph

            options = []
            for loc, loc_info in candidate_locations.items():
                travel_time_mins = loc_info["travel_time_mins"]
                dist_km = loc_info["distance_km"]

                if travel_time_mins >= time_remaining_in_shift_mins:
                    continue

                vehicle_cost_per_km = FUEL_TYPE_COSTS_PER_KM.get(fuel_type, 0.30)
                raw_eph = predicted_eph.get(loc, 10.0)
                time_efficiency_multiplier = 60 / (60 + travel_time_mins)
                travel_cost_hourly = (dist_km * vehicle_cost_per_km) * (60 / (travel_time_mins + 1)) if travel_time_mins > 0 else 0

                surge_multiplier = 1.0
                if surge_by_hour is not None and current_hour is not None:
                    if current_hour in surge_by_hour.index:
                        row = surge_by_hour.loc[current_hour]
                        if isinstance(row, dict):
                            surge_multiplier = row.get(loc, 1.0)
                        else:
                            surge_multiplier = getattr(row, loc, 1.0)

                effective_eph = ((raw_eph * time_efficiency_multiplier) * surge_multiplier) - travel_cost_hourly

                options.append({
                    "location": loc,
                    "distance_km": dist_km,
                    "travel_time_mins": travel_time_mins,
                    "raw_eph": raw_eph,
                    "effective_eph": effective_eph,
                    "surge_multiplier": surge_multiplier
                })

            if not options:
                return ("Stay put. No viable alternative locations found within your shift time.", details)

            ranked_options = sorted(options, key=lambda x: x["effective_eph"], reverse=True)
            details["ranked_options"] = ranked_options
            best_option = ranked_options[0]

            if best_option["location"] != current_location and best_option["effective_eph"] - predicted_eph.get(current_location, 0) > MOVE_ADVANTANTAGE_THRESHOLD:
                return (f"Move to {best_option['location']} for higher earnings.", details)
            else:
                return ("Stay at your current location.", details)