"""
Generate a synthetic Georgia voterfile CSV for the Powerbuilder demo.

Designed for the Gwinnett GOTV demo flow:
    "Organizer creates a GOTV campaign for Latinx voters 18-35 in Gwinnett County
     -> app suggests a precinct universe -> generates a Spanish-language door
     script -> exports CSV."

This script produces a TargetSmart-shaped CSV that the existing
chat/agents/voterfile_agent.py will detect as 'TargetSmart' and process
through its full standardization + segmentation pipeline.

NO REAL VOTER DATA. All names, addresses, IDs, scores, and vote history are
fabricated. Demographic distributions are tuned to match Gwinnett County
publicly reported aggregates (Census ACS + GA SOS aggregate counts) so the
demo feels realistic without exposing any real voter PII.

Usage:
    python scripts/generate_demo_voterfile.py [--out PATH] [--rows N] [--seed N]

Defaults:
    --out   data/demo/gwinnett_demo_voterfile.csv
    --rows  50000   (subset of the ~720K real VAP, kept small for fast demo upload)
    --seed  20260427  (deterministic; same seed = identical file)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import string
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Reference data — Gwinnett County, GA
# ---------------------------------------------------------------------------

STATE = "GA"
COUNTY = "Gwinnett"
COUNTY_FIPS = "13135"

# 16 of Gwinnett's largest cities/places. Real city names so geographic joins work.
CITIES = [
    ("Lawrenceville",   "30043"), ("Lawrenceville",   "30044"),
    ("Duluth",          "30096"), ("Duluth",          "30097"),
    ("Norcross",        "30071"), ("Norcross",        "30093"),
    ("Snellville",      "30039"), ("Snellville",      "30078"),
    ("Suwanee",         "30024"), ("Buford",          "30518"),
    ("Buford",          "30519"), ("Lilburn",         "30047"),
    ("Grayson",         "30017"), ("Loganville",      "30052"),
    ("Sugar Hill",      "30518"), ("Peachtree Corners","30092"),
]

STREET_NAMES = [
    "Peachtree", "Sugarloaf", "Oak", "Magnolia", "Pine Bluff", "Buford",
    "Lawrenceville", "Sweetwater", "Camp Creek", "Old Norcross", "Pleasant Hill",
    "Indian Trail", "Five Forks", "Club", "River", "Stonewall", "Highland",
    "Ridge", "Trickum", "Killian Hill", "Centerville", "Lenora Church",
    "Beaver Ruin", "Singleton", "Rockbridge", "Hewatt", "Petersen",
]

STREET_TYPES = ["Rd", "Dr", "Ln", "Way", "Trl", "Ct", "Pkwy", "Pl", "Cir", "Blvd"]

# 156 fake precinct codes patterned on real GA precinct naming
PRECINCT_PREFIXES = [
    "BAY", "BEN", "BER", "CEN", "DUL", "DAC", "GOO", "HAR", "LAW", "LIL",
    "LOG", "NOR", "PCC", "REH", "SNL", "SUW", "SUG",
]

# Race / ethnicity distribution.
# Tuned to roughly match Gwinnett County ACS estimates AND the live
# Powerbuilder response (White 65 / Black 21 / Hispanic 7 / AAPI 12 oversum is
# expected — Hispanic is an ethnicity overlay in Census). We pick MUTUALLY
# EXCLUSIVE buckets that sum to 100 for clean demo segmentation.
RACE_DISTRIBUTION = [
    ("White",                    0.43),
    ("Black/African American",   0.27),
    ("Hispanic/Latino",          0.18),  # oversampled vs 7% so demo target group has volume
    ("Asian/AAPI",               0.10),
    ("Other",                    0.02),
]

GENDER_DISTRIBUTION = [("F", 0.52), ("M", 0.46), ("U", 0.02)]

PARTY_DISTRIBUTION = [
    ("Dem", 0.48), ("Rep", 0.36), ("NPA", 0.14), ("Other", 0.02),
]

# Hispanic surname pool (publicly common surnames; no individuals referenced)
HISPANIC_LAST = [
    "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Perez", "Sanchez", "Ramirez", "Torres", "Flores", "Rivera", "Gomez",
    "Diaz", "Morales", "Reyes", "Cruz", "Ortiz", "Gutierrez", "Jimenez",
    "Vargas", "Castillo", "Ruiz", "Mendoza", "Alvarez", "Romero", "Herrera",
]
HISPANIC_FIRST_F = [
    "Maria", "Sofia", "Isabella", "Camila", "Valeria", "Lucia", "Daniela",
    "Gabriela", "Ana", "Adriana", "Carolina", "Natalia", "Andrea", "Paula",
    "Jimena", "Ximena", "Mariana", "Fernanda", "Alejandra", "Rosa",
]
HISPANIC_FIRST_M = [
    "Juan", "Carlos", "Luis", "Miguel", "Jose", "Diego", "Mateo", "Daniel",
    "Alejandro", "Andres", "Sebastian", "Santiago", "David", "Gabriel",
    "Javier", "Pablo", "Roberto", "Eduardo", "Fernando", "Ricardo",
]

# Generic surname pool (publicly common; no individuals referenced)
GENERIC_LAST = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Davis", "Miller",
    "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White",
    "Harris", "Martin", "Thompson", "Robinson", "Clark", "Lewis", "Walker",
    "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green", "Baker",
    "Adams", "Nelson", "Carter", "Mitchell", "Roberts", "Turner", "Phillips",
    "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Morris",
]
GENERIC_FIRST_F = [
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan",
    "Jessica", "Sarah", "Karen", "Nancy", "Lisa", "Margaret", "Betty",
    "Sandra", "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Carol",
    "Amanda", "Melissa", "Deborah", "Stephanie", "Rebecca", "Laura", "Sharon",
]
GENERIC_FIRST_M = [
    "James", "Robert", "John", "Michael", "William", "David", "Richard",
    "Joseph", "Thomas", "Charles", "Christopher", "Daniel", "Matthew",
    "Anthony", "Mark", "Donald", "Steven", "Andrew", "Paul", "Joshua",
    "Kenneth", "Kevin", "Brian", "George", "Edward", "Ronald", "Timothy",
    "Jason", "Jeffrey", "Ryan", "Jacob", "Gary",
]

# Black/African American surname pool — these surnames are shared widely
# across many groups but are common in Black communities; used here to give
# the synthetic file plausible name diversity.
BLACK_LAST = [
    "Williams", "Johnson", "Jones", "Brown", "Davis", "Jackson", "Harris",
    "Robinson", "Walker", "Wright", "Mitchell", "Carter", "Phillips",
    "Roberts", "Turner", "Washington", "Rivers", "Banks", "Bell", "Gibson",
]
BLACK_FIRST_F = [
    "Aaliyah", "Aniyah", "Imani", "Jada", "Zoe", "Nia", "Tiana", "Maya",
    "Kayla", "Layla", "Amara", "Sanaa", "Brianna", "Destiny", "Kiara",
]
BLACK_FIRST_M = [
    "Andre", "Darius", "DeShawn", "Elijah", "Isaiah", "Jamal", "Jaylen",
    "Khalil", "Malik", "Marcus", "Terrence", "Tyrone", "Xavier", "Devon",
]

# Asian/AAPI surname pool — broad mix to span Korean, Vietnamese, Chinese,
# Indian communities present in Gwinnett.
AAPI_LAST = [
    "Nguyen", "Tran", "Le", "Pham", "Patel", "Singh", "Kim", "Park", "Lee",
    "Choi", "Wang", "Chen", "Liu", "Zhang", "Yang", "Wu", "Shah", "Gupta",
]
AAPI_FIRST_F = [
    "Linh", "Anh", "Mai", "Priya", "Anika", "Aishwarya", "Min-jung", "Hye-jin",
    "Yuki", "Mei", "Wen", "Xin", "Aanya", "Diya",
]
AAPI_FIRST_M = [
    "Minh", "Nam", "Hieu", "Arjun", "Rohan", "Aditya", "Min-jun", "Tae-yang",
    "Hiroshi", "Wei", "Jian", "Kai", "Kabir", "Vihaan",
]

# Pinned random module to a seeded Random instance to avoid global state.
_rng: random.Random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def weighted_choice(pairs):
    """Pick a value from [(value, weight), ...]."""
    r = _rng.random()
    cum = 0.0
    for value, weight in pairs:
        cum += weight
        if r <= cum:
            return value
    return pairs[-1][0]


def random_choice_with_pool(race: str, gender: str):
    """Return (first_name, last_name) drawn from a culturally-aligned pool."""
    if race == "Hispanic/Latino":
        last = _rng.choice(HISPANIC_LAST)
        first = _rng.choice(HISPANIC_FIRST_F if gender == "F" else HISPANIC_FIRST_M)
    elif race == "Black/African American":
        last = _rng.choice(BLACK_LAST + GENERIC_LAST)
        first = _rng.choice(BLACK_FIRST_F if gender == "F" else BLACK_FIRST_M)
    elif race == "Asian/AAPI":
        last = _rng.choice(AAPI_LAST)
        first = _rng.choice(AAPI_FIRST_F if gender == "F" else AAPI_FIRST_M)
    else:
        last = _rng.choice(GENERIC_LAST)
        first = _rng.choice(GENERIC_FIRST_F if gender == "F" else GENERIC_FIRST_M)
    return first, last


def make_address(rng: random.Random) -> tuple[str, str, str]:
    num = rng.randint(100, 9999)
    street = f"{rng.choice(STREET_NAMES)} {rng.choice(STREET_TYPES)}"
    city, zipc = rng.choice(CITIES)
    return f"{num} {street}", city, zipc


def make_voter_id(idx: int) -> str:
    """TargetSmart-style voterbase_id: GA + zero-padded sequential."""
    return f"GA{idx:09d}"


def make_tsmart_key() -> str:
    """Random 12-char alphanumeric key; mirrors tsmart_key shape."""
    return "".join(_rng.choices(string.ascii_uppercase + string.digits, k=12))


def make_dob_for_age(age: int) -> date:
    today = date.today()
    year = today.year - age
    # random day in that year, avoiding Feb 29 edge case
    month = _rng.randint(1, 12)
    day = _rng.randint(1, 28)
    return date(year, month, day)


def make_registration_date(age: int, is_new: bool) -> date:
    today = date.today()
    if is_new:
        days_back = _rng.randint(30, 540)  # within last ~18 months
    else:
        max_years = max(1, age - 18)
        years_back = _rng.randint(1, min(max_years, 30))
        days_back = years_back * 365 + _rng.randint(0, 364)
    return today - timedelta(days=days_back)


def partisan_score_for(race: str, party: str) -> int:
    """
    Return a 0-100 partisan score (higher = more Democratic).

    Distributions are tuned for plausibility, not real-world accuracy.
    """
    base_means = {
        "Hispanic/Latino":         62,
        "Black/African American":  82,
        "Asian/AAPI":              60,
        "White":                   42,
        "Other":                   55,
    }
    mean = base_means.get(race, 50)
    if party == "Dem":
        mean = min(95, mean + 15)
    elif party == "Rep":
        mean = max(5, mean - 25)
    elif party == "NPA":
        mean = mean  # no shift
    return max(0, min(100, int(_rng.gauss(mean, 18))))


def turnout_score_for(age: int, vote_history_count: int) -> int:
    """
    Higher score = more likely to vote.
    Older + more past-cycle votes => higher score.
    """
    base = 30 + min(age, 75) * 0.6  # slow climb with age
    base += vote_history_count * 12  # each past cycle voted is a big lift
    return max(0, min(100, int(_rng.gauss(base, 10))))


def spanish_score_for(race: str) -> int:
    if race == "Hispanic/Latino":
        return max(0, min(100, int(_rng.gauss(72, 18))))
    return max(0, min(100, int(_rng.gauss(8, 10))))


def vote_history(age: int, turnout_propensity: float) -> dict:
    """
    Returns a dict with keys vote_history_2018/2020/2022/2024, values "TRUE"/"FALSE".

    Older + higher turnout_propensity => more TRUE values.
    """
    cycles = ["vote_history_2018", "vote_history_2020", "vote_history_2022", "vote_history_2024"]
    eligible_in_year = {
        "vote_history_2018": age >= 26,  # 18+ in 2018
        "vote_history_2020": age >= 24,
        "vote_history_2022": age >= 22,
        "vote_history_2024": age >= 20,
    }
    out = {}
    for c in cycles:
        if not eligible_in_year[c]:
            out[c] = "FALSE"
            continue
        # Higher propensity + higher cycle salience (presidential > midterm) => more TRUE
        salience = 0.92 if c in ("vote_history_2020", "vote_history_2024") else 0.65
        prob = min(0.97, turnout_propensity * salience)
        out[c] = "TRUE" if _rng.random() < prob else "FALSE"
    return out


def precinct_for_address(address: str, zipc: str) -> tuple[str, str]:
    """
    Map an address+ZIP to a deterministic precinct. Real Gwinnett uses ~156
    precincts; multiple precincts per ZIP and multiple ZIPs per precinct are
    both normal. We hash street+ZIP so the same address always lands in the
    same precinct (geographic stability) while neighboring streets in one ZIP
    can split across precincts (geographic realism).
    """
    import hashlib
    h = int(hashlib.md5(f"{address}|{zipc}".encode()).hexdigest()[:8], 16)
    # ZIP supplies a regional bias toward a cluster of prefixes (mirrors
    # real-world adjacency), then the address hash picks within. Suffix range
    # is capped so total unique precincts lands ~150-180, near real Gwinnett.
    zip_seed = int(zipc[-3:]) if zipc[-3:].isdigit() else 0
    # Use a non-contiguous slice of prefixes per ZIP for better spread
    prefix_pool = [
        PRECINCT_PREFIXES[(zip_seed * 5 + offset * 3) % len(PRECINCT_PREFIXES)]
        for offset in range(5)  # ZIP biases toward 5 prefixes spread across list
    ]
    prefix = prefix_pool[h % len(prefix_pool)]
    suffix = (h // 5) % 11 + 1  # 1..11 → ~17 prefixes × 11 suffixes ≈ 187 max
    code = f"{prefix}{suffix:02d}"
    name = f"{prefix.capitalize()} {suffix:02d}"
    return code, name


# Backwards-compat shim in case anything else imports the old name
def precinct_for_zip(zipc: str) -> tuple[str, str]:
    return precinct_for_address("", zipc)


# ---------------------------------------------------------------------------
# Row generation
# ---------------------------------------------------------------------------

def generate_row(idx: int) -> dict:
    """Return one TargetSmart-shaped voter record."""
    race = weighted_choice(RACE_DISTRIBUTION)
    gender = weighted_choice(GENDER_DISTRIBUTION)
    party = weighted_choice(PARTY_DISTRIBUTION)

    # Tilt Hispanic and AAPI cohorts younger (matches real Gwinnett demographics)
    if race == "Hispanic/Latino":
        age = max(18, min(85, int(_rng.gauss(34, 12))))
    elif race == "Asian/AAPI":
        age = max(18, min(85, int(_rng.gauss(38, 14))))
    elif race == "Black/African American":
        age = max(18, min(90, int(_rng.gauss(42, 16))))
    else:
        age = max(18, min(95, int(_rng.gauss(48, 17))))

    # ~9% of Hispanic/Latino voters in our file are NEW REGISTRANTS in last 18mo
    # (so the demo has a juicy "new registrant outreach" segment)
    is_new = (race == "Hispanic/Latino" and _rng.random() < 0.18) \
             or (_rng.random() < 0.05)

    first_name, last_name = random_choice_with_pool(race, gender)
    dob = make_dob_for_age(age)
    reg_date = make_registration_date(age, is_new)
    address, city, zipc = make_address(_rng)
    precinct_code, precinct_name = precinct_for_address(address, zipc)

    p_score = partisan_score_for(race, party)
    s_score = spanish_score_for(race)

    # Vote history needs a propensity estimate; bootstrap from age
    boot_propensity = 0.3 + min(age, 70) * 0.008
    vh = vote_history(age, boot_propensity)
    vh_count = sum(1 for v in vh.values() if v == "TRUE")
    t_score = turnout_score_for(age, vh_count)

    # Suppress scores entirely for new registrants (matches TargetSmart behavior)
    if is_new:
        p_score_field: str = ""
        t_score_field: str = ""
    else:
        p_score_field = str(p_score)
        t_score_field = str(t_score)

    return {
        "voterbase_id":                       make_voter_id(idx),
        "tsmart_key":                         make_tsmart_key(),
        "tsmart_first_name":                  first_name,
        "tsmart_last_name":                   last_name,
        "address":                            address,
        "res_city":                           city,
        "res_state":                          STATE,
        "zip":                                zipc,
        "county":                             COUNTY,
        "precinct_code":                      precinct_code,
        "precinct_name":                      precinct_name,
        "congressional_district":             "GA-07",  # Gwinnett ~ GA-07
        "state_senate_district":              str(_rng.choice([5, 9, 40, 41, 45, 48, 55])),
        "state_house_district":               str(_rng.choice(list(range(95, 110)) + list(range(95, 110)))),
        "voterbase_age":                      str(age),
        "dob":                                dob.isoformat(),
        "voterbase_gender":                   gender,
        "tsmart_race":                        race,
        "party_registration":                 party,
        "tsmart_partisan_score":              p_score_field,
        "tsmart_vote_propensity":             t_score_field,
        "tsmart_spanish_language_score":      str(s_score),
        "registration_date":                  reg_date.isoformat(),
        "vote_history_2018":                  vh["vote_history_2018"],
        "vote_history_2020":                  vh["vote_history_2020"],
        "vote_history_2022":                  vh["vote_history_2022"],
        "vote_history_2024":                  vh["vote_history_2024"],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COLUMN_ORDER = [
    "voterbase_id", "tsmart_key", "tsmart_first_name", "tsmart_last_name",
    "address", "res_city", "res_state", "zip", "county",
    "precinct_code", "precinct_name",
    "congressional_district", "state_senate_district", "state_house_district",
    "voterbase_age", "dob", "voterbase_gender", "tsmart_race",
    "party_registration",
    "tsmart_partisan_score", "tsmart_vote_propensity", "tsmart_spanish_language_score",
    "registration_date",
    "vote_history_2018", "vote_history_2020", "vote_history_2022", "vote_history_2024",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="data/demo/gwinnett_demo_voterfile.csv",
        help="Output CSV path (default: data/demo/gwinnett_demo_voterfile.csv)",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=50_000,
        help="Number of voter records to generate (default: 50000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260427,
        help="Random seed for deterministic output (default: 20260427)",
    )
    args = parser.parse_args()

    global _rng
    _rng = random.Random(args.seed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.rows:,} synthetic Gwinnett County, GA voter records")
    print(f"  seed: {args.seed}")
    print(f"  out:  {out_path}")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMN_ORDER)
        writer.writeheader()
        for i in range(1, args.rows + 1):
            writer.writerow(generate_row(i))
            if i % 10_000 == 0:
                print(f"  ... {i:,} rows")

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Done. Wrote {args.rows:,} rows ({size_mb:.1f} MB) to {out_path}")
    print()
    print("Verify with:")
    print(f"  head -2 {out_path}")
    print(f"  wc -l {out_path}")


if __name__ == "__main__":
    main()
