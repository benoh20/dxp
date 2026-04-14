# powerbuilder/chat/utils/cook_client.py
"""
CookPoliticalClient — optional Cook Political Report integration layer.

Architecture
------------
1. Credentials check: if COOK_EMAIL / COOK_PASSWORD are absent, returns a
   null-result dict immediately. The agent still runs; the memo notes the gap.
2. Static seed file first: `data/cook_pvi_2025.json` is checked before any
   network call. Built from Cook's February 2025 PVI release (see seed file).
3. 24-hour local cache: API responses are written to `data/cook_cache/` as
   JSON files. A fresh cache hit skips the API call entirely.
4. Live API call: Cook Political Report is a subscriber service. The endpoint
   URLs below are illustrative — update them when API access is provisioned.
   Cook's guidance is one request per second; the client adds a short sleep.

Returned dict schema
--------------------
{
    "cook_pvi":    "R+5" | "D+3" | "EVEN" | None,
    "race_rating": "Lean R" | "Likely D" | "Toss-up" | None,
    "incumbent":   "Rep. Jane Doe (R)" | None,
    "cycle":       2026 | None,
    "source":      "seed" | "cache" | "api" | None,
}

None values in all fields means Cook data was not available (no credentials,
API error, or district not covered by Cook).
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CACHE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/cook_cache"))
SEED_PATH    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/cook_pvi_2025.json"))
CACHE_TTL    = timedelta(hours=24)

# Cook Political Report API — subscriber service.
# Update BASE_URL and endpoint paths when API credentials / docs are available.
# As of 2025, Cook does not publish a formal REST API; access is negotiated
# with their data team. These paths are illustrative placeholders.
BASE_URL = "https://data.cookpolitical.com/api/v1"  # placeholder — verify with Cook

ENDPOINTS = {
    "congressional": "/house/ratings/{state}/{district}",
    "senate":        "/senate/ratings/{state}",
    "governor":      "/governor/ratings/{state}",
    # State legislative races are not covered by Cook Political Report.
    "state_house":   None,
    "state_senate":  None,
}

# Mapping from Cook's raw rating strings to normalised labels
RATING_MAP = {
    "safe democrat":     "Safe D",
    "likely democrat":   "Likely D",
    "lean democrat":     "Lean D",
    "toss-up":           "Toss-up",
    "toss up":           "Toss-up",
    "lean republican":   "Lean R",
    "likely republican": "Likely R",
    "safe republican":   "Safe R",
}

# ---------------------------------------------------------------------------
# Null result helper
# ---------------------------------------------------------------------------

def _null_result(source: Optional[str] = None) -> dict:
    return {
        "cook_pvi":    None,
        "race_rating": None,
        "incumbent":   None,
        "cycle":       None,
        "source":      source,
    }


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CookPoliticalClient:
    """
    Fetches Cook Political Report PVI and race ratings with a layered
    fallback chain: static seed → 24-hour local cache → live API.

    When COOK_EMAIL and COOK_PASSWORD are absent the client returns _null_result
    immediately without network I/O or raising exceptions.
    """

    def __init__(self):
        self.email    = os.environ.get("COOK_EMAIL", "").strip()
        self.password = os.environ.get("COOK_PASSWORD", "").strip()
        self._has_creds = bool(self.email and self.password)

        if not self._has_creds:
            logger.info(
                "Cook Political Report credentials not configured — skipping. "
                "Set COOK_EMAIL and COOK_PASSWORD to enable live ratings."
            )

        # Load static seed once on construction
        self._seed: dict = self._load_seed()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        district_type: str,
        district_id: str,
        state_fips: str,
        cycle: int = 2026,
    ) -> dict:
        """
        Return Cook data for the given district.

        Parameters
        ----------
        district_type : "congressional" | "senate" | "governor" | "state_house" | "state_senate"
        district_id   : GEOID string e.g. "5107" (congressional) or "statewide" (senate)
        state_fips    : 2-char FIPS string e.g. "51"
        cycle         : target election cycle (default 2026)

        Returns a dict matching the schema in the module docstring.
        """
        # Districts Cook doesn't cover
        if ENDPOINTS.get(district_type) is None and district_type not in ("congressional", "senate", "governor"):
            return _null_result()

        # 1. Static seed (always checked, no credentials required)
        seed_result = self._check_seed(district_type, district_id, state_fips)
        if seed_result:
            return {**seed_result, "source": "seed"}

        # 2. No credentials → stop here
        if not self._has_creds:
            return _null_result()

        # 3. Local 24-hour cache
        cache_key  = self._cache_key(district_type, district_id, state_fips, cycle)
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
        cached     = self._load_cache(cache_path)
        if cached:
            return {**cached, "source": "cache"}

        # 4. Live API call
        api_result = self._call_api(district_type, district_id, state_fips, cycle)
        if api_result:
            self._save_cache(cache_path, api_result)
            return {**api_result, "source": "api"}

        return _null_result()

    # ------------------------------------------------------------------
    # Static seed
    # ------------------------------------------------------------------

    def _load_seed(self) -> dict:
        """Load data/cook_pvi_2025.json into memory. Returns {} on failure."""
        try:
            with open(SEED_PATH) as f:
                data = json.load(f)
            logger.debug(f"CookClient: loaded seed file ({len(data.get('districts', {}))} districts)")
            return data
        except FileNotFoundError:
            logger.debug("CookClient: seed file not found — PVI seed unavailable.")
            return {}
        except json.JSONDecodeError as e:
            logger.warning(f"CookClient: seed file parse error — {e}")
            return {}

    def _check_seed(self, district_type: str, district_id: str, state_fips: str) -> Optional[dict]:
        """
        Look up the district in the static seed file.
        Returns a partial result dict (missing 'source') or None if not found.
        Congressional districts: keyed by GEOID (e.g. "5107").
        Senate: keyed by state_fips + "_senate".
        """
        districts = self._seed.get("districts", {})

        if district_type == "senate":
            key = f"{state_fips}_senate"
        elif district_type == "governor":
            key = f"{state_fips}_gov"
        else:
            key = district_id  # GEOID e.g. "5107"

        entry = districts.get(key)
        if not entry:
            return None

        return {
            "cook_pvi":    entry.get("cook_pvi"),
            "race_rating": entry.get("race_rating"),
            "incumbent":   entry.get("incumbent"),
            "cycle":       entry.get("cycle"),
        }

    # ------------------------------------------------------------------
    # Local cache
    # ------------------------------------------------------------------

    def _cache_key(self, district_type: str, district_id: str, state_fips: str, cycle: int) -> str:
        safe_id = district_id.replace("/", "_")
        return f"{state_fips}_{district_type}_{safe_id}_{cycle}"

    def _load_cache(self, path: str) -> Optional[dict]:
        """Return cached dict if it exists and is younger than CACHE_TTL, else None."""
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
            if datetime.now() - cached_at < CACHE_TTL:
                data.pop("_cached_at", None)
                return data
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return None

    def _save_cache(self, path: str, data: dict):
        os.makedirs(CACHE_DIR, exist_ok=True)
        payload = {**data, "_cached_at": datetime.now().isoformat()}
        try:
            with open(path, "w") as f:
                json.dump(payload, f)
        except OSError as e:
            logger.warning(f"CookClient: could not write cache to {path} — {e}")

    # ------------------------------------------------------------------
    # Live API
    # ------------------------------------------------------------------

    def _call_api(
        self,
        district_type: str,
        district_id: str,
        state_fips: str,
        cycle: int,
    ) -> Optional[dict]:
        """
        Attempt a live Cook Political Report API call.

        NOTE: Cook does not publish a public REST API spec. The URL pattern
        below is a placeholder. When Cook provides API documentation, update:
          1. BASE_URL and ENDPOINTS at the top of this module
          2. The response parsing logic in _parse_api_response()
        """
        try:
            import requests
        except ImportError:
            logger.error("CookClient: 'requests' package not installed — cannot call API.")
            return None

        endpoint_tpl = ENDPOINTS.get(district_type)
        if not endpoint_tpl:
            return None

        # Build URL — placeholder parameters; adjust to actual API spec
        state_abbr   = self._fips_to_abbr(state_fips)
        district_num = district_id.replace(state_fips, "").lstrip("0") or "0"
        url = BASE_URL + endpoint_tpl.format(state=state_abbr, district=district_num)

        try:
            time.sleep(1.0)  # respect Cook's rate-limit guidance
            resp = requests.get(
                url,
                auth=(self.email, self.password),
                timeout=10,
                params={"cycle": cycle},
            )
            resp.raise_for_status()
            return self._parse_api_response(resp.json(), cycle)
        except Exception as e:
            logger.warning(f"CookClient: API call failed for {district_type} {district_id} — {e}")
            return None

    @staticmethod
    def _parse_api_response(data: dict, cycle: int) -> Optional[dict]:
        """
        Parse a Cook API JSON response into our standard result dict.
        UPDATE THIS METHOD when the actual Cook API spec is known.
        """
        if not isinstance(data, dict):
            return None

        raw_rating = (data.get("rating") or data.get("race_rating") or "").lower().strip()
        rating     = RATING_MAP.get(raw_rating)

        return {
            "cook_pvi":    data.get("pvi") or data.get("cook_pvi"),
            "race_rating": rating or raw_rating or None,
            "incumbent":   data.get("incumbent"),
            "cycle":       data.get("cycle") or cycle,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Inverted from GeographyStandardizer.STATE_FIPS — only 2-char abbreviations.
    _FIPS_TO_ABBR = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
        "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
        "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
        "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
        "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
        "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
        "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
        "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
        "56": "WY",
    }

    def _fips_to_abbr(self, fips: str) -> str:
        return self._FIPS_TO_ABBR.get(fips.zfill(2), fips)
