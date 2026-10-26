"""Document types: how to recognise each one and which fields to read from it.

`TEMPLATES[doc_type]["fields"]` holds the default extraction patterns. A state can override or add
patterns under `STATE_OVERRIDES[state_code][doc_type]` without code changes elsewhere.
Each pattern must capture the value in a named group `v`.
"""

DATE = r"(?P<v>\d{1,2}[-/.]\d{1,2}[-/.]\d{4})"

DOC_TYPES = {
    "FIRE_NOC": "Fire NOC",
    "BUILDING_COMPLETION": "Building completion certificate",
    "STRUCTURAL_STABILITY": "Structural stability certificate",
    "LAND_DEED": "Land document (registered deed)",
    "AFFILIATION_LETTER": "University affiliation letter",
    "NBA_ACCREDITATION": "NBA accreditation certificate",
    "TER_RECEIPT": "TER payment receipt",
    "AFFIDAVIT": "Affidavit (undertaking)",
    "FACULTY_LIST": "Faculty list",
    "LAB_PHOTO": "Computer-lab photograph",
}

TEMPLATES = {
    "FIRE_NOC": {
        "keywords": {"fire no objection certificate": 4, "chief fire officer": 3, "fire prevention": 2,
                     "fire safety": 1, "fire": 1, "noc": 1},
        "fields": {
            "cert_no": [r"No\.?\s*(?P<v>FNOC/[0-9A-Z/\-]+)"],
            "issue_date": [r"Date\s*[:\-]\s*" + DATE],
            "premises_name": [r"^Name of premises\s*[:\-]?\s*(?P<v>.+)$"],
            "address": [r"^Address\s*[:\-]?\s*(?P<v>.+)$"],
            "built_up_area": [r"Built-up area\s*[:\-]?\s*(?P<v>[\d,]+)\s*m"],
            "valid_from": [r"Valid from\s*[:\-]?\s*" + DATE],
            "valid_till": [r"Valid till\s*[:\-]?\s*" + DATE, r"Valid up ?to\s*[:\-]?\s*" + DATE],
        },
    },
    "BUILDING_COMPLETION": {
        "keywords": {"completion certificate": 4, "occupancy": 2, "building permission": 2, "municipal": 1},
        "fields": {
            "cert_no": [r"Certificate No\.?\s*[:\-]?\s*(?P<v>BCC/[0-9A-Z/\-]+)"],
            "issue_date": [r"Date of issue\s*[:\-]?\s*" + DATE],
            "premises_name": [r"^Name of (?:premises|owner)\s*[:\-]?\s*(?P<v>.+)$"],
            "built_up_area": [r"Built-up area\s*[:\-]?\s*(?P<v>[\d,]+)\s*m"],
        },
    },
    "STRUCTURAL_STABILITY": {
        "keywords": {"structural stability": 5, "structural engineer": 3, "load bearing": 1},
        "fields": {
            "cert_no": [r"Certificate No\.?\s*[:\-]?\s*(?P<v>SSC/[0-9A-Z/\-]+)"],
            "issue_date": [r"Date of issue\s*[:\-]?\s*" + DATE],
            "premises_name": [r"^Name of premises\s*[:\-]?\s*(?P<v>.+)$"],
            "valid_till": [r"Valid till\s*[:\-]?\s*" + DATE],
        },
    },
    "LAND_DEED": {
        "keywords": {"sale deed": 4, "sub-registrar": 3, "registration no": 2, "survey no": 2, "conveyance": 1},
        "fields": {
            "registration_no": [r"Registration No\.?\s*[:\-]?\s*(?P<v>[A-Z]{2,4}/[0-9A-Z/\-]+)"],
            "registration_date": [r"Date of registration\s*[:\-]?\s*" + DATE],
            "owner_name": [r"^Purchaser\s*[:\-]?\s*(?P<v>.+)$"],
            "survey_no": [r"Survey No\.?\s*[:\-]?\s*(?P<v>[0-9A-Z/\-]+)"],
            "area_acres": [r"Area\s*[:\-]?\s*(?P<v>[\d.]+)\s*acres"],
        },
    },
    "AFFILIATION_LETTER": {
        "keywords": {"affiliation": 4, "university": 2, "approved intake": 3, "academic year": 2, "registrar": 1},
        "fields": {
            "letter_no": [r"Letter No\.?\s*[:\-]?\s*(?P<v>AFF/[0-9A-Z/\-]+)"],
            "issue_date": [r"Date\s*[:\-]\s*" + DATE],
            "academic_year": [r"academic year\s*(?P<v>\d{4}\s*-\s*\d{2})"],
            "institution_name": [r"^Institution\s*[:\-]?\s*(?P<v>.+)$"],
        },
        # lines such as "B.Tech Computer Science and Engineering   120"
        "intake_lines": r"^(?P<prog>(?:B\.Tech|M\.Tech|B\.Pharm|M\.Pharm|MBA|MCA|Diploma)\s[A-Za-z&().,\- ]{2,80}?)\s+(?P<v>\d{2,3})$",
    },
    "NBA_ACCREDITATION": {
        "keywords": {"national board of accreditation": 5, "accreditation": 3, "accredited": 2},
        "fields": {
            "accreditation_no": [r"Accreditation No\.?\s*[:\-]?\s*(?P<v>NBA/[0-9A-Z/\-]+)"],
            "institution_name": [r"^Institution\s*[:\-]?\s*(?P<v>.+)$"],
            "valid_till": [r"Valid till\s*[:\-]?\s*" + DATE],
        },
    },
    "TER_RECEIPT": {
        "keywords": {"payment receipt": 4, "transaction": 2, "processing fee": 3, "ter": 1, "amount": 1},
        "fields": {
            "txn_id": [r"Transaction ID\s*[:\-]?\s*(?P<v>TER-[0-9A-Z\-]+)"],
            "amount": [r"Amount\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*(?P<v>[\d,]+)"],
            "payment_date": [r"Payment date\s*[:\-]?\s*" + DATE],
            "institution_name": [r"^Paid by\s*[:\-]?\s*(?P<v>.+)$"],
        },
    },
    "AFFIDAVIT": {
        "keywords": {"affidavit": 5, "solemnly": 3, "deponent": 3, "notary": 2, "undertaking": 2},
        "fields": {
            "deponent": [r"I,\s*(?P<v>[A-Z][A-Za-z. ]{3,60}?),"],
            "affidavit_date": [r"(?:Dated|Date)\s*[:\-]?\s*" + DATE],
            "notary_reg_no": [r"Notary Reg(?:istration)?\.? No\.?\s*[:\-]?\s*(?P<v>[0-9A-Z/\-]+)"],
        },
    },
    "FACULTY_LIST": {
        "keywords": {"faculty": 4, "designation": 2, "qualification": 2, "faculty id": 3},
        "fields": {},
        "faculty_ids": r"(?P<v>FID-\d{5,7})",
    },
    "LAB_PHOTO": {"keywords": {}, "fields": {}},
}

# Example of a state-specific variant: Maharashtra fire NOCs print "Valid up to" instead of "Valid till".
STATE_OVERRIDES = {
    "MH": {"FIRE_NOC": {"valid_till": [r"Valid up to\s*[:\-]?\s*" + DATE]}},
}

DATE_FIELDS = {"issue_date", "valid_from", "valid_till", "registration_date", "payment_date", "affidavit_date"}
NUMBER_FIELDS = {"built_up_area", "amount"}


def field_patterns(doc_type: str, state_code: str | None) -> dict[str, list[str]]:
    base = {k: list(v) for k, v in TEMPLATES.get(doc_type, {}).get("fields", {}).items()}
    for name, extra in STATE_OVERRIDES.get(state_code or "", {}).get(doc_type, {}).items():
        base[name] = list(extra) + base.get(name, [])
    return base
