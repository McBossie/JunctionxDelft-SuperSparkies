# Data loading and hex mapping utilities
import pandas as pd

def load_data_from_excel(file_path: str) -> dict:
    try:
        earners_df = pd.read_excel(file_path, sheet_name="earners")
        rides_trips_df = pd.read_excel(file_path, sheet_name="rides_trips")
        heatmap_df = pd.read_excel(file_path, sheet_name="heatmap")
        incentives_df = pd.read_excel(file_path, sheet_name="incentives_weekly")
        merchants_df = pd.read_excel(file_path, sheet_name="merchants")
        return {
            "earners": earners_df,
            "rides_trips": rides_trips_df,
            "heatmap": heatmap_df,
            "incentives_weekly": incentives_df,
            "merchants": merchants_df
        }
    except FileNotFoundError:
        print(f"Error: The file was not found at '{file_path}'")
        return None
    except Exception as e:
        print(f"An error occurred while reading the Excel file: {e}")
        return None

def load_hex_mapping(file_path, sheet_name="merchants"):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    mapping = df[["hex_id9", "lat", "lon"]].drop_duplicates()
    mapping = mapping.set_index("hex_id9")
    return mapping
