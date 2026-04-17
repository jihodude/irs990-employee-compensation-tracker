import inflate64
import io
import os
import struct
import subprocess
import tempfile
import time
import zlib

import pandas as pd
import requests
from lxml import etree

# IRS TEOS URLs (replaced the old S3 bucket which was shut down in 2021)
IRS_INDEX_CSV_URL = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/index_{year}.csv"
IRS_BATCH_ZIP_URL = "https://apps.irs.gov/pub/epostcard/990/xml/{year}/{batch_name}.zip"

MAX_DOWNLOAD_ATTEMPTS = 3
SECONDS_BETWEEN_RETRIES = 2
CACHE_TTL_SECONDS = 86400  # 24 hours

# ZIP file format binary signatures (used to navigate ZIP structure)
ZIP_LOCAL_FILE_HEADER_SIGNATURE   = b'PK\x03\x04'
ZIP_CENTRAL_DIR_ENTRY_SIGNATURE   = b'PK\x01\x02'
ZIP_END_OF_CENTRAL_DIR_SIGNATURE  = b'PK\x05\x06'
ZIP64_END_OF_CENTRAL_DIR_SIGNATURE = b'PK\x06\x06'


# =============================================================================
# SECTION 1: Basic HTTP helpers
# =============================================================================

DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; 990-pipeline/1.0)"
}

def download_url_with_retries(url, range_header=None):
    """
    Download a URL and return the response.
    If range_header is provided (e.g. 'bytes=0-1023'), only that byte range is downloaded.
    Tries up to MAX_DOWNLOAD_ATTEMPTS times on failure.
    """
    headers = dict(DOWNLOAD_HEADERS)
    if range_header:
        headers["Range"] = range_header

    for attempt_number in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=headers, timeout=(10, 60))
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            print(f"    [WARNING] Attempt {attempt_number}/{MAX_DOWNLOAD_ATTEMPTS} failed for {url}: {error}")
            if attempt_number < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(SECONDS_BETWEEN_RETRIES)
    return None


def get_file_size_from_url(url):
    """Return the total byte size of a remote file using a HEAD request."""
    try:
        response = requests.head(url, timeout=10)
        if response.status_code == 200:
            return int(response.headers.get("Content-Length", 0))
    except requests.RequestException:
        pass
    return None


def download_byte_range_from_url(url, start_byte, end_byte):
    """Download only the bytes between start_byte and end_byte (inclusive) from a URL."""
    for attempt_number in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                ["curl", "-L", "--http1.1", "--max-time", "60",
                 "--silent", "--show-error",
                 "-A", DOWNLOAD_HEADERS["User-Agent"],
                 "-r", f"{start_byte}-{end_byte}",
                 "-o", tmp_path, url],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            with open(tmp_path, "rb") as f:
                return f.read()
        except Exception as error:
            print(f"    [WARNING] Attempt {attempt_number}/{MAX_DOWNLOAD_ATTEMPTS} failed for {url}: {error}")
            if attempt_number < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(SECONDS_BETWEEN_RETRIES)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    return None


# =============================================================================
# SECTION 2: IRS index CSV
# =============================================================================

def download_irs_index_for_year(year):
    """
    Download the IRS filing index CSV for the given year.
    This is one large file (~80-90MB) listing every 990 filed that year.
    Returns a pandas DataFrame, or None if the download fails.

    This should be called ONCE per run and reused for all orgs.
    A cached copy is used if one exists and is less than 24 hours old.
    """
    cache_dir  = os.path.join(os.path.dirname(__file__), "..", "cache")
    cache_path = os.path.join(cache_dir, f"index_{year}.csv")

    # Use cached copy if it exists and is less than 24 hours old
    if os.path.exists(cache_path):
        age_seconds = time.time() - os.path.getmtime(cache_path)
        if age_seconds < CACHE_TTL_SECONDS:
            age_str = f"{int(age_seconds // 3600)}h {int((age_seconds % 3600) // 60)}m"
            print(f"  Loading IRS index for {year} from cache ({age_str} old)...")
            try:
                index_dataframe = pd.read_csv(cache_path, dtype=str)
                print(f"  Index loaded: {len(index_dataframe):,} total filings found for {year}.")
                return index_dataframe
            except Exception as error:
                print(f"  [WARNING] Cache file unreadable ({error}), re-downloading...")

    os.makedirs(cache_dir, exist_ok=True)

    index_url = IRS_INDEX_CSV_URL.format(year=year)
    print(f"  Downloading IRS filing index for {year} (~80-90 MB, may take 30-60 seconds)...")

    for attempt_number in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                ["curl", "-L", "--http1.1", "--max-time", "180",
                 "--silent", "--show-error",
                 "-A", DOWNLOAD_HEADERS["User-Agent"],
                 "-o", tmp_path, index_url],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            os.rename(tmp_path, cache_path)
            tmp_path = None  # already moved, skip finally cleanup
            index_dataframe = pd.read_csv(cache_path, dtype=str)
            print(f"  Index loaded: {len(index_dataframe):,} total filings found for {year}.")
            return index_dataframe
        except Exception as error:
            print(f"    [WARNING] Attempt {attempt_number}/{MAX_DOWNLOAD_ATTEMPTS} failed for {index_url}: {error}")
            if attempt_number < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(SECONDS_BETWEEN_RETRIES)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    print(f"  [WARNING] Could not download IRS index for {year}.")
    return None


def find_filing_in_index(index_dataframe, ein):
    """
    Search the index DataFrame for a given EIN.
    Returns (object_id, batch_name, tax_period) where:
      - batch_name may be empty for pre-2024 years
      - tax_period is a string like "202309" (period END year+month, from IRS index)
    Returns (None, None, None) if no matching filing is found.

    Only full 990 returns are considered — 990EZ has no Part VII compensation data,
    and 990PF is a private foundation form with a completely different structure.
    """
    # Normalize: remove dashes, strip whitespace, and zero-pad to 9 digits.
    # Some EINs start with 0 (e.g. 010360869) and the IRS index may or may not
    # include the leading zero — zfill(9) ensures both sides always match.
    ein_normalized = ein.replace("-", "").strip().zfill(9)

    # Also zero-pad the index column so the comparison is apples-to-apples
    index_eins_normalized = index_dataframe["EIN"].str.strip().str.zfill(9)
    matching_rows = index_dataframe[index_eins_normalized == ein_normalized]

    # Only full 990 returns have Part VII compensation data
    matching_rows = matching_rows[matching_rows["RETURN_TYPE"] == "990"]

    if len(matching_rows) == 0:
        return None, None, None

    # If multiple filings exist for the same EIN, take the most recent tax period
    most_recent_row = matching_rows.sort_values("TAX_PERIOD", ascending=False).iloc[0]

    object_id  = most_recent_row.get("OBJECT_ID", "").strip()
    tax_period = most_recent_row.get("TAX_PERIOD", "").strip()
    # XML_BATCH_ID is only present in 2024+ indexes
    batch_name = most_recent_row.get("XML_BATCH_ID", "").strip() if "XML_BATCH_ID" in index_dataframe.columns else ""

    return object_id, batch_name, tax_period


# =============================================================================
# SECTION 3: ZIP range-request extraction
# (Downloads only the file we need — no full ZIP download)
# =============================================================================

def read_zip_central_directory(zip_url):
    """
    Read the central directory of a remote ZIP file using range requests.
    The central directory is a table at the end of every ZIP that lists
    all file names and their byte offsets inside the ZIP.

    Returns the raw bytes of the central directory, or None on failure.
    """
    zip_size = get_file_size_from_url(zip_url)
    if not zip_size:
        return None

    # The End of Central Directory (EOCD) record is at the very end of the ZIP.
    # We download the last 65KB which is always enough to find it.
    tail_bytes = download_byte_range_from_url(zip_url, max(0, zip_size - 65536), zip_size - 1)
    if not tail_bytes:
        return None

    # Find the EOCD signature scanning backwards through the tail
    eocd_position = tail_bytes.rfind(ZIP_END_OF_CENTRAL_DIR_SIGNATURE)
    if eocd_position == -1:
        return None

    eocd_data = tail_bytes[eocd_position:]
    if len(eocd_data) < 22:
        return None

    # Parse the EOCD to get the central directory's location and size
    # Format: signature(4) + disk_num(2) + start_disk(2) + entries_here(2) +
    #         total_entries(2) + central_dir_size(4) + central_dir_offset(4) + comment_len(2)
    (_, _, _, _, _, central_dir_size, central_dir_offset, _) = struct.unpack_from("<4sHHHHIIH", eocd_data)

    # Handle ZIP64 format (used for large ZIPs — indicated by offset = 0xFFFFFFFF)
    if central_dir_offset == 0xFFFFFFFF:
        zip64_locator_start = eocd_position - 20
        if zip64_locator_start >= 0:
            zip64_eocd_offset = struct.unpack_from("<Q", tail_bytes, zip64_locator_start + 8)[0]
            zip64_eocd_bytes = download_byte_range_from_url(zip_url, zip64_eocd_offset, zip64_eocd_offset + 55)
            if zip64_eocd_bytes:
                central_dir_size   = struct.unpack_from("<Q", zip64_eocd_bytes, 40)[0]
                central_dir_offset = struct.unpack_from("<Q", zip64_eocd_bytes, 48)[0]

    # Download the central directory itself
    central_dir_bytes = download_byte_range_from_url(
        zip_url, central_dir_offset, central_dir_offset + central_dir_size - 1
    )
    return central_dir_bytes


def find_file_location_in_central_directory(central_dir_bytes, xml_filename):
    """
    Search the central directory bytes for a specific filename.
    Returns (local_header_offset, compressed_size, compression_method) if found,
    or (None, None, None) if the file is not in this ZIP.
    """
    target_filename_bytes = xml_filename.encode("utf-8")
    position = 0

    while position < len(central_dir_bytes) - 4:
        if central_dir_bytes[position:position + 4] != ZIP_CENTRAL_DIR_ENTRY_SIGNATURE:
            break
        if position + 46 > len(central_dir_bytes):
            break

        # Parse the 46-byte fixed header of this central directory entry
        # Format (corrected): sig(4) + ver_made(2) + ver_need(2) + flags(2) +
        #   compression(2) + mod_time(2) + mod_date(2) + crc(4) +
        #   compressed_size(4) + uncompressed_size(4) + name_len(2) +
        #   extra_len(2) + comment_len(2) + disk_num(2) + int_attrs(2) +
        #   ext_attrs(4) + local_offset(4)
        entry_fields = struct.unpack_from("<4sHHHHHHIIIHHHHHII", central_dir_bytes, position)
        compression_method  = entry_fields[4]
        compressed_size     = entry_fields[8]
        name_length         = entry_fields[10]
        extra_length        = entry_fields[11]
        comment_length      = entry_fields[12]
        local_header_offset = entry_fields[16]

        entry_filename_bytes = central_dir_bytes[position + 46 : position + 46 + name_length]

        if entry_filename_bytes == target_filename_bytes:
            return local_header_offset, compressed_size, compression_method

        position += 46 + name_length + extra_length + comment_length

    return None, None, None


def download_and_decompress_xml_from_zip(zip_url, local_header_offset, compressed_size, compression_method):
    """
    Download and decompress a specific XML file from a ZIP.
    Uses the byte offset found in the central directory.
    Returns the raw XML bytes, or None on failure.
    """
    # Read the local file header (30 bytes fixed + variable name/extra) to find the exact data start
    local_header_bytes = download_byte_range_from_url(
        zip_url, local_header_offset, local_header_offset + 1023
    )
    if not local_header_bytes or local_header_bytes[:4] != ZIP_LOCAL_FILE_HEADER_SIGNATURE:
        return None

    local_name_length  = struct.unpack_from("<H", local_header_bytes, 26)[0]
    local_extra_length = struct.unpack_from("<H", local_header_bytes, 28)[0]
    data_start_byte    = local_header_offset + 30 + local_name_length + local_extra_length
    data_end_byte      = data_start_byte + compressed_size - 1

    # Download the compressed file data
    compressed_data = download_byte_range_from_url(zip_url, data_start_byte, data_end_byte)
    if not compressed_data:
        return None

    # Decompress
    try:
        if compression_method == 8:    # DEFLATE (standard ZIP compression)
            return zlib.decompress(compressed_data, -15)  # -15 = raw deflate, no wrapper
        elif compression_method == 0:  # STORED (no compression)
            return compressed_data
        elif compression_method == 9:  # DEFLATE64 (used in some 2025 IRS batch ZIPs)
            return inflate64.Inflater().inflate(compressed_data)
        else:
            print(f"    [WARNING] Unsupported ZIP compression method: {compression_method}")
            return None
    except zlib.error as error:
        print(f"    [WARNING] Failed to decompress XML data: {error}")
        return None


# =============================================================================
# SECTION 4: Batch ZIP search (for 2023 and earlier without XML_BATCH_ID)
# =============================================================================

def build_monthly_batch_search_order(object_id, year):
    """
    For years without XML_BATCH_ID, build a list of monthly batch ZIP names
    to search, in order of most-likely to least-likely.

    The Object ID format appears to embed a week number in digits 4-5,
    which we use to guess the most likely calendar month.
    """
    likely_month = 6  # Default: start searching from June if we can't guess

    if len(object_id) >= 6 and object_id[4:6].isdigit():
        embedded_week_number = int(object_id[4:6])
        # Approximate conversion from week number to calendar month
        likely_month = max(1, min(12, round(embedded_week_number * 12 / 52)))

    # Put the likely month first, then radiate outward in both directions
    search_order = [likely_month]
    for offset in range(1, 13):
        for candidate_month in [likely_month + offset, likely_month - offset]:
            if 1 <= candidate_month <= 12 and candidate_month not in search_order:
                search_order.append(candidate_month)

    # Try A through E variants for each month — IRS has used A, B, C, D in different years
    batch_names = []
    for month in search_order:
        for suffix in ["A", "B", "C", "D", "E"]:
            batch_names.append(f"{year}_TEOS_XML_{month:02d}{suffix}")
    return batch_names


def find_batch_and_download_xml(object_id, year, batch_name_hint=""):
    """
    Find the batch ZIP that contains the given Object ID and extract the XML file.
    If batch_name_hint is provided (from 2024+ index), goes directly to that ZIP.
    For 2023 and earlier, searches monthly batch ZIPs in order of likelihood.

    Returns (xml_bytes, batch_name_used) or (None, None) if not found.
    """
    if batch_name_hint:
        # IRS index sometimes uses lowercase batch names (e.g. "05a").
        # Try both the hint as-is and uppercased — IRS Linux servers are case-sensitive.
        hint_upper = batch_name_hint.upper()
        hint_lower = batch_name_hint.lower()
        # Deduplicate while preserving order (uppercase first)
        seen = set()
        batches_to_search = []
        for b in [hint_upper, hint_lower]:
            if b not in seen:
                seen.add(b)
                batches_to_search.append(b)
    else:
        batches_to_search = build_monthly_batch_search_order(object_id, year)

    for batch_name in batches_to_search:
        zip_url = IRS_BATCH_ZIP_URL.format(year=year, batch_name=batch_name)

        print(f"    Checking batch {batch_name}...")
        central_dir_bytes = read_zip_central_directory(zip_url)
        if central_dir_bytes is None:
            continue  # This batch ZIP may not exist for this year

        # Try with the batch-name subfolder first (2024 and earlier ZIP structure),
        # then fall back to the root-level path (2025+ ZIP structure, no subfolder).
        xml_filename = f"{batch_name}/{object_id}_public.xml"
        local_header_offset, compressed_size, compression_method = find_file_location_in_central_directory(
            central_dir_bytes, xml_filename
        )

        if local_header_offset is None:
            # 2025+ ZIPs store files at the root with no batch-name subfolder
            xml_filename = f"{object_id}_public.xml"
            local_header_offset, compressed_size, compression_method = find_file_location_in_central_directory(
                central_dir_bytes, xml_filename
            )

        if local_header_offset is None:
            continue  # File not in this batch

        print(f"    Found in {batch_name}. Downloading XML...")
        xml_bytes = download_and_decompress_xml_from_zip(
            zip_url, local_header_offset, compressed_size, compression_method
        )
        return xml_bytes, batch_name

    return None, None


# =============================================================================
# SECTION 5: Main entry point
# =============================================================================

def download_filing_for_org(ein, year, index_dataframe):
    """
    Find and download the 990 XML filing for a given EIN and year.

    Requires the already-downloaded index DataFrame (from download_irs_index_for_year).
    Returns a tuple: (xml_tree, xml_url, pdf_url) or (None, None, None) if not found.

    - xml_tree: parsed XML object (passed to parser.py)
    - xml_url:  informational URL showing which batch ZIP and file was used
    - pdf_url:  link to ProPublica's page for this org (IRS PDFs aren't directly linkable)
    """
    object_id, batch_name, tax_period = find_filing_in_index(index_dataframe, ein)

    if not object_id:
        print(f"    [WARNING] No 990 filing found for EIN {ein} in the {year} index.")
        return None, None, None, None

    print(f"    Object ID: {object_id} | Batch hint: {batch_name or '(none — will search)'} | Tax period: {tax_period}")

    xml_bytes, batch_name_used = find_batch_and_download_xml(object_id, year, batch_name_hint=batch_name)

    if not xml_bytes:
        print(f"    [WARNING] Could not locate or download XML for EIN {ein} ({year}).")
        return None, None, None, None

    try:
        xml_tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as error:
        print(f"    [WARNING] XML file for EIN {ein} ({year}) could not be parsed: {error}")
        return None, None, None, None

    xml_url = f"{IRS_BATCH_ZIP_URL.format(year=year, batch_name=batch_name_used)}#{object_id}_public.xml"
    pdf_url = f"https://projects.propublica.org/nonprofits/organizations/{ein.replace('-', '')}"

    return xml_tree, xml_url, pdf_url, tax_period
