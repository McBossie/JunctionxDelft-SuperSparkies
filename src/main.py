
# in terminal : pip install pandas
#               pip install openpyxl

import pandas as pd

def load_excel_data(file_path, name):
  
  df = pd.read_excel(file_path, sheet_name=name)
  return df

path_to_file = "data/data_sets.xlsx" 


#my_uber_data = load_excel_data(path_to_file)

earners = load_excel_data(path_to_file, "earners")
ride_trips = load_excel_data(path_to_file, "rides_trips")
eats_orders = load_excel_data(path_to_file, "eats_orders")
heatmap = load_excel_data(path_to_file, "heatmap")
