import csv
import os

# =============================================================================
# 990 Pipeline Configuration
# =============================================================================
# ORGANIZATIONS:
#   The list of orgs and EINs is stored in user/organizations.csv.
#   You can edit that file in Excel or the web UI — no coding needed.
#   To find an EIN: search the org at https://apps.irs.gov/app/eos/
#   EIN format: 9 digits, no dashes (e.g. 910123456)
# =============================================================================

def load_orgs_from_csv():
    """
    Read the organization list from user/organizations.csv.
    Each row must have a 'name' column and an 'ein' column.
    Returns a list of dicts: [{"name": "...", "ein": "..."}, ...]
    """
    orgs_csv_path = os.path.join(os.path.dirname(__file__), "..", "organizations.csv")

    if not os.path.exists(orgs_csv_path):
        raise FileNotFoundError(
            f"Organization list not found: {orgs_csv_path}\n"
            "Please create organizations.csv with columns: name, ein"
        )

    orgs = []
    with open(orgs_csv_path, newline="", encoding="utf-8-sig") as csv_file:
        for row in csv.DictReader(csv_file):
            name = row.get("name", "").strip()
            ein  = row.get("ein",  "").strip()
            if name and ein:
                orgs.append({"name": name, "ein": ein})

    return orgs


ORGS = load_orgs_from_csv()

# The default IRS index year shown in the web UI.
# Users can change this in the Run Settings dropdown; editing here is optional.
# Valid options: 2021, 2022, 2023, 2024, 2025
YEAR = 2024

# Minimum total compensation to include a row in the output.
# Set to 0 to include everyone; set higher (e.g. 100000) to filter to key staff.
MIN_COMP = 0

# Output file path (relative to project root)
OUTPUT_FILE = "../outputs/compensation_output.csv"
