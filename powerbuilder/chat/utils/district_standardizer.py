import re

# ---------------------------------------------------------------------------
# At-large district normalization
# ---------------------------------------------------------------------------

# Canonical aliases that all mean "this state has one at-large representative".
# Covers MEDSL ("ZZ", 0), Census API ("ZZ"), user queries ("at-large"), and
# common zero-padded strings ("00", "000", "0000").  Zero is also handled
# numerically in normalize_district so the set only needs the string forms.
_AT_LARGE_TOKENS: frozenset = frozenset({
    "zz", "al", "at-large", "at large", "at_large", "atlarge",
})


def normalize_district(district_id, state_fips=None) -> int:
    """
    Normalize any district identifier to a plain integer district number.

    Handles every form that appears across MEDSL data, Census API responses,
    election ingestor records, and user queries:

      At-large aliases  → 1
        'ZZ', 'AL', 'at-large', 'at large', 'AT-LARGE', 'AT LARGE'
      Zero values       → 1  (at-large convention used by MEDSL)
        0, '0', '00', '000', '0000'
      Zero-padded       → stripped integer
        '01' → 1,  '06' → 6
      GEOID format      → district number  (requires state_fips)
        '0406' with state_fips='04' → 6
      Plain integer     → itself
        6 → 6

    Raises ValueError for inputs that cannot be interpreted as a district number.
    """
    # Fast path for plain integers
    if isinstance(district_id, int):
        return 1 if district_id == 0 else district_id

    s = str(district_id).strip()

    # At-large text aliases (case-insensitive)
    if s.lower() in _AT_LARGE_TOKENS:
        return 1

    # GEOID format: "SSDD" (4 chars) where SS = state_fips, DD = district
    # Strip the state prefix so "0406" with state_fips "04" → "06" → 6.
    if state_fips is not None:
        prefix = str(state_fips).zfill(2)
        if len(s) == len(prefix) + 2 and s.startswith(prefix):
            s = s[len(prefix):]

    try:
        n = int(s)
        return 1 if n == 0 else n
    except (ValueError, TypeError):
        raise ValueError(
            f"normalize_district: cannot interpret {district_id!r} as a district number"
        )


class GeographyStandardizer:
    """
    The 'Golden Key' Engine: Converts natural language into 
    precise Census GEOIDs/FIPS codes.
    """

    STATE_FIPS = {
        "alabama": "01", "al": "01",
        "alaska": "02", "ak": "02",
        "arizona": "04", "az": "04",
        "arkansas": "05", "ar": "05",
        "california": "06", "ca": "06",
        "colorado": "08", "co": "08",
        "connecticut": "09", "ct": "09",
        "delaware": "10", "de": "10",
        "district of columbia": "11", "dc": "11",
        "florida": "12", "fl": "12",
        "georgia": "13", "ga": "13",
        "hawaii": "15", "hi": "15",
        "idaho": "16", "id": "16",
        "illinois": "17", "il": "17",
        "indiana": "18", "in": "18",
        "iowa": "19", "ia": "19",
        "kansas": "20", "ks": "20",
        "kentucky": "21", "ky": "21",
        "louisiana": "22", "la": "22",
        "maine": "23", "me": "23",
        "maryland": "24", "md": "24",
        "massachusetts": "25", "ma": "25",
        "michigan": "26", "mi": "26",
        "minnesota": "27", "mn": "27",
        "mississippi": "28", "ms": "28",
        "missouri": "29", "mo": "29",
        "montana": "30", "mt": "30",
        "nebraska": "31", "ne": "31",
        "nevada": "32", "nv": "32",
        "new hampshire": "33", "nh": "33",
        "new jersey": "34", "nj": "34",
        "new mexico": "35", "nm": "35",
        "new york": "36", "ny": "36",
        "north carolina": "37", "nc": "37",
        "north dakota": "38", "nd": "38",
        "ohio": "39", "oh": "39",
        "oklahoma": "40", "ok": "40",
        "oregon": "41", "or": "41",
        "pennsylvania": "42", "pa": "42",
        "rhode island": "44", "ri": "44",
        "south carolina": "45", "sc": "45",
        "south dakota": "46", "sd": "46",
        "tennessee": "47", "tn": "47",
        "texas": "48", "tx": "48",
        "utah": "49", "ut": "49",
        "vermont": "50", "vt": "50",
        "virginia": "51", "va": "51",
        "washington": "53", "wa": "53",
        "west virginia": "54", "wv": "54",
        "wisconsin": "55", "wi": "55",
        "wyoming": "56", "wy": "56",
        "american samoa": "60", "as": "60",
        "guam": "66", "gu": "66",
        "northern mariana islands": "69", "mp": "69",
        "puerto rico": "72", "pr": "72",
        "virgin islands": "78", "vi": "78"
    }

    @staticmethod
    def convert_to_geoid(state_name, district_num, chamber_type="congressional"):
        state_code = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
        if not state_code:
            return {"error": f"State '{state_name}' not recognized."}

        # Normalise any at-large alias or zero value to 1 so that single-district
        # states always produce a valid GEOID like "0201".
        try:
            district_num = normalize_district(district_num, state_fips=state_code)
        except ValueError:
            return {"error": f"District identifier {district_num!r} could not be normalized."}

        dist_padded = str(district_num).zfill(2) # '7' -> '07'

        # Census Bureau GEOID Standard Formats:
        if chamber_type == "congressional":
            # Format: [State FIPS (2)][District (2)] -> e.g., '5107'
            return f"{state_code}{dist_padded}"
        
        elif chamber_type == "state_senate":
            # Format: [State FIPS (2)][SLDU Prefix (3)][District (3)]
            # Often handled as 51 + district for internal math
            return f"{state_code}S{dist_padded.zfill(3)}" 
        
        elif chamber_type == "state_house":
            return f"{state_code}H{dist_padded.zfill(3)}"

        return f"{state_code}{dist_padded}"