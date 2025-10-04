
from core.data_loader import load_data_from_excel
from core.engine import UberDriverAdvisor

def run_interactive(ride_trips, eats_orders, heatmap, surge_by_hour):
    advisor = UberDriverAdvisor(ride_trips, eats_orders, heatmap, surge_by_hour)
    # ...existing code for interactive CLI...

if __name__ == "__main__":
    path_to_file = "/Users/chahid/projects/uber-copilot/data/data_sets.xlsx"
    all_data = load_data_from_excel(path_to_file)
    earners = all_data["earners"]
    ride_trips = all_data["rides_trips"]
    eats_orders = all_data["eats_orders"]
    surge_by_hour = all_data["surge_by_hour"] if "surge_by_hour" in all_data else None
    heatmap = all_data["heatmap"]
    run_interactive(ride_trips, eats_orders, heatmap, surge_by_hour)