import re


# The XML tag that wraps each person's compensation block in Part VII
PART_VII_PERSON_BLOCK_TAG = "Form990PartVIISectionAGrp"


def read_filing_tax_year(xml_root, namespace_prefix):
    """
    Read the <TaxYr> tag from the filing's ReturnHeader.
    This tells us which fiscal year the 990 actually covers (e.g. 2023),
    which may differ from the IRS index year used to find the filing.
    Returns the tax year as an integer, or None if the tag is missing.
    """
    tax_year_element = xml_root.find(f".//{namespace_prefix}TaxYr")
    if tax_year_element is not None and tax_year_element.text:
        try:
            return int(tax_year_element.text.strip())
        except ValueError:
            return None
    return None


def check_filing_is_current_enough(org_name, irs_index_year, tax_period_from_index):
    """
    Verify that this filing's actual fiscal period is not stale relative to the
    IRS index year the user requested.

    Uses TAX_PERIOD from the IRS index (e.g. "202309"), NOT <TaxYr> from the XML.

    WHY: <TaxYr> in IRS XML = the year the fiscal period BEGINS.
    For non-December fiscal year filers (e.g. Oct 2022 - Sep 2023), TaxYr = 2022
    even though the period ends in 2023. Using TaxYr incorrectly blocks these orgs.

    TAX_PERIOD (from the index CSV) = the period END year+month (YYYYMM).
    The first 4 digits = the year the fiscal period ends. This is the correct value
    to compare against the IRS index year.

    A filing found in index year N is acceptable if its period ends in year N-1 or later.
    If the period ended in N-2 or earlier, the org filed significantly late and the data
    is outdated.

    Returns True if the filing is acceptable.
    Returns False (and prints a warning) if the filing is stale and should be skipped.
    """
    if not tax_period_from_index or len(tax_period_from_index) < 4:
        print(f"    [WARNING] Could not read tax period for {org_name}. Proceeding anyway.")
        return True

    period_end_year = int(tax_period_from_index[:4])
    expected_end_year = irs_index_year - 1

    if period_end_year < expected_end_year:
        years_behind = expected_end_year - period_end_year
        print(f"    [STALE FILING] {org_name}'s filing covers the period ending {tax_period_from_index}, "
              f"but index year {irs_index_year} should have data ending in {expected_end_year}.")
        print(f"    This org filed late. Their data is {years_behind} year(s) behind.")
        print(f"    Skipping to avoid labeling old data as {irs_index_year} data.")
        return False

    return True


def detect_xml_namespace(xml_root):
    """
    IRS XML files wrap every tag in a namespace like {http://www.irs.gov/efile}.
    This function reads the namespace from the root tag and returns it as a
    prefix string (e.g. '{http://www.irs.gov/efile}') so we can search for tags.
    Returns an empty string if no namespace is found.
    """
    root_tag = xml_root.tag  # looks like: {http://www.irs.gov/efile}Return
    namespace_match = re.match(r'\{[^}]+\}', root_tag)
    if namespace_match:
        return namespace_match.group(0)  # returns e.g. '{http://www.irs.gov/efile}'
    return ""


def read_text_from_tag(parent_element, tag_name, namespace_prefix):
    """
    Find a child tag by name inside a parent element and return its text content.
    Returns an empty string if the tag is missing or has no text.
    """
    found_element = parent_element.find(f"{namespace_prefix}{tag_name}")
    if found_element is not None and found_element.text:
        return found_element.text.strip()
    return ""


def read_dollar_amount_from_tag(parent_element, tag_name, namespace_prefix):
    """
    Find a child tag by name and return its value as an integer dollar amount.
    Returns 0 if the tag is missing, empty, or not a valid number.
    """
    raw_text = read_text_from_tag(parent_element, tag_name, namespace_prefix)
    if not raw_text:
        return 0
    try:
        return int(float(raw_text))
    except ValueError:
        return 0


def extract_compensation_rows(xml_root, org_name, ein, year, xml_url, pdf_url, tax_period_from_index=""):
    """
    Extract all compensation entries from Part VII of a 990 XML filing.

    Searches for every person block (Form990PartVIISectionAGrp) in the XML,
    pulls the name, title, and compensation amounts, and returns them as a
    list of dicts — one dict per person.

    tax_period_from_index: the TAX_PERIOD string from the IRS index CSV (e.g. "202309").
    Used to check for stale filings. If empty, the check is skipped with a warning.

    Returns an empty list if no compensation data is found, or if the filing
    turns out to cover a fiscal period that is too far behind the requested year
    (stale filing — org filed late).
    """
    namespace_prefix = detect_xml_namespace(xml_root)

    # Block stale filings before extracting anything.
    # Uses TAX_PERIOD from the IRS index (period end year), NOT <TaxYr> from the XML.
    if not check_filing_is_current_enough(org_name, year, tax_period_from_index):
        return []

    person_block_tag = f"{namespace_prefix}{PART_VII_PERSON_BLOCK_TAG}"

    # Search the entire XML tree for Part VII person blocks
    all_person_blocks = xml_root.findall(f".//{person_block_tag}")

    if not all_person_blocks:
        # Check if the org flagged that additional Part VII data is in Schedule O (free-form text).
        # If so, the data exists but is not machine-readable in the XML — it requires manual PDF review.
        schedule_o_flag = xml_root.find(f".//{namespace_prefix}InfoInScheduleOPartVIInd")
        if schedule_o_flag is not None and schedule_o_flag.text and schedule_o_flag.text.strip().upper() in ("X", "TRUE", "1"):
            print(f"    [MANUAL REVIEW NEEDED] {org_name} reports Part VII compensation in Schedule O (free-form text).")
            print(f"    This data cannot be extracted automatically. Review the PDF at the pdf_url.")
        else:
            print(f"    [WARNING] No Part VII compensation data found for {org_name} ({year}).")
        return []

    compensation_rows = []

    for person_block in all_person_blocks:
        person_name = read_text_from_tag(person_block, "PersonNm", namespace_prefix)
        irs_title = read_text_from_tag(person_block, "TitleTxt", namespace_prefix)

        # Skip blocks with no name (sometimes the XML has empty filler rows)
        if not person_name:
            continue

        base_comp = read_dollar_amount_from_tag(
            person_block, "ReportableCompFromOrgAmt", namespace_prefix
        )
        # Column E: compensation paid by related organizations (sister entities, subsidiaries).
        # This is NOT a bonus — it is wages from a related org, reported separately by IRS rules.
        related_org_comp = read_dollar_amount_from_tag(
            person_block, "ReportableCompFromRltdOrgAmt", namespace_prefix
        )
        other_comp = read_dollar_amount_from_tag(
            person_block, "OtherCompensationAmt", namespace_prefix
        )

        # Total = wages from this org + wages from related orgs + other compensation
        # This matches IRS Part VII column G (D + E + F) — the full picture of what
        # the person earns, regardless of which entity in the family cuts the paycheck.
        total_comp = base_comp + related_org_comp + other_comp

        compensation_rows.append({
            "org_name":          org_name,
            "ein":               ein,
            "year":              year,
            "person_name":       person_name,
            "irs_title":         irs_title,
            "base_comp":         base_comp,
            "related_org_comp":  related_org_comp,
            "other_comp":        other_comp,
            "total_comp":        total_comp,
            "xml_url":           xml_url,
            "pdf_url":           pdf_url,
        })

    return compensation_rows
