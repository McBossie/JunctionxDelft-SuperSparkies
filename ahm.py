import pandas as pd

def load_excel_data(file_path):

  df = pd.read_excel(file_path)
  return df

path_to_file = "data/data_sets.xlsx" 

my_uber_data = load_excel_data(path_to_file)

print(my_uber_data.head())

# in terminal : pip install pandas
#               pip install openpyxl
