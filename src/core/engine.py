# UberDriverAdvisor and related logic from original engine.py
"""
Uber Driver Advisor - Real Data Implementation
Run this after loading your Excel data.
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

class UberDriverAdvisor:
    """Advises Uber drivers on optimal actions based on real-time hotspots and surge."""
    FATIGUE_CRITICAL_THRESHOLD = 0.8
    MAX_HOURS_BEFORE_BREAK = 10
    MIN_MOVE_ADVANTAGE = 1.25
    MAX_TRAVEL_DISTANCE_KM = 15  # 30 min at 30km/h
    AVG_CITY_SPEED_KMH = 30
    WORK_DURATION_HOURS = 1
    def __init__(self, ride_trips: pd.DataFrame, eats_orders: pd.DataFrame, heatmap: pd.DataFrame, surge_by_hour: pd.DataFrame):
        self.ride_trips = ride_trips
        self.eats_orders = eats_orders
        self.heatmap = heatmap
        self.surge_by_hour = surge_by_hour
        self._prepare_hex_coordinates()
    def _prepare_hex_coordinates(self):
        rides_coords = self.ride_trips[['pickup_hex_id9', 'pickup_lat', 'pickup_lon']].drop_duplicates()
        eats_coords = self.eats_orders[['pickup_hex_id9', 'pickup_lat', 'pickup_lon']].drop_duplicates()
        self.hex_coords = pd.concat([rides_coords, eats_coords]).drop_duplicates('pickup_hex_id9')
        self.hex_coords = self.hex_coords.set_index('pickup_hex_id9')
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c
    def compute_fatigue(self, total_hours_driven: float, recent_jobs: int) -> float:
        if total_hours_driven <= 8:
            hour_fatigue = total_hours_driven / 16
        else:
            hour_fatigue = 0.5 + (total_hours_driven - 8) / 8
        job_fatigue = min(0.5, recent_jobs / 30)
        total_fatigue = min(1.0, hour_fatigue + job_fatigue)
        return round(total_fatigue, 3)
    def get_driver_status(self, driver_id: str, current_time: str) -> Dict:
        current_dt = pd.to_datetime(current_time)
        current_date = current_dt.date()
        rides = self.ride_trips[(self.ride_trips['driver_id'] == driver_id) & (pd.to_datetime(self.ride_trips['start_time']).dt.date == current_date) & (pd.to_datetime(self.ride_trips['start_time']) <= current_dt)].copy()
        eats = self.eats_orders[(self.eats_orders['courier_id'] == driver_id) & (pd.to_datetime(self.eats_orders['start_time']).dt.date == current_date) & (pd.to_datetime(self.eats_orders['start_time']) <= current_dt)].copy()
        if rides.empty and eats.empty:
            return {'error': f'No activity found for {driver_id} on {current_date} up to {current_time}'}
        total_hours = rides['duration_mins'].sum() / 60 + eats['duration_mins'].sum() / 60
        total_jobs = len(rides) + len(eats)
        if not rides.empty:
            last = rides.sort_values('start_time').iloc[-1]
            current_hex = last['pickup_hex_id9']
            current_lat = last['pickup_lat']
            current_lon = last['pickup_lon']
            city_id = last['city_id']
        else:
            last = eats.sort_values('start_time').iloc[-1]
            current_hex = last['pickup_hex_id9']
            current_lat = last['pickup_lat']
            current_lon = last['pickup_lon']
            city_id = last['city_id']
        fatigue = self.compute_fatigue(total_hours, total_jobs)
        return {
            'driver_id': driver_id,
            'current_time': current_time,
            'current_hex': current_hex,
            'current_lat': current_lat,
            'current_lon': current_lon,
            'city_id': city_id,
            'total_hours': total_hours,
            'total_jobs': total_jobs,
            'fatigue': fatigue
        }
    def find_hotspots(self, city_id: int, current_hour: int, current_hex: str, current_lat: float, current_lon: float) -> pd.DataFrame:
        city_heatmap = self.heatmap[self.heatmap['msg.city_id'] == city_id].copy()
        if city_heatmap.empty:
            return pd.DataFrame()
        surge_data = self.surge_by_hour[(self.surge_by_hour['city_id'] == city_id) & (self.surge_by_hour['hour'] == current_hour)]
        surge_multiplier = 1.0 if surge_data.empty else surge_data['surge_multiplier'].iloc[0]
        median_eph = city_heatmap['msg.predictions.predicted_eph'].median()
        hotspots = city_heatmap[city_heatmap['msg.predictions.predicted_eph'] * surge_multiplier > median_eph].copy()
        hotspots = hotspots.merge(self.hex_coords, left_on='msg.predictions.hexagon_id_9', right_index=True, how='left')
        hotspots = hotspots.dropna(subset=['pickup_lat', 'pickup_lon'])
        if hotspots.empty:
            return pd.DataFrame()
        hotspots['distance_km'] = hotspots.apply(lambda row: self.haversine_distance(current_lat, current_lon, row['pickup_lat'], row['pickup_lon']), axis=1)
        hotspots = hotspots[(hotspots['distance_km'] > 0.5) & (hotspots['distance_km'] <= self.MAX_TRAVEL_DISTANCE_KM)]
        if hotspots.empty:
            return pd.DataFrame()
        hotspots['travel_time_mins'] = (hotspots['distance_km'] / self.AVG_CITY_SPEED_KMH) * 60
        hotspots['roundtrip_time_mins'] = hotspots['travel_time_mins'] * 2
        work_minutes = self.WORK_DURATION_HOURS * 60
        hotspots['effective_eph'] = (hotspots['msg.predictions.predicted_eph'] * work_minutes) / (work_minutes + hotspots['roundtrip_time_mins'])
        hotspots['effective_eph'] = hotspots['effective_eph'] * surge_multiplier
        hotspots['surge_multiplier'] = surge_multiplier
        return hotspots.sort_values('effective_eph', ascending=False)
    def recommend_action(self, driver_id: str, current_time: str, verbose: bool = True) -> Dict:
        status = self.get_driver_status(driver_id, current_time)
        if 'error' in status:
            if verbose:
                print(f"\n{status['error']}\n")
            return status
        if status['fatigue'] >= self.FATIGUE_CRITICAL_THRESHOLD:
            status['recommendation'] = "Take a break - your fatigue level is critically high"
            status['action'] = 'break'
            if verbose:
                self._print_output(status, None, None)
            return status
        if status['total_hours'] >= self.MAX_HOURS_BEFORE_BREAK:
            status['recommendation'] = f"Take a break - you've worked {status['total_hours']:.1f} hours today"
            status['action'] = 'break'
            if verbose:
                self._print_output(status, None, None)
            return status
        current_dt = pd.to_datetime(current_time)
        current_hour = current_dt.hour
        current_eph_data = self.heatmap[(self.heatmap['msg.city_id'] == status['city_id']) & (self.heatmap['msg.predictions.hexagon_id_9'] == status['current_hex'])]
        current_eph = 20.0 if current_eph_data.empty else current_eph_data['msg.predictions.predicted_eph'].iloc[0]
        fatigue_multiplier = 1 - (status['fatigue'] * 0.7)
        current_effective_eph = current_eph * fatigue_multiplier
        status['current_eph'] = round(current_eph, 2)
        status['current_effective_eph'] = round(current_effective_eph, 2)
        hotspots = self.find_hotspots(status['city_id'], current_hour, status['current_hex'], status['current_lat'], status['current_lon'])
        if hotspots.empty:
            status['recommendation'] = "Stay at current location - no better hotspots within 30min"
            status['action'] = 'stay'
            status['reason'] = 'no_hotspots'
            if verbose:
                self._print_output(status, None, hotspots)
            return status
        best = hotspots.iloc[0]
        best_effective_eph = best['effective_eph'] * fatigue_multiplier
        status['best_hex'] = best['msg.predictions.hexagon_id_9']
        status['best_eph'] = round(best['msg.predictions.predicted_eph'], 2)
        status['best_effective_eph'] = round(best_effective_eph, 2)
        status['best_distance_km'] = round(best['distance_km'], 2)
        status['best_travel_time_mins'] = round(best['travel_time_mins'], 1)
        improvement_ratio = best_effective_eph / current_effective_eph if current_effective_eph > 0 else float('inf')
        status['improvement_ratio'] = round(improvement_ratio, 2)
        if improvement_ratio >= self.MIN_MOVE_ADVANTAGE:
            earning_increase = best_effective_eph - current_effective_eph
            status['recommendation'] = (f"Move to {status['best_hex']} - {earning_increase:.2f}/hr increase " f"({status['best_distance_km']}km, ~{status['best_travel_time_mins']:.0f} min drive)")
            status['action'] = 'move'
        else:
            status['recommendation'] = (f"Stay at current location - improvement only {(improvement_ratio - 1) * 100:.0f}% " f"(need {(self.MIN_MOVE_ADVANTAGE - 1) * 100:.0f}%)")
            status['action'] = 'stay'
            status['reason'] = 'insufficient_improvement'
        if verbose:
            self._print_output(status, best, hotspots)
        return status
    def _print_output(self, status: Dict, best_hotspot, all_hotspots):
        print(f"\n{'='*70}")
        print(f"UBER DRIVER ADVISOR - {status['current_time']}")
        print(f"{'='*70}")
        print(f"Driver ID: {status['driver_id']}")
        print(f"Current Location: {status['current_hex']} (City {status['city_id']})")
        print(f"\n--- Driver Status ---")
        print(f"Hours worked today: {status['total_hours']:.1f}")
        print(f"Jobs completed: {status['total_jobs']}")
        print(f"Fatigue level: {status['fatigue']:.2f} ({self._fatigue_desc(status['fatigue'])})")
        if 'current_eph' in status:
            print(f"\n--- Current Location ---")
            print(f"Base EPH: {status['current_eph']:.2f}/hr")
            print(f"Effective EPH (fatigue-adjusted): {status['current_effective_eph']:.2f}/hr")
        if best_hotspot is not None:
            print(f"\n--- Best Hotspot ---")
            print(f"Location: {status['best_hex']}")
            print(f"Distance: {status['best_distance_km']}km (~{status['best_travel_time_mins']:.0f} min)")
            print(f"Base EPH: {status['best_eph']:.2f}/hr")
            print(f"Effective EPH: {status['best_effective_eph']:.2f}/hr")
            print(f"Improvement: {(status['improvement_ratio'] - 1) * 100:.0f}%")
        print(f"\n--- RECOMMENDATION ---")
        print(f"{status['recommendation']}")
        if all_hotspots is not None and not all_hotspots.empty:
            print(f"\n--- Top 5 Hotspots ---")
            top5 = all_hotspots.head(5)[['msg.predictions.hexagon_id_9', 'distance_km', 'travel_time_mins', 'msg.predictions.predicted_eph', 'effective_eph']].copy()
            top5.columns = ['Hex', 'Dist(km)', 'Travel(min)', 'Base EPH', 'Eff EPH']
            for col in ['Dist(km)', 'Travel(min)', 'Base EPH', 'Eff EPH']:
                top5[col] = top5[col].round(2)
            print(top5.to_string(index=False))
        print(f"{'='*70}\n")
    @staticmethod
    def _fatigue_desc(fatigue: float) -> str:
        if fatigue < 0.3:
            return "Fresh"
        elif fatigue < 0.5:
            return "Moderate"
        elif fatigue < 0.7:
            return "Tired"
        elif fatigue < 0.85:
            return "Very Tired"
        else:
            return "Exhausted"
