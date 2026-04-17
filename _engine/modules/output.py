import os
import datetime
import pandas as pd

# Internal column names used throughout the pipeline (do not rename these)
CSV_COLUMNS = [
    "org_name",
    "ein",
    "year",
    "person_name",
    "irs_title",
    "standard_position",
    "base_comp",
    "related_org_comp",
    "other_comp",
    "total_comp",
    "xml_url",
    "pdf_url",
]

# Maps internal names → human-readable column headers in the output CSV
COLUMN_RENAME_MAP = {
    "org_name":           "Organization",
    "ein":                "EIN",
    "year":               "Year",
    "person_name":        "Name",
    "irs_title":          "Title",
    "standard_position":  "Association Comparable Position",
    "base_comp":          "Base",
    "related_org_comp":   "Bonus",
    "other_comp":         "Other",
    "total_comp":         "Total Comp",
    "xml_url":            "XML Source URL",
    "pdf_url":            "ProPublica URL",
}

# Final column order in the output CSV (matches human-pulled file format)
OUTPUT_COLUMNS = [
    "Organization",
    "EIN",
    "Year",
    "Name",
    "Title",
    "Association Comparable Position",
    "Base",
    "Bonus",
    "Other",
    "Total Comp",
    "Base (Inflation Adjusted)",
    "Bonus (Inflation Adjusted)",
    "Other (Inflation Adjusted)",
    "Total Comp (Inflation Adjusted)",
    "XML Source URL",
    "ProPublica URL",
]


def compute_inflation_factor(irs_index_year, annual_rate):
    """
    Returns the inflation factor to bring compensation from the filing's
    fiscal year up to the current calendar year.

    The IRS index year (e.g. 2025) typically contains filings covering
    fiscal year ending one year prior (e.g. 2024). So we adjust from
    (index_year - 1) to the current year.

    annual_rate: decimal rate, e.g. 0.03 for 3%
    """
    current_year = datetime.datetime.now().year
    fiscal_year = int(irs_index_year) - 1
    years_of_inflation = max(0, current_year - fiscal_year)
    return (1 + annual_rate) ** years_of_inflation


def write_results_to_csv(all_rows, output_filepath, inflation_rate=0.03):
    """
    Write all compensation rows to a CSV file with human-readable column names
    and inflation-adjusted compensation columns.

    - all_rows: list of dicts, one per person per org per year
    - output_filepath: path to write the CSV
    - inflation_rate: annual inflation rate as a decimal (e.g. 0.03 for 3%)

    Creates the output directory if it doesn't exist.
    Overwrites the file if it already exists.
    """
    if not all_rows:
        print("[WARNING] No rows to write — output file was not created.")
        return

    output_directory = os.path.dirname(output_filepath)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    df = pd.DataFrame(all_rows, columns=CSV_COLUMNS)

    # Compute inflation-adjusted columns
    df["inflation_factor"] = df["year"].apply(lambda y: compute_inflation_factor(y, inflation_rate))
    df["Base (Inflation Adjusted)"]       = (df["base_comp"]         * df["inflation_factor"]).round(2)
    df["Bonus (Inflation Adjusted)"]      = (df["related_org_comp"]  * df["inflation_factor"]).round(2)
    df["Other (Inflation Adjusted)"]      = (df["other_comp"]        * df["inflation_factor"]).round(2)
    df["Total Comp (Inflation Adjusted)"] = (df["total_comp"]        * df["inflation_factor"]).round(2)
    df = df.drop(columns=["inflation_factor"])

    # Rename internal columns to human-readable headers
    df = df.rename(columns=COLUMN_RENAME_MAP)

    # Write in the final column order
    df[OUTPUT_COLUMNS].to_csv(output_filepath, index=False, encoding="utf-8-sig")
    # utf-8-sig adds a BOM so Excel opens it correctly without garbled characters

    print(f"\n  Output written to: {output_filepath}")
    print(f"  Total rows: {len(df):,}")
    print(f"  Total orgs: {df['Organization'].nunique()}")


