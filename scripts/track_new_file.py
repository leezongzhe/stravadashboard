import time
from pathlib import Path
import xml.etree.ElementTree as ET
import sqlite3

from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

# 1. Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
WATCH_DIR = BASE_DIR / "incoming"
DB_PATH = BASE_DIR / "strava_dashboard.db"


def init_db():
    """Ensure the database and table exist before processing files."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()


def process_tcx_file(file_path: Path):
    """Parses a TCX file and inserts its trackpoints into SQLite."""
    print(f"\n[+] New TCX detected: {file_path.name}")
    
    # Small pause to prevent race condition (ensures browser finished writing file)
    time.sleep(1)

    activity_id = file_path.stem
    ns = {
        "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
        "ext": "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
    }

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        parsed_data = []
        trackpoints = root.findall(".//tcx:Trackpoint", ns)

        for tp in trackpoints:
            time_elem = tp.find("tcx:Time", ns)
            lat_elem = tp.find("tcx:Position/tcx:LatitudeDegrees", ns)
            lon_elem = tp.find("tcx:Position/tcx:LongitudeDegrees", ns)
            alt_elem = tp.find("tcx:AltitudeMeters", ns)
            dist_elem = tp.find("tcx:DistanceMeters", ns)
            hr_elem = tp.find("tcx:HeartRateBpm/tcx:Value", ns)
            speed_elem = tp.find("tcx:Extensions/ext:TPX/ext:Speed", ns)

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

        if not parsed_data:
            print(f"[!] No trackpoints found in {file_path.name}")
            return

        # Insert to SQLite
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT INTO trackpoints (
                activity_id, time, latitude, longitude, altitude, distance, heart_rate, speed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', parsed_data)
        
        conn.commit()
        conn.close()

        print(f"[✓] Successfully imported {len(parsed_data)} trackpoints from {file_path.name}")

    except Exception as e:
        print(f"[X] Error processing {file_path.name}: {e}")


class TCXHandler(PatternMatchingEventHandler):
    """Event handler that filters specifically for *.tcx files."""
    def __init__(self):
        super().__init__(
            patterns=["*.tcx"],
            ignore_directories=True,
            case_sensitive=False
        )

    def on_created(self, event):
        process_tcx_file(Path(event.src_path))


if __name__ == "__main__":
    init_db()
    WATCH_DIR.mkdir(parents=True, exist_ok=True)

    event_handler = TCXHandler()
    observer = Observer()
    observer.schedule(event_handler, path=str(WATCH_DIR), recursive=False)

    print(f"[*] Watching for incoming TCX files in: {WATCH_DIR}")
    print("[*] Press Ctrl+C to stop.")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[*] Stopping folder watcher...")
    
    observer.join()