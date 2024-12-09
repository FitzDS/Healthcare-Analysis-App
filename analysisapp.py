import streamlit as st
import pandas as pd
import requests
from streamlit_folium import st_folium
import folium
import geopandas as gpd
import json

# Load API keys from Streamlit secrets
GEOAPIFY_API_KEY = st.secrets["api_keys"]["geoapify"]
GOOGLE_API_KEY = st.secrets["api_keys"]["google"]

CARE_TYPES = {
    "All Healthcare": "healthcare",
    "Pharmacy": "healthcare.pharmacy",
    "Hospital": "healthcare.hospital",
    "Clinic": "healthcare.clinic",
    "Dentist": "healthcare.dentist",
    "Rehabilitation": "healthcare.rehabilitation",
    "Emergency": "healthcare.emergency",
    "Veterinary": "healthcare.veterinary",
}

# Initialize session state for map and facilities
if "map" not in st.session_state:
    st.session_state["map"] = None
if "facilities" not in st.session_state:
    st.session_state["facilities"] = pd.DataFrame()

def fetch_healthcare_data_within_state_paginated(state_geojson, care_type):
    """Fetch healthcare data within the selected state boundary using pagination."""
    url = "https://api.geoapify.com/v2/places"
    facilities = []
    offset = 0
    limit = 100  # Max results per request

    while True:
        params = {
            "categories": care_type,
            "filter": {"boundary": {"geojson": state_geojson}},
            "limit": limit,
            "offset": offset,
            "apiKey": GEOAPIFY_API_KEY,
        }
        response = requests.post(url, json=params)
        if response.status_code == 200:
            data = response.json()
            features = data.get("features", [])
            if not features:
                break  # Exit loop if no more results
            for feature in features:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                facility = {
                    "name": properties.get("name", "Unknown"),
                    "address": properties.get("formatted", "N/A"),
                    "latitude": geometry.get("coordinates", [])[1],
                    "longitude": geometry.get("coordinates", [])[0],
                }
                facilities.append(facility)
            offset += limit  # Increment offset for next page
        else:
            st.error(f"Error fetching data from Geoapify: {response.status_code}")
            break
    return pd.DataFrame(facilities)

def simplify_geojson(state_geojson, tolerance=0.01):
    """Simplify GeoJSON geometry to reduce complexity."""
    if isinstance(state_geojson, str):
        state_geojson = json.loads(state_geojson)
    gdf = gpd.GeoDataFrame.from_features(state_geojson["features"])
    gdf["geometry"] = gdf["geometry"].simplify(tolerance)
    return json.loads(gdf.to_json())

def load_state_boundaries():
    """Load GeoJSON file with state boundaries."""
    url = "https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_040_00_500k.json"
    gdf = gpd.read_file(url)
    return gdf

def get_lat_lon_from_query(query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": query, "key": GOOGLE_API_KEY}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["results"]:
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]
    st.error("Location not found. Please try again.")
    return None, None

st.title("Healthcare Facility Locator")

# Add legend above the map
st.markdown(f"""### Legend
- **Red Marker**: Current Location
- **Blue Marker**: Healthcare Facility
""")

location_query = st.text_input("Search by Location:")
care_type = st.selectbox("Type of Care:", options=[""] + list(CARE_TYPES.keys()))

# Add state selection for boundary overlay
state_boundaries = load_state_boundaries()
states = state_boundaries["NAME"].tolist()
selected_state = st.selectbox("Select a State for Boundary Analysis:", options=[""] + states)

latitude = st.number_input("Latitude", value=38.5449)
longitude = st.number_input("Longitude", value=-121.7405)

if location_query:
    lat, lon = get_lat_lon_from_query(location_query)
    if lat and lon:
        latitude = lat
        longitude = lon
        st.write(f"Using location: {location_query} (Latitude: {latitude}, Longitude: {longitude})")

if st.button("Search", key="search_button"):
    m = folium.Map(location=[latitude, longitude], zoom_start=6 if selected_state else 12)

    if selected_state and selected_state.strip():
        try:
            state_geojson = state_boundaries[state_boundaries["NAME"] == selected_state].__geo_interface__
            state_geojson = simplify_geojson(state_geojson)  # Simplify the boundary

            # Fetch facilities within the state boundary using pagination
            facilities = fetch_healthcare_data_within_state_paginated(state_geojson, CARE_TYPES.get(care_type, "healthcare"))

            # Add state boundary
            folium.GeoJson(
                data=state_geojson,
                name=f"Boundary: {selected_state}",
                style_function=lambda x: {
                    "fillColor": "#428bca",
                    "color": "#428bca",
                    "weight": 2,
                    "fillOpacity": 0.1,
                },
            ).add_to(m)

            # Add facilities
            if facilities.empty:
                st.error("No facilities found within the state boundary.")
            else:
                st.write(f"Found {len(facilities)} facilities within {selected_state}.")
                for _, row in facilities.iterrows():
                    folium.Marker(
                        location=[row["latitude"], row["longitude"]],
                        popup=f"<b>{row['name']}</b><br>Address: {row['address']}",
                        icon=folium.Icon(color="blue")
                    ).add_to(m)

        except Exception as e:
            st.error(f"Failed to add state boundary or fetch facilities: {e}")

    else:
        st.error("Please select a state for boundary analysis.")

    st.session_state["map"] = m

if "map" in st.session_state and st.session_state["map"] is not None:
    st_folium(st.session_state["map"], width=700, height=500)
else:
    default_map = folium.Map(location=[latitude, longitude], zoom_start=12)
    folium.Marker(
        location=[latitude, longitude],
        popup="Current Location",
        icon=folium.Icon(icon="info-sign", color="red")
    ).add_to(default_map)
    st_folium(default_map, width=700, height=500)
