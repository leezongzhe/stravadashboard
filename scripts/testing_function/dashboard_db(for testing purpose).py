from pathlib import Path
import xml.etree.ElementTree as ET
import sqlite3

# 1. Setup file paths
BASE_DIR = Path(__file__).resolve().parent.parent
TCX_DIR = BASE_DIR / "incoming"
DB_PATH = BASE_DIR / "strava_dashboard.db"

# Find TCX file
tcx_files = list(TCX_DIR.glob("*.tcx"))
if not tcx_files:
    raise FileNotFoundError("No TCX files found.")

tcx_file = tcx_files[0]
activity_id = tcx_file.stem  # Extracts '19751444438' from '19751444438.tcx'

print(f"Parsing TCX file: {tcx_file.name}...")

# 2. Parse XML
tree = ET.parse(tcx_file)
root = tree.getroot()

NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ext": "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
}

parsed_data = []
trackpoints = root.findall(".//tcx:Trackpoint", NS)

for tp in trackpoints:
    time_elem = tp.find("tcx:Time", NS)
    lat_elem = tp.find("tcx:Position/tcx:LatitudeDegrees", NS)
    lon_elem = tp.find("tcx:Position/tcx:LongitudeDegrees", NS)
    alt_elem = tp.find("tcx:AltitudeMeters", NS)
    dist_elem = tp.find("tcx:DistanceMeters", NS)
    hr_elem = tp.find("tcx:HeartRateBpm/tcx:Value", NS)
    speed_elem = tp.find("tcx:Extensions/ext:TPX/ext:Speed", NS)

    parsed_data.append((
        activity_id,
        time_elem.text if time_elem is not None else None,
        float(lat_elem.text) if lat_elem is not None else None,
        float(lon_elem.text) if lon_elem is not None else None,
        float(alt_elem.text) if alt_elem is not None else None,
        float(dist_elem.text) if dist_elem is not None else None,
        int(hr_elem.text) if hr_elem is not None else None,
        float(speed_elem.text) if speed_elem is not None else None
    ))

print(f"Extracted {len(parsed_data)} trackpoints. Connecting to database...")

# 3. Database Operations
# Connect to SQLite (creates the file if it doesn't exist)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create the schema
cursor.execute('''
    CREATE TABLE IF NOT EXISTS trackpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id TEXT,
        time TEXT,
        latitude REAL,
        longitude REAL,
        altitude REAL,
        distance REAL,
        heart_rate INTEGER,
        speed REAL
    )
''')

# 4. Insert Data
# We use REPLACE or INSERT to avoid duplicates if you run the script twice, 
# though right now we are just appending. Let's do a standard INSERT.
insert_query = '''
    INSERT INTO trackpoints (
        activity_id, time, latitude, longitude, altitude, distance, heart_rate, speed
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
'''

# executemany is highly optimized for bulk inserts in SQLite
cursor.executemany(insert_query, parsed_data)

# Commit changes and close connection
conn.commit()
conn.close()

print(f"Successfully saved trackpoints to {DB_PATH.name}!")