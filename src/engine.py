from typing import Dict, Tuple, List
import pandas as pd
import numpy as np


class UberDriverAdvisor:
    """Advises Uber drivers on optimal actions based on earnings, fatigue, and location data."""
    
    # Configuration constants
    FATIGUE_CRITICAL_THRESHOLD = 0.8  # Must take break above this
    FATIGUE_HIGH_THRESHOLD = 0.6      # Reduced incentive to move
    MIN_MOVE_ADVANTAGE = 1.25         # 25% earning improvement to justify move
    MAX_HOURS_BEFORE_BREAK = 10       # Maximum continuous hours
    TRAVEL_TIME_PENALTY = 0.15        # Assume 15 min average travel time
    MOVE_COST_PER_KM = 0.5            # Estimated fuel/time cost
    
    def __init__(self, earnings_daily: pd.DataFrame, heatmap: pd.DataFrame):
        """
        Initialize advisor with earnings and heatmap data.
        
        Args:
            earnings_daily: DataFrame with driver earnings history
            heatmap: DataFrame with predicted earnings per location
        """
        self.earnings_daily = earnings_daily
        self.heatmap = heatmap
    
    def compute_fatigue(self, total_hours_driven: float, recent_jobs: int, 
                       hours_since_break: float = None) -> float:
        """
        Calculate driver fatigue level (0-1).
        
        Args:
            total_hours_driven: Total hours driven today
            recent_jobs: Number of jobs completed recently
            hours_since_break: Hours since last significant break
            
        Returns:
            Fatigue level between 0 (fresh) and 1 (exhausted)
        """
        # Base fatigue from hours (increases exponentially after 8 hours)
        if total_hours_driven <= 8:
            hour_fatigue = total_hours_driven / 16
        else:
            hour_fatigue = 0.5 + (total_hours_driven - 8) / 8
        
        # Job intensity fatigue (many short jobs = more stressful)
        job_fatigue = min(0.5, recent_jobs / 30)
        
        # Continuous work fatigue
        if hours_since_break is not None:
            continuous_fatigue = min(0.4, hours_since_break / 15)
        else:
            continuous_fatigue = 0
        
        total_fatigue = min(1.0, hour_fatigue + job_fatigue + continuous_fatigue)
        return round(total_fatigue, 3)
    
    def calculate_effective_earnings(self, eph: float, fatigue: float, 
                                     travel_time_mins: float = 0) -> float:
        """
        Calculate effective earnings per hour adjusted for fatigue and travel.
        
        Args:
            eph: Base earnings per hour at location
            fatigue: Current fatigue level
            travel_time_mins: Time to reach location
            
        Returns:
            Adjusted effective earnings per hour
        """
        # Fatigue reduces both earning potential and enjoyment
        fatigue_multiplier = 1 - (fatigue * 0.7)  # Max 70% reduction
        
        # Travel time reduces effective hourly rate
        if travel_time_mins > 0:
            # Amortize travel time over next 2 hours of work
            effective_hours = 2 + (travel_time_mins / 60)
            travel_multiplier = 2 / effective_hours
        else:
            travel_multiplier = 1.0
        
        return eph * fatigue_multiplier * travel_multiplier
    
    def recommend_action(self, current_loc: str, fatigue_level: float, 
                        earning_per_hour: Dict[str, float],
                        total_hours_today: float,
                        distances: Dict[str, float] = None) -> Tuple[str, Dict]:
        """
        Recommend optimal action for driver.
        
        Args:
            current_loc: Current location hex ID
            fatigue_level: Current fatigue level (0-1)
            earning_per_hour: Dict of location -> predicted EPH
            total_hours_today: Total hours worked today
            distances: Optional dict of location -> distance in km
            
        Returns:
            Tuple of (recommendation string, details dict)
        """
        details = {
            "fatigue_level": fatigue_level,
            "current_eph": earning_per_hour.get(current_loc, 0),
            "total_hours": total_hours_today
        }
        
        # Critical fatigue check
        if fatigue_level >= self.FATIGUE_CRITICAL_THRESHOLD:
            return ("Take a break - your fatigue level is too high for safe driving", details)
        
        # Maximum hours check
        if total_hours_today >= self.MAX_HOURS_BEFORE_BREAK:
            return (f"Take a break - you've worked {total_hours_today:.1f} hours today", details)
        
        # Calculate current effective earnings
        current_eph = earning_per_hour.get(current_loc, 0)
        current_effective = self.calculate_effective_earnings(current_eph, fatigue_level)
        details["current_effective_eph"] = round(current_effective, 2)
        
        # Find best alternative location
        best_loc = None
        best_effective = current_effective
        best_raw_eph = current_eph
        
        for loc, eph in earning_per_hour.items():
            if loc == current_loc:
                continue
            
            # Calculate travel time (use distance if available, else estimate)
            travel_time = 0
            if distances and loc in distances:
                # Assume 30 km/h average speed in city
                travel_time = (distances[loc] / 30) * 60
            
            effective = self.calculate_effective_earnings(eph, fatigue_level, travel_time)
            
            if effective > best_effective:
                best_loc = loc
                best_effective = effective
                best_raw_eph = eph
        
        details["best_location"] = best_loc
        details["best_eph"] = best_raw_eph
        details["best_effective_eph"] = round(best_effective, 2)
        
        # Decision logic
        if best_loc is None:
            return ("Stay at current location - it's your best option", details)
        
        # High fatigue reduces willingness to move
        if fatigue_level >= self.FATIGUE_HIGH_THRESHOLD:
            move_threshold = self.MIN_MOVE_ADVANTAGE * 1.3  # Need 30% more incentive
        else:
            move_threshold = self.MIN_MOVE_ADVANTAGE
        
        improvement_ratio = best_effective / current_effective if current_effective > 0 else float('inf')
        details["improvement_ratio"] = round(improvement_ratio, 2)
        
        if improvement_ratio >= move_threshold:
            earning_increase = best_effective - current_effective
            return (
                f"Move to {best_loc} - potential ${earning_increase:.2f}/hr increase "
                f"(${best_effective:.2f}/hr vs ${current_effective:.2f}/hr)",
                details
            )
        elif fatigue_level >= self.FATIGUE_HIGH_THRESHOLD:
            return (
                f"Stay at current location - you're fatigued and the move advantage "
                f"is only {(improvement_ratio - 1) * 100:.0f}%",
                details
            )
        else:
            return (
                f"Stay at current location - not enough advantage to move "
                f"({(improvement_ratio - 1) * 100:.0f}% improvement)",
                details
            )
    
    def rank_locations(self, fatigue_level: float, 
                       earning_per_hour: Dict[str, float],
                       top_n: int = 5) -> pd.DataFrame:
        """
        Rank all locations by effective earnings potential.
        
        Args:
            fatigue_level: Current fatigue level
            earning_per_hour: Dict of location -> predicted EPH
            top_n: Number of top locations to return
            
        Returns:
            DataFrame with ranked locations
        """
        rankings = []
        for loc, eph in earning_per_hour.items():
            effective = self.calculate_effective_earnings(eph, fatigue_level)
            rankings.append({
                "location": loc,
                "raw_eph": eph,
                "effective_eph": effective,
                "fatigue_adjusted": effective / eph if eph > 0 else 0
            })
        
        df = pd.DataFrame(rankings)
        df = df.sort_values("effective_eph", ascending=False).head(top_n)
        return df.reset_index(drop=True)
    
    def analyze_driver(self, earner_id: str, date: str, 
                      verbose: bool = True) -> Dict:
        """
        Analyze specific driver and provide recommendation.
        
        Args:
            earner_id: Driver ID
            date: Date to analyze
            verbose: Whether to print detailed output
            
        Returns:
            Dictionary with analysis results
        """
        # Filter data
        df_earner = self.earnings_daily[
            (self.earnings_daily["earner_id"] == earner_id) &
            (self.earnings_daily["date"] == date)
        ]
        
        if df_earner.empty:
            if verbose:
                print(f"No data found for earner {earner_id} on {date}")
            return {"error": "No data found"}
        
        # Calculate metrics
        total_hours = (
            df_earner["rides_duration_mins"].sum() / 60 + 
            df_earner["eats_duration_mins"].sum() / 60
        )
        recent_jobs = df_earner["total_jobs"].sum()
        fatigue = self.compute_fatigue(total_hours, recent_jobs)
        
        # Get current location
        if "pickup_hex_id9" in df_earner.columns:
            current_loc = df_earner["pickup_hex_id9"].iloc[-1]
        else:
            current_loc = "unknown"
        
        # Build earnings map
        city_id = df_earner["city_id"].iloc[0]
        df_heatmap = self.heatmap[self.heatmap["msg.city_id"] == city_id]
        
        earning_per_hour = dict(zip(
            df_heatmap["msg.predictions.hexagon_id_9"],
            df_heatmap["msg.predictions.predicted_eph"]
        ))
        
        # Get recommendation
        action, details = self.recommend_action(
            current_loc, fatigue, earning_per_hour, total_hours
        )
        
        # Print results
        if verbose:
            print(f"\n{'='*60}")
            print(f"UBER DRIVER ADVISOR - {date}")
            print(f"{'='*60}")
            print(f"Driver ID: {earner_id}")
            print(f"City: {city_id}")
            print(f"Current Location: {current_loc}")
            print(f"\n--- Driver Status ---")
            print(f"Hours worked today: {total_hours:.1f}")
            print(f"Jobs completed: {recent_jobs}")
            print(f"Fatigue level: {fatigue:.2f} ({self._fatigue_description(fatigue)})")
            print(f"\n--- Earnings Analysis ---")
            print(f"Current location EPH: ${details['current_eph']:.2f}")
            print(f"Effective EPH (fatigue-adjusted): ${details['current_effective_eph']:.2f}")
            
            if details.get('best_location'):
                print(f"Best alternative: {details['best_location']} (${details['best_eph']:.2f} EPH)")
            
            print(f"\n--- RECOMMENDATION ---")
            print(f"► {action}")
            print(f"{'='*60}\n")
            
            # Show top locations
            print("Top 5 Locations (Fatigue-Adjusted):")
            rankings = self.rank_locations(fatigue, earning_per_hour, top_n=5)
            print(rankings.to_string(index=False))
            print()
        
        return {
            "earner_id": earner_id,
            "date": date,
            "recommendation": action,
            "details": details,
            "total_hours": total_hours,
            "jobs": recent_jobs,
            "fatigue": fatigue
        }
    
    @staticmethod
    def _fatigue_description(fatigue: float) -> str:
        """Convert fatigue level to human description."""
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


def main():
    """Example usage with sample data."""
    
    # Sample earnings data
    earnings_daily = pd.DataFrame({
        "earner_id": ["E10000", "E10000", "E10001"],
        "date": ["2023-01-12", "2023-01-12", "2023-01-12"],
        "rides_duration_mins": [180, 120, 60],
        "eats_duration_mins": [60, 90, 30],
        "total_jobs": [8, 6, 3],
        "pickup_hex_id9": ["hex1", "hex1", "hex2"],
        "city_id": [1, 1, 1]
    })
    
    # Sample heatmap data
    heatmap = pd.DataFrame({
        "msg.city_id": [1, 1, 1, 1, 1],
        "msg.predictions.hexagon_id_9": ["hex1", "hex2", "hex3", "hex4", "hex5"],
        "msg.predictions.predicted_eph": [22, 28, 18, 25, 30]
    })
    
    # Initialize advisor
    advisor = UberDriverAdvisor(earnings_daily, heatmap)
    
    # Analyze drivers
    advisor.analyze_driver(earner_id="E10000", date="2023-01-12")
    advisor.analyze_driver(earner_id="E10001", date="2023-01-12")


if __name__ == "__main__":
    main()