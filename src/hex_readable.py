import pandas as pd
from geopy.geocoders import Nominatim

# Load mapping of hex_id9 → lat/lon
def load_hex_mapping(file_path, sheet_name="merchants"):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    mapping = df[["hex_id9", "lat", "lon"]].drop_duplicates()
    mapping = mapping.set_index("hex_id9")
    return mapping

# Reverse geocode lat/lon → readable location
def latlon_to_location(lat, lon):
    geolocator = Nominatim(user_agent="uber_advisor")
    location = geolocator.reverse((lat, lon), language="en", zoom=14)
    return location.address if location else "Unknown location"

# Get location from hex_id9
def get_location_from_hex(hex_id, mapping):
    if hex_id not in mapping.index:
        return None, None, "Hex not found in mapping"
    
    lat, lon = mapping.loc[hex_id, ["lat", "lon"]]
    location = latlon_to_location(lat, lon)
    return lat, lon, location


# if _name_ == "_main_":
#     excel_file = "data/data_sets.xlsx"   # adjust if different
#     mapping = load_hex_mapping(excel_file, sheet_name="merchants")

#     example_hex = "89fb0333e75a7e5"  # from your advisor output
#     lat, lon, location = get_location_from_hex(example_hex, mapping)

#     print(f"Hex: {example_hex}")
#     print(f"Lat/Lon: {lat}, {lon}")
#     print(f"Location: {location}")