def write_run_report(all_rows, skipped_orgs, year, min_comp, output_filepath, inflation_rate=0.03):
    """
    Write a plain-text run report alongside the CSV.

    The report explains:
      - What the pipeline successfully extracted
      - Every org that was skipped and exactly why
      - Specific guidance on what a human needs to do for each skipped org

    The report file is saved next to the CSV with a _run_report.txt suffix.
    Example: user/outputs/compensation_output.csv
          → user/outputs/compensation_output_run_report.txt
    """
    # Build the report file path (same folder, same base name, different extension)
    base_path = output_filepath.replace(".csv", "")
    report_filepath = f"{base_path}_run_report.txt"

    output_directory = os.path.dirname(report_filepath)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    successful_org_count = len(set(row["org_name"] for row in all_rows)) if all_rows else 0
    total_row_count = len(all_rows)

    lines = []
    lines.append("=" * 70)
    lines.append("  990 COMPENSATION PIPELINE — RUN REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Run date:        {run_timestamp}")
    year_display = "Most Recent (auto)" if year == "most_recent" else str(year)
    lines.append(f"  IRS index year:  {year_display}")
    lines.append(f"  Min compensation filter: ${min_comp:,}")
    lines.append(f"  Inflation rate:          {inflation_rate * 100:.1f}% per year")
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"  RESULTS SUMMARY")
    lines.append("-" * 70)
    lines.append(f"  Orgs with data extracted:  {successful_org_count}")
    lines.append(f"  Orgs skipped / incomplete: {len(skipped_orgs)}")
    lines.append(f"  Total rows in output CSV:  {total_row_count:,}")
    lines.append("")

    if not skipped_orgs:
        lines.append("  All orgs processed successfully. No issues to report.")
    else:
        lines.append("-" * 70)
        lines.append(f"  SKIPPED ORGS — ACTION NEEDED ({len(skipped_orgs)} total)")
        lines.append("-" * 70)
        lines.append("")

        for entry in skipped_orgs:
            org_name = entry["org"]
            ein      = entry["ein"]
            reason   = entry["reason"]
            action   = entry.get("action", "")

            lines.append(f"  ORG:    {org_name}")
            lines.append(f"  EIN:    {ein}")
            lines.append(f"  REASON: {reason}")
            if action:
                lines.append(f"  ACTION: {action}")
            lines.append(f"  PDF:    https://projects.propublica.org/nonprofits/organizations/{ein}")
            lines.append("")

    lines.append("-" * 70)
    lines.append("  COLUMN REFERENCE")
    lines.append("-" * 70)
    lines.append("")
    lines.append("  Base             IRS Part VII Col D — wages paid directly by this org")
    lines.append("  Bonus            IRS Part VII Col E — wages paid by a related organization")
    lines.append("                   (labeled Bonus to match prior format — this is NOT a")
    lines.append("                   performance bonus; it is pay from a sister/affiliate entity)")
    lines.append("  Other            IRS Part VII Col F — benefits, deferred comp, other")
    lines.append("  Total Comp       Base + Bonus + Other  (Col D + E + F)")
    lines.append("                   Matches IRS Part VII Column G total.")
    lines.append("")
    lines.append("  *Inflation Adjusted columns use 3% annual inflation from the filing's")
    lines.append("  fiscal year (IRS index year minus 1) to the current calendar year.")
    lines.append("")
    lines.append("-" * 70)
    lines.append("  KNOWN PERMANENT LIMITATIONS")
    lines.append("-" * 70)
    lines.append("")
    lines.append("  1. Orgs with all-volunteer leadership report $0 for all Part VII entries.")
    lines.append("     If any paid staff exist, they may earn below the IRS reporting threshold")
    lines.append("     ($100K for key employees) and will not appear in this output.")
    lines.append("")
    lines.append("  2. Orgs that have never filed an electronic 990 (e.g. paper filers or")
    lines.append("     orgs with revoked tax-exempt status) will never appear in the IRS")
    lines.append("     e-file index. Their data must be obtained directly from the org.")
    lines.append("     (Affects: North Dakota Hospitality Association)")
    lines.append("")
    lines.append("  3. Orgs that report Part VII compensation in Schedule O (free-form text)")
    lines.append("     instead of structured XML fields cannot be parsed automatically.")
    lines.append("     Their data must be entered manually from the PDF.")
    lines.append("")
    lines.append("=" * 70)
    lines.append("")

    report_text = "\n".join(lines)

    with open(report_filepath, "w", encoding="utf-8") as report_file:
        report_file.write(report_text)

    print(f"  Run report written to: {report_filepath}")
