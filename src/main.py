
# in terminal : pip install pandas
#               pip install openpyxl

import pandas as pd
from engine import run_interactive

def load_excel_data(file_path, name):
  
  df = pd.read_excel(file_path, sheet_name=name)
  return df

path_to_file = "/Users/chahid/projects/uber-copilot/data/data_sets.xlsx" 


#my_uber_data = load_excel_data(path_to_file)

earners = load_excel_data(path_to_file, "earners")
ride_trips = load_excel_data(path_to_file, "rides_trips")
eats_orders = load_excel_data(path_to_file, "eats_orders")
surge_by_hour = load_excel_data(path_to_file, "surge_by_hour")
heatmap = load_excel_data(path_to_file, "heatmap")

run_interactive(ride_trips, eats_orders, heatmap, surge_by_hour)