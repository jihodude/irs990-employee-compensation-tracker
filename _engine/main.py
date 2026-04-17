import sys
import os

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(__file__))

from config import ORGS, YEAR, MIN_COMP, OUTPUT_FILE
from modules.filing_fetcher import download_irs_index_for_year, download_filing_for_org
from modules.parser import extract_compensation_rows
from modules.classifier import assign_standard_position
from modules.output import write_results_to_csv, write_run_report


def run_pipeline():
    print("=" * 60)
    print(f"  990 Compensation Pipeline")
    print(f"  Year: {YEAR}  |  Orgs: {len(ORGS)}  |  Min comp: ${MIN_COMP:,}")
    print("=" * 60)
    print()

    # Step 1: Download the IRS index once — reused for all orgs
    index_dataframe = download_irs_index_for_year(YEAR)
    if index_dataframe is None:
        print("[ERROR] Could not download IRS index. Exiting.")
        return

    print()

    # Step 2: Loop through every org, fetch and parse its 990
    all_compensation_rows = []
    skipped_orgs = []  # Track every org that couldn't be processed, with a reason

    for org in ORGS:
        org_name = org["name"]
        ein      = org["ein"]

        print(f"--- {org_name} (EIN: {ein}) ---")

        # Fetch the XML filing
        xml_tree, xml_url, pdf_url, tax_period = download_filing_for_org(ein, YEAR, index_dataframe)

        if xml_tree is None:
            reason = f"No 990 filing found in the {YEAR} IRS index. The org may not have filed yet, or the EIN may be wrong."
            action = (
                "Verify the EIN is correct at https://apps.irs.gov/app/eos/ or search the org on ProPublica. "
                "If the EIN is correct and no electronic filing exists, contact the org directly to obtain compensation data."
            )
            print(f"  Skipping — {reason}\n")
            skipped_orgs.append({"org": org_name, "ein": ein, "reason": reason, "action": action})
            continue

        # Extract compensation rows from Part VII
        compensation_rows = extract_compensation_rows(xml_tree, org_name, ein, YEAR, xml_url, pdf_url, tax_period)

        if not compensation_rows:
            # Determine why — stale and Schedule O messages are printed inside the parser.
            # Here we record the right reason for the ACTION NEEDED summary.
            period_end_year = int(tax_period[:4]) if tax_period and len(tax_period) >= 4 else None
            expected_end_year = YEAR - 1

            if period_end_year is not None and period_end_year < expected_end_year:
                reason = (
                    f"Stale filing — the 990 found covers the period ending {tax_period}, "
                    f"but index year {YEAR} should have data ending in {expected_end_year}. "
                    f"This org filed late. Check if a newer filing exists in a later index year."
                )
                action = (
                    f"Try running the pipeline again with IRS index year {YEAR + 1} or {YEAR + 2}. "
                    "Alternatively, open the PDF link below to manually review the filing."
                )
            else:
                reason = (
                    "Filing was found but contained no extractable Part VII compensation data. "
                    "The org may report compensation in Schedule O (see PDF link) or may have no paid staff."
                )
                action = (
                    "Open the PDF link below and review Part VII and Schedule O for compensation data. "
                    "If the org employs all staff through a management affiliate, their compensation "
                    "will be in the affiliate's separate 990 under a different EIN."
                )

            print(f"  Skipping — see reason above.\n")
            skipped_orgs.append({"org": org_name, "ein": ein, "reason": reason, "action": action})
            continue

        # Apply the standard_position column (currently mirrors irs_title for manual review)
        for row in compensation_rows:
            row["standard_position"] = assign_standard_position(row["irs_title"])

        # Apply minimum compensation filter
        rows_above_threshold = [
            row for row in compensation_rows
            if row["total_comp"] >= MIN_COMP
        ]

        print(f"  People found: {len(compensation_rows)} total | {len(rows_above_threshold)} above ${MIN_COMP:,} threshold")

        if rows_above_threshold:
            all_compensation_rows.extend(rows_above_threshold)
        else:
            # All extracted rows were filtered out by the min_comp threshold.
            # This usually means the org has all-volunteer leadership with $0 comp,
            # or all staff fall below the IRS Part VII reporting threshold.
            reason = (
                f"Filing found and parsed, but all {len(compensation_rows)} Part VII "
                f"entries had $0 or below-threshold compensation. This org likely has "
                f"all-volunteer leadership; paid staff (if any) may earn below the IRS "
                f"reporting threshold or be reported as independent contractors."
            )
            action = (
                "Open the PDF link below. If the org has paid executives, "
                "their compensation may appear on Schedule O or as independent contractor fees."
            )
            skipped_orgs.append({
                "org": org_name, "ein": ein,
                "reason": reason, "action": action,
                "pdf_url": pdf_url if pdf_url else "",
            })
        print()

    # Step 3: Write everything to CSV and a run report alongside it
    print("=" * 60)
    write_results_to_csv(all_compensation_rows, OUTPUT_FILE)
    write_run_report(all_compensation_rows, skipped_orgs, YEAR, MIN_COMP, OUTPUT_FILE)
    print("=" * 60)

    # Step 4: Print a clear summary of everything that was skipped and why
    if skipped_orgs:
        print()
        print(f"  ACTION NEEDED — {len(skipped_orgs)} org(s) could not be included:")
        print()
        for entry in skipped_orgs:
            print(f"  • {entry['org']} (EIN: {entry['ein']})")
            print(f"    Reason: {entry['reason']}")
            print()
    else:
        print()
        print("  All orgs processed successfully — no skips.")

    print()
    print("  Done.")


if __name__ == "__main__":
    run_pipeline()
