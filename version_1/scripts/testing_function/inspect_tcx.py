from pathlib import Path
import xml.etree.ElementTree as ET


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
TCX_DIR = BASE_DIR / "incoming"

tcx_files = list(TCX_DIR.glob("*.tcx"))

if not tcx_files:
    raise FileNotFoundError(
        "No TCX files found in incoming/"
    )

tcx_file = tcx_files[0]

print(f"Reading: {tcx_file}")


# --------------------------------------------------
# Parse XML
# --------------------------------------------------

tree = ET.parse(tcx_file)
root = tree.getroot()


# --------------------------------------------------
# Basic information
# --------------------------------------------------

print("\nRoot element:")
print(root.tag)

print("\nRoot attributes:")
print(root.attrib)


# --------------------------------------------------
# Display XML structure
# --------------------------------------------------

def print_tree(element, level=0, max_depth=9):

    indent = "    " * level

    # Remove XML namespace for easier reading
    tag = element.tag.split("}")[-1]

    print(f"{indent}{tag}")

    # Stop at maximum depth
    if level >= max_depth:
        return

    # --------------------------------------------------
    # If this is Track, inspect only the first Trackpoint
    # --------------------------------------------------

    if tag == "Track":

        trackpoints = []

        for child in element:
            child_tag = child.tag.split("}")[-1]

            if child_tag == "Trackpoint":
                trackpoints.append(child)

            else:
                print_tree(child, level + 1, max_depth)

        if trackpoints:

            print(
                f"{indent}    Trackpoint "
                f"(showing first of {len(trackpoints)})"
            )

            print_tree(
                trackpoints[0],
                level + 2,
                max_depth
            )

        return

    # --------------------------------------------------
    # Normal XML traversal
    # --------------------------------------------------

    for child in element:
        print_tree(child, level + 1, max_depth)

print("\nXML structure:")
print_tree(root)