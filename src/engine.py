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
    
    # Configuration constants
    FATIGUE_CRITICAL_THRESHOLD = 0.8
    MAX_HOURS_BEFORE_BREAK = 10
    MIN_MOVE_ADVANTAGE = 1.25
    MAX_TRAVEL_DISTANCE_KM = 15  # 30 min at 30km/h

    eats_dates = pd.to_datetime(eats_orders['start_time'])
    min_date = min(ride_dates.min(), eats_dates.min())
    max_date = max(ride_dates.max(), eats_dates.max())
    
    print(f"\n{'='*70}")
    print("UBER DRIVER ADVISOR - INTERACTIVE MODE")
    print(f"{'='*70}")
    print(f"Total drivers: {len(all_drivers)}")
    print(f"Date range: {min_date.date()} to {max_date.date()}")
    print(f"{'='*70}\n")
    
    while True:
        # Get driver ID
        driver_id = input("Enter driver ID (or 'list' to see options, 'q' to quit): ").strip()
        
        if driver_id.lower() == 'q':
            print("Goodbye!")
            break
        
        if driver_id.lower() == 'list':
            print(f"\nShowing first 30 drivers:")
            for i, eid in enumerate(all_drivers[:30], 1):
                print(f"  {i}. {eid}")
            if len(all_drivers) > 30:
                print(f"  ... and {len(all_drivers) - 30} more")
            print()
            continue
        
        if driver_id not in all_drivers:
            print(f"❌ Driver '{driver_id}' not found. Try 'list' to see options.\n")
            continue
        
        # Get time
        time_input = input("Enter time (YYYY-MM-DD HH:MM:SS) or press Enter for latest: ").strip()
        
        if time_input == "":
            # Find latest time for this driver
            driver_rides = ride_trips[ride_trips['driver_id'] == driver_id]
            driver_eats = eats_orders[eats_orders['courier_id'] == driver_id]
            
            if not driver_rides.empty:
                latest = pd.to_datetime(driver_rides['start_time']).max()
            elif not driver_eats.empty:
                latest = pd.to_datetime(driver_eats['start_time']).max()
            else:
                print(f"❌ No data for {driver_id}\n")
                continue
            
            current_time = latest.strftime('%Y-%m-%d %H:%M:%S')
            print(f"Using latest time: {current_time}")
        else:
            current_time = time_input
        
        # Get recommendation
        advisor.recommend_action(driver_id, current_time, verbose=True)
        
        # Continue?
        another = input("Analyze another driver? (y/n): ").strip().lower()
        if another != 'y':
            print("Goodbye!")
            break
        print()

