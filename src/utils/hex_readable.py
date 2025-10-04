# Location conversion utilities
import pandas as pd
from geopy.geocoders import Nominatim

def latlon_to_location(lat, lon):
    geolocator = Nominatim(user_agent="uber_advisor")
    location = geolocator.reverse((lat, lon), language="en", zoom=14)
    return location.address if location else "Unknown location"

def get_location_from_hex(hex_id, mapping):
    norm_hex_id = str(hex_id).strip().lower()
    if not all(isinstance(idx, str) and idx == idx.strip().lower() for idx in mapping.index):
        mapping.index = mapping.index.map(lambda x: str(x).strip().lower())
    try:
        lat, lon = mapping.loc[norm_hex_id, ["lat", "lon"]]
        location = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        return lat, lon, location
    except KeyError:
        return None, None, "Unknown location"
