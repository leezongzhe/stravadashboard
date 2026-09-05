from pathlib import Path
import xml.etree.ElementTree as ET

# 1. Setup file paths
BASE_DIR = Path(__file__).resolve().parent.parent
TCX_DIR = BASE_DIR / "incoming"

tcx_files = list(TCX_DIR.glob("*.tcx"))
if not tcx_files:
    raise FileNotFoundError("No TCX files found.")

tcx_file = tcx_files[1]
print(f"Parsing TCX file: {tcx_file.name}...\n")

# 2. Parse XML and define explicit namespaces
tree = ET.parse(tcx_file)
root = tree.getroot()

NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ext": "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
}

# 3. Extract the data safely
parsed_data = []

# Find all trackpoints in the file
trackpoints = root.findall(".//tcx:Trackpoint", NS)

for tp in trackpoints:
    # --- Safe Extraction Helpers ---
    # Time
    time_elem = tp.find("tcx:Time", NS)
    time_val = time_elem.text if time_elem is not None else None
    
    # Position
    lat_elem = tp.find("tcx:Position/tcx:LatitudeDegrees", NS)
    lon_elem = tp.find("tcx:Position/tcx:LongitudeDegrees", NS)
    lat_val = float(lat_elem.text) if lat_elem is not None else None
    lon_val = float(lon_elem.text) if lon_elem is not None else None
    
    # Altitude & Distance
    alt_elem = tp.find("tcx:AltitudeMeters", NS)
    dist_elem = tp.find("tcx:DistanceMeters", NS)
    alt_val = float(alt_elem.text) if alt_elem is not None else None
    dist_val = float(dist_elem.text) if dist_elem is not None else None
    
    # Heart Rate (Nested)
    hr_elem = tp.find("tcx:HeartRateBpm/tcx:Value", NS)
    hr_val = int(hr_elem.text) if hr_elem is not None else None
    
    # Speed (Extension)
    speed_elem = tp.find("tcx:Extensions/ext:TPX/ext:Speed", NS)
    speed_val = float(speed_elem.text) if speed_elem is not None else None

    # Append to our Python list
    parsed_data.append({
        "time": time_val,
        "latitude": lat_val,
        "longitude": lon_val,
        "altitude": alt_val,
        "distance": dist_val,
        "heart_rate": hr_val,
        "speed": speed_val
    })

# 4. Verify the output
print(f"Successfully parsed {len(parsed_data)} trackpoints!")
print("-" * 40)
print("Preview of the first and last 3 rows:")
print("-" * 40)
for row in parsed_data[:3]:
    print(row)
print("...\n...\n...")
for row in parsed_data[-3:]:
    print(row)

# 5. Check actual sampling interval
print("\n" + "=" * 50)
print("SAMPLING INTERVAL ANALYSIS")
print("=" * 50)

# Convert timestamps to datetime
import pandas as pd

time_series = pd.to_datetime(
    [row["time"] for row in parsed_data],
    errors="coerce"
)

# Calculate interval between consecutive trackpoints
time_diff = time_series.to_series().diff().dt.total_seconds()

# Remove first NaN
time_diff = time_diff.dropna()

print(f"Number of intervals: {len(time_diff)}")
print(f"Mean interval:       {time_diff.mean():.4f} seconds")
print(f"Median interval:     {time_diff.median():.4f} seconds")
print(f"Minimum interval:    {time_diff.min():.4f} seconds")
print(f"Maximum interval:    {time_diff.max():.4f} seconds")
print(f"Std deviation:       {time_diff.std():.4f} seconds")

print("\nFirst 20 sampling intervals:")
print(time_diff.head(20).to_string(index=False))

print("\nInterval distribution:")
print(
    time_diff
    .round(3)
    .value_counts()
    .sort_index()
    .head(30)
)