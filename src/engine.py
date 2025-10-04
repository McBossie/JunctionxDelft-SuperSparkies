from typing import Dict
import pandas as pd

def recommend_action(current_loc: str, fatigue_level: float, earning_per_hour: Dict[str, float]) -> str:
    current_score = earning_per_hour.get(current_loc, 0) * (1 - fatigue_level)
    best_loc = max(earning_per_hour, key=earning_per_hour.get)
    best_score = earning_per_hour[best_loc] * (1 - fatigue_level)
    
    if fatigue_level > 0.99:
        return "Take a break"
    elif best_score > current_score * 1.2:
        return f"Move to {best_loc}"
    else:
        return "Stay"

def compute_fatigue(total_hours_driven: float, recent_jobs: int) -> float:
    return min(1.0, (total_hours_driven / 12) + (recent_jobs / 20))

def rank_locations_by_eph(earning_per_hour: Dict[str, float], fatigue_level: float) -> Dict[str, float]:
    return {loc: eph * (1 - fatigue_level) for loc, eph in earning_per_hour.items()}


def main(earnings_daily: pd.DataFrame, heatmap: pd.DataFrame, earner_id: str, date: str):
    """
    Example main function to test Uber Co-Pilot recommendations.

    Args:
        earnings_daily (DataFrame): daily earnings per earner
        heatmap (DataFrame): predicted earnings per hex
        earner_id (str): which driver/courier to simulate
        date (str): date of simulation, format 'YYYY-MM-DD'
    """
    # Filter data for this earner and date
    df_earner = earnings_daily[(earnings_daily["earner_id"] == earner_id) & 
                               (earnings_daily["date"] == date)]
    if df_earner.empty:
        print(f"No data found for earner {earner_id} on {date}")
        return

    total_hours = df_earner["rides_duration_mins"].sum() / 60 + df_earner["eats_duration_mins"].sum() / 60
    recent_jobs = df_earner["total_jobs"].sum()
    fatigue = compute_fatigue(total_hours, recent_jobs)

    # Mock current location as the hex with most recent job, or take first one
    current_loc = df_earner.get("pickup_hex_id9", pd.Series(["hex1"])).iloc[-1]

    # Build earning_per_hour dictionary from heatmap for the earner's city
    city_id = df_earner["city_id"].iloc[0]
    df_heatmap = heatmap[heatmap["msg.city_id"] == city_id]
    earning_per_hour = dict(zip(df_heatmap["msg.predictions.hexagon_id_9"], 
                                df_heatmap["msg.predictions.predicted_eph"]))

    # Get recommendation
    action = recommend_action(current_loc, fatigue, earning_per_hour)

    print(f"Earner: {earner_id} | Date: {date}")
    print(f"Total hours: {total_hours:.2f}, Jobs: {recent_jobs}, Fatigue: {fatigue:.2f}")
    print(f"Current location: {current_loc}")
    print(f"Recommended action: {action}")


# Example usage with dummy data
if __name__ == "__main__":
    # Assuming your teammate will load these from Excel
    earnings_daily = pd.DataFrame({
        "earner_id": ["E10000"],
        "date": ["2023-01-12"],
        "rides_duration_mins": [60],
        "eats_duration_mins": [30],
        "total_jobs": [3],
        "pickup_hex_id9": ["hex1"],
        "city_id": [1]
    })

    heatmap = pd.DataFrame({
        "msg.city_id": [1, 1, 1],
        "msg.predictions.hexagon_id_9": ["hex1", "hex2", "hex3"],
        "msg.predictions.predicted_eph": [20, 25, 18]
    })

    main(earnings_daily, heatmap, earner_id="E10000", date="2023-01-12")
