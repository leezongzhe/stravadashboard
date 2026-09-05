from pathlib import Path
import xml.etree.ElementTree as ET


BASE_DIR = Path(__file__).resolve().parent.parent
TCX_DIR = BASE_DIR / "incoming"

tcx_files = list(TCX_DIR.glob("*.tcx"))

if not tcx_files:
    raise FileNotFoundError("No TCX files found.")

tcx_file = tcx_files[0]

print(f"Reading: {tcx_file}")

tree = ET.parse(tcx_file)
root = tree.getroot()


# Find first Trackpoint regardless of namespace
trackpoint = root.find(".//{*}Trackpoint")

if trackpoint is None:
    raise ValueError("No Trackpoint found.")


print("\n" + "=" * 60)
print("FIRST TRACKPOINT - RAW XML")
print("=" * 60)

print(
    ET.tostring(
        trackpoint,
        encoding="unicode"
    )
)

print("=" * 60)