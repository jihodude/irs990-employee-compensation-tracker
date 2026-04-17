import csv
import datetime
import io
import json
import os
import queue
import socket
import sys
import threading

from flask import Flask, Response, render_template, send_file

# Set working directory to the project folder so relative paths (data/, templates/) always work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Allow imports from the project root (same as main.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MIN_COMP, ORGS, OUTPUT_FILE, YEAR
from modules.filing_fetcher import download_filing_for_org, download_irs_index_for_year
from modules.classifier import assign_standard_position
from modules.output import write_results_to_csv, write_run_report
from modules.parser import extract_compensation_rows


app = Flask(__name__)

# Holds the current pipeline run state so the status page can poll it
pipeline_state = {
    "running": False,
    "log_queue": queue.Queue(),
    "result": None,   # "success" | "error" | None
    "row_count": 0,
    "org_count": 0,
}


class QueueWriter(io.TextIOBase):
    """
    A fake stdout/stderr that puts every line into the log queue
    so we can stream it to the browser via Server-Sent Events.
    """
    def __init__(self, log_queue):
        self.log_queue = log_queue
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.log_queue.put(line)
        return len(text)

    def flush(self):
        if self.buffer:
            self.log_queue.put(self.buffer)
            self.buffer = ""


def fetch_org_data(org, search_year, index_dataframe, min_comp):
    """
    Fetches and parses compensation data for a single org in a given IRS index year.

    Returns a dict with:
      - "rows":          list of compensation row dicts (empty if nothing usable was found)
      - "filing_found":  True if the org's EIN appeared in this year's IRS index
      - "skip_entry":    a dict ready to add to skipped_orgs, or None if rows were found
    """
    org_name = org["name"]
    ein = org["ein"]

    xml_tree, xml_url, pdf_url, tax_period = download_filing_for_org(ein, search_year, index_dataframe)

    if xml_tree is None:
        return {"rows": [], "filing_found": False, "skip_entry": None}

    compensation_rows = extract_compensation_rows(xml_tree, org_name, ein, search_year, xml_url, pdf_url, tax_period)

    if not compensation_rows:
        period_end_year = int(tax_period[:4]) if tax_period and len(tax_period) >= 4 else None
        expected_end_year = search_year - 1

        if period_end_year is not None and period_end_year < expected_end_year:
            reason = (
                f"Stale filing — the 990 found covers the period ending {tax_period}, "
                f"but index year {search_year} should have data ending in {expected_end_year}. "
                f"This org filed late. Check if a newer filing exists in a later index year."
            )
            action = (
                f"Try running the pipeline again with IRS index year {search_year + 1} or {search_year + 2}. "
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

        skip_entry = {
            "org": org_name, "ein": ein,
            "reason": reason, "action": action,
            "pdf_url": pdf_url or "",
        }
        return {"rows": [], "filing_found": True, "skip_entry": skip_entry}

    for row in compensation_rows:
        row["standard_position"] = assign_standard_position(row["irs_title"])

    rows_above_threshold = [row for row in compensation_rows if row["total_comp"] >= min_comp]

    print(f"  People found: {len(compensation_rows)} total | {len(rows_above_threshold)} above ${min_comp:,} threshold")

    if rows_above_threshold:
        return {"rows": rows_above_threshold, "filing_found": True, "skip_entry": None}
    else:
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
        skip_entry = {
            "org": org_name, "ein": ein,
            "reason": reason, "action": action,
            "pdf_url": pdf_url or "",
        }
        return {"rows": [], "filing_found": True, "skip_entry": skip_entry}


def run_pipeline_in_background(year_selection, min_comp, inflation_rate):
    """
    Runs the full 990 pipeline in a background thread.
    year_selection is either "most_recent" or a specific year string like "2024".
    Captures all print() output and routes it into the log queue.
    Updates pipeline_state when done.
    """
    pipeline_state["running"] = True
    pipeline_state["result"] = None
    pipeline_state["row_count"] = 0
    pipeline_state["org_count"] = 0

    # Redirect stdout so all print() calls go into the queue
    original_stdout = sys.stdout
    sys.stdout = QueueWriter(pipeline_state["log_queue"])

    try:
        if year_selection == "most_recent":
            current_year = datetime.datetime.now().year
            years_to_search = [current_year - 1, current_year - 2, current_year - 3]
            mode_label = f"Most Recent (searches {', '.join(str(y) for y in years_to_search)})"
        else:
            years_to_search = [int(year_selection)]
            mode_label = str(year_selection)

        print("=" * 60)
        print(f"  990 Compensation Pipeline")
        print(f"  Year Mode: {mode_label}")
        print(f"  Orgs: {len(ORGS)}  |  Min comp: ${min_comp:,}  |  Inflation: {inflation_rate * 100:.1f}%")
        print("=" * 60)
        print()

        all_compensation_rows = []
        skipped_orgs = []

        if year_selection == "most_recent":
            # Multi-year mode: search newest index first, fall back for orgs not found
            orgs_still_needed = list(ORGS)

            for search_year in years_to_search:
                if not orgs_still_needed:
                    break

                print(f"{'=' * 60}")
                print(f"  Searching IRS index year {search_year}  ({len(orgs_still_needed)} org(s) remaining)")
                print(f"{'=' * 60}")
                print()

                index_dataframe = download_irs_index_for_year(search_year)
                if index_dataframe is None:
                    print(f"[WARNING] Could not download index for {search_year}. Skipping this year.\n")
                    continue

                print()

                orgs_not_found_this_year = []

                for org in orgs_still_needed:
                    org_name = org["name"]
                    ein = org["ein"]
                    print(f"--- {org_name} (EIN: {ein}) ---")

                    result = fetch_org_data(org, search_year, index_dataframe, min_comp)

                    if not result["filing_found"]:
                        # Not in this year's index — will try the next (earlier) year
                        print(f"  Not in {search_year} index — will try earlier year.\n")
                        orgs_not_found_this_year.append(org)
                    elif result["rows"]:
                        all_compensation_rows.extend(result["rows"])
                        print()
                    else:
                        # Found filing but no usable rows — record skip, do not retry
                        if result["skip_entry"]:
                            skipped_orgs.append(result["skip_entry"])
                        print()

                orgs_still_needed = orgs_not_found_this_year

            # Any orgs not found in any of the searched years
            for org in orgs_still_needed:
                reason = (
                    f"No 990 filing found in any of the searched IRS index years "
                    f"({', '.join(str(y) for y in years_to_search)}). "
                    "The org may not have filed electronically yet, or the EIN may be wrong."
                )
                action = (
                    "Verify the EIN is correct at https://apps.irs.gov/app/eos/ or search the org on ProPublica. "
                    "If the EIN is correct and no electronic filing exists, contact the org directly to obtain compensation data."
                )
                skipped_orgs.append({
                    "org": org["name"], "ein": org["ein"],
                    "reason": reason, "action": action, "pdf_url": "",
                })

        else:
            # Single-year mode
            search_year = int(year_selection)

            index_dataframe = download_irs_index_for_year(search_year)
            if index_dataframe is None:
                print("[ERROR] Could not download IRS index. Aborting.")
                pipeline_state["result"] = "error"
                return

            print()

            for org in ORGS:
                org_name = org["name"]
                ein = org["ein"]
                print(f"--- {org_name} (EIN: {ein}) ---")

                result = fetch_org_data(org, search_year, index_dataframe, min_comp)

                if not result["filing_found"]:
                    reason = (
                        f"No 990 filing found in the {search_year} IRS index. "
                        "The org may not have filed yet, or the EIN may be wrong."
                    )
                    action = (
                        "Verify the EIN is correct at https://apps.irs.gov/app/eos/ or search the org on ProPublica. "
                        "If the EIN is correct and no electronic filing exists, contact the org directly to obtain compensation data."
                    )
                    print(f"  Skipping — {reason}\n")
                    skipped_orgs.append({
                        "org": org_name, "ein": ein,
                        "reason": reason, "action": action, "pdf_url": "",
                    })
                elif result["rows"]:
                    all_compensation_rows.extend(result["rows"])
                    print()
                else:
                    if result["skip_entry"]:
                        skipped_orgs.append(result["skip_entry"])
                    print()

        # Determine label for run report (most_recent uses "most_recent" string; single year uses int)
        report_year_label = year_selection if year_selection == "most_recent" else int(year_selection)

        print("=" * 60)
        write_results_to_csv(all_compensation_rows, OUTPUT_FILE, inflation_rate)
        write_run_report(all_compensation_rows, skipped_orgs, report_year_label, min_comp, OUTPUT_FILE, inflation_rate)
        print("=" * 60)

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

        pipeline_state["row_count"] = len(all_compensation_rows)
        pipeline_state["org_count"] = len(set(r["org_name"] for r in all_compensation_rows))
        pipeline_state["result"] = "success"

        print()
        print("  Done.")

    except Exception as error:
        print(f"\n[ERROR] Pipeline crashed: {error}")
        pipeline_state["result"] = "error"

    finally:
        sys.stdout.flush()
        sys.stdout = original_stdout
        pipeline_state["running"] = False
        # Sentinel tells the SSE stream to close
        pipeline_state["log_queue"].put(None)


# =============================================================================
# Routes
# =============================================================================

@app.route("/")
def index():
    """Render the main page."""
    return render_template(
        "index.html",
        orgs=ORGS,
        default_year=YEAR,
        default_min_comp=MIN_COMP,
        output_file=OUTPUT_FILE,
    )


@app.route("/run", methods=["POST"])
def run():
    """
    Start the pipeline in a background thread.
    Returns immediately — the browser streams progress via /stream.
    """
    from flask import request

    if pipeline_state["running"]:
        return {"error": "Pipeline is already running."}, 409

    # year can be "most_recent" or a numeric string like "2024"
    year_selection = request.form.get("year", str(YEAR))
    min_comp = int(request.form.get("min_comp", MIN_COMP))
    inflation_rate = float(request.form.get("inflation_rate", 3)) / 100

    # Clear old log queue
    while not pipeline_state["log_queue"].empty():
        pipeline_state["log_queue"].get_nowait()

    thread = threading.Thread(
        target=run_pipeline_in_background,
        args=(year_selection, min_comp, inflation_rate),
        daemon=True,
    )
    thread.start()

    return {"status": "started"}, 200


@app.route("/stream")
def stream():
    """
    Server-Sent Events endpoint.
    Streams log lines to the browser as they are produced by the pipeline.
    """
    def generate():
        while True:
            line = pipeline_state["log_queue"].get()
            if line is None:
                # Pipeline finished — send final status event and close stream
                result = pipeline_state.get("result", "error")
                payload = json.dumps({
                    "result": result,
                    "row_count": pipeline_state["row_count"],
                    "org_count": pipeline_state["org_count"],
                })
                yield f"event: done\ndata: {payload}\n\n"
                return
            yield f"data: {json.dumps(line)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/download")
def download():
    """Serve the output CSV as a file download."""
    output_path = os.path.join(os.path.dirname(__file__), OUTPUT_FILE)
    if not os.path.exists(output_path):
        return "No output file found. Run the pipeline first.", 404
    return send_file(
        output_path,
        as_attachment=True,
        download_name="compensation_output.csv",
        mimetype="text/csv",
    )


@app.route("/status")
def status():
    """Return current pipeline state as JSON (used by the UI to poll)."""
    return {
        "running": pipeline_state["running"],
        "result": pipeline_state["result"],
    }


@app.route("/orgs", methods=["GET"])
def get_orgs():
    """Return the current org list as JSON."""
    from config import load_orgs_from_csv
    try:
        orgs = load_orgs_from_csv()
        return {"orgs": orgs}
    except Exception as error:
        return {"error": str(error)}, 500


@app.route("/save_orgs", methods=["POST"])
def save_orgs():
    """
    Save an updated org list to user/organizations.csv.
    Expects JSON body: {"orgs": [{"name": "...", "ein": "..."}, ...]}
    """
    from flask import request as flask_request
    import importlib
    import config as config_module

    data = flask_request.get_json()
    if not data or "orgs" not in data:
        return {"error": "Invalid request — expected JSON with 'orgs' list."}, 400

    orgs = data["orgs"]

    # Basic validation
    for org in orgs:
        ein = str(org.get("ein", "")).strip()
        if not ein.isdigit() or len(ein) != 9:
            return {"error": f"Invalid EIN '{ein}' — must be exactly 9 digits, no dashes."}, 400

    orgs_csv_path = os.path.join(os.path.dirname(__file__), "..", "organizations.csv")

    with open(orgs_csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["name", "ein"])
        writer.writeheader()
        for org in orgs:
            writer.writerow({"name": org["name"].strip(), "ein": str(org["ein"]).strip()})

    # Reload config so the in-memory ORGS list reflects the change immediately
    importlib.reload(config_module)

    return {"status": "saved", "count": len(orgs)}


def find_open_port(start_port=5000, max_attempts=20):
    """
    Try ports starting at start_port and return the first one that is not in use.
    Returns None if no open port is found within max_attempts tries.
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
            try:
                test_socket.bind(("", port))
                return port  # Port is free — use it
            except OSError:
                continue  # Port is in use — try the next one
    return None


if __name__ == "__main__":
    import webbrowser

    port = find_open_port(start_port=5000)

    if port is None:
        print("")
        print("  ERROR: Could not find an open port between 5000 and 5019.")
        print("  Please close other applications and try again.")
        sys.exit(1)

    if port != 5000:
        print(f"  Port 5000 was in use. Using port {port} instead.")

    print("")
    print("  ============================================")
    print(f"   Open your browser and go to:")
    print(f"   http://localhost:{port}")
    print("  ============================================")
    print("")

    # Open the browser after a short delay — Python knows the exact port,
    # so this is always correct regardless of which port was available.
    url = f"http://localhost:{port}"
    threading.Timer(2.0, lambda: webbrowser.open(url)).start()

    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(debug=False, port=port, use_reloader=False)
