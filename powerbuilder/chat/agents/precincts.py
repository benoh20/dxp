# powerbuilder/chat/agents/precincts.py
import logging
import os
import re
from typing import List

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import requests
from langchain_openai import ChatOpenAI

from ..utils.census_vars import VOTER_DEMOGRAPHICS, MULTI_VAR_METRICS, TRACT_ONLY_METRICS
from ..utils.data_fetcher import DataFetcher
from ..utils.district_standardizer import GeographyStandardizer, normalize_district
from ..utils.storage import file_exists, read_dataframe
from .state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demographic targeting configuration
# ---------------------------------------------------------------------------

# Maps AgentState.demographic_intent → primary metrics passed to get_top_precincts().
_DEMOGRAPHIC_METRICS: dict[str, list[str]] = {
    "youth":         ["youth_vap", "college_enrolled"],
    "hispanic":      ["hispanic_pop"],
    "black":         ["black_pop"],
    "aapi":          ["aapi"],
    "native":        ["native_pop"],
    "senior":        ["senior_vap"],
    "educated":      ["graduate_educated"],
    "working_class": ["no_hs_diploma", "some_college"],
    "low_income":    ["poverty_pop"],
    "high_income":   ["median_income"],
    "immigrant":     ["foreign_born_pop"],
    "veteran":       ["veteran_pop"],
    "suburban":      ["owner_pop"],
    "renter":        ["renter_pop"],
    "default":       ["total_vap"],
}

# Human-readable explanation written into structured_data["demographic_profile"].
_DEMOGRAPHIC_PROFILES: dict[str, str] = {
    "youth": (
        "Targeting precincts with high concentrations of voters aged 18-29 and college "
        "enrollment. youth_vap sums B01001_007-011E and B01001_031-035E (18-29 male and "
        "female); college_enrolled uses B14001_005E."
    ),
    "hispanic": (
        "Targeting precincts with high Hispanic/Latino population concentrations "
        "(B03003_003E). Note: total population, not CVAP — citizenship rates vary."
    ),
    "black": (
        "Targeting precincts with high Black/African American population concentrations "
        "(B02001_003E). Note: total population, not CVAP."
    ),
    "aapi": (
        "Targeting precincts with high Asian American and Pacific Islander population "
        "concentrations. Combines Asian alone (B02001_005E) and Native Hawaiian/Pacific "
        "Islander alone (B02001_006E)."
    ),
    "native": (
        "Targeting precincts with high American Indian and Alaska Native population "
        "concentrations (B02001_004E). Note: total population, not CVAP."
    ),
    "senior": (
        "Targeting precincts with high concentrations of voters aged 65 and older. "
        "senior_vap sums B01001_020-025E (male 65+) and B01001_044-049E (female 65+)."
    ),
    "educated": (
        "Targeting precincts with high concentrations of college and graduate degree holders. "
        "graduate_educated combines bachelor's (B15003_022E) with master's, professional, "
        "and doctoral degrees (B15003_023-025E). Uses tract-level data — less granular than "
        "block-group targeting."
    ),
    "working_class": (
        "Targeting precincts with high concentrations of working-class voters without "
        "four-year degrees. no_hs_diploma sums B15003_002-016E; some_college sums "
        "B15003_019-021E. Both use tract-level data — less granular than block-group targeting."
    ),
    "low_income": (
        "Targeting precincts with high concentrations of low-income households "
        "(B17001_002E — households below the federal poverty line)."
    ),
    "high_income": (
        "Targeting precincts with high median household income (B19013_001E) — "
        "for donor prospecting and persuasion targeting in affluent areas."
    ),
    "immigrant": (
        "Targeting precincts with high concentrations of foreign-born and naturalized "
        "citizen populations (B05002_013E — foreign-born). Note: not all foreign-born "
        "residents are eligible voters."
    ),
    "veteran": (
        "Targeting precincts with high concentrations of veteran and military-connected "
        "voters (B21001_002E — civilian veterans 18+)."
    ),
    "suburban": (
        "Targeting precincts with high homeownership rates (B25003_002E — owner-occupied "
        "housing units) as a proxy for suburban and exurban voter populations."
    ),
    "renter": (
        "Targeting precincts with high renter-occupied housing (B25003_003E) — proxy for "
        "urban and transient populations, including young voters and recent movers."
    ),
    "default": (
        "No demographic targeting specified. Ranking precincts by total voting-age population "
        "(VAP from 2020 Decennial PL94-171) — the broadest measure of the resident voter universe."
    ),
}

# ---------------------------------------------------------------------------
# County FIPS → county name lookup for all counties in crosswalk-covered states.
# Keys are 5-digit strings (state_fips_2 + county_fips_3), e.g. "04013" = Maricopa, AZ.
# Virginia independent cities are stored with " City" suffix so _format_precinct_label
# can omit the "Co." abbreviation for those entries.
# ---------------------------------------------------------------------------
_COUNTY_NAMES: dict[str, str] = {
    # === Arizona (04) — 15 counties ===
    "04001": "Apache",      "04003": "Cochise",     "04005": "Coconino",
    "04007": "Gila",        "04009": "Graham",      "04011": "Greenlee",
    "04012": "La Paz",      "04013": "Maricopa",    "04015": "Mohave",
    "04017": "Navajo",      "04019": "Pima",        "04021": "Pinal",
    "04023": "Santa Cruz",  "04025": "Yavapai",     "04027": "Yuma",

    # === Nevada (32) — 16 counties + 1 independent city ===
    "32001": "Churchill",   "32003": "Clark",       "32005": "Douglas",
    "32007": "Elko",        "32009": "Esmeralda",   "32011": "Eureka",
    "32013": "Humboldt",    "32015": "Lander",      "32017": "Lincoln",
    "32019": "Lyon",        "32021": "Mineral",     "32023": "Nye",
    "32027": "Pershing",    "32029": "Storey",      "32031": "Washoe",
    "32033": "White Pine",  "32510": "Carson City",

    # === Michigan (26) — 83 counties ===
    "26001": "Alcona",      "26003": "Alger",       "26005": "Allegan",
    "26007": "Alpena",      "26009": "Antrim",      "26011": "Arenac",
    "26013": "Baraga",      "26015": "Barry",       "26017": "Bay",
    "26019": "Benzie",      "26021": "Berrien",     "26023": "Branch",
    "26025": "Calhoun",     "26027": "Cass",        "26029": "Charlevoix",
    "26031": "Cheboygan",   "26033": "Chippewa",    "26035": "Clare",
    "26037": "Clinton",     "26039": "Crawford",    "26041": "Delta",
    "26043": "Dickinson",   "26045": "Eaton",       "26047": "Emmet",
    "26049": "Genesee",     "26051": "Gladwin",     "26053": "Gogebic",
    "26055": "Grand Traverse", "26057": "Gratiot",  "26059": "Hillsdale",
    "26061": "Houghton",    "26063": "Huron",       "26065": "Ingham",
    "26067": "Ionia",       "26069": "Iosco",       "26071": "Iron",
    "26073": "Isabella",    "26075": "Jackson",     "26077": "Kalamazoo",
    "26079": "Kalkaska",    "26081": "Kent",        "26083": "Keweenaw",
    "26085": "Lake",        "26087": "Lapeer",      "26089": "Leelanau",
    "26091": "Lenawee",     "26093": "Livingston",  "26095": "Luce",
    "26097": "Mackinac",    "26099": "Macomb",      "26101": "Manistee",
    "26103": "Marquette",   "26105": "Mason",       "26107": "Mecosta",
    "26109": "Menominee",   "26111": "Midland",     "26113": "Missaukee",
    "26115": "Monroe",      "26117": "Montcalm",    "26119": "Montmorency",
    "26121": "Muskegon",    "26123": "Newaygo",     "26125": "Oakland",
    "26127": "Oceana",      "26129": "Ogemaw",      "26131": "Ontonagon",
    "26133": "Osceola",     "26135": "Oscoda",      "26137": "Otsego",
    "26139": "Ottawa",      "26141": "Presque Isle", "26143": "Roscommon",
    "26145": "Saginaw",     "26147": "St. Clair",   "26149": "St. Joseph",
    "26151": "Sanilac",     "26153": "Schoolcraft", "26155": "Shiawassee",
    "26157": "Tuscola",     "26159": "Van Buren",   "26161": "Washtenaw",
    "26163": "Wayne",       "26165": "Wexford",

    # === Ohio (39) — 88 counties ===
    "39001": "Adams",       "39003": "Allen",       "39005": "Ashland",
    "39007": "Ashtabula",   "39009": "Athens",      "39011": "Auglaize",
    "39013": "Belmont",     "39015": "Brown",       "39017": "Butler",
    "39019": "Carroll",     "39021": "Champaign",   "39023": "Clark",
    "39025": "Clermont",    "39027": "Clinton",     "39029": "Columbiana",
    "39031": "Coshocton",   "39033": "Crawford",    "39035": "Cuyahoga",
    "39037": "Darke",       "39039": "Defiance",    "39041": "Delaware",
    "39043": "Erie",        "39045": "Fairfield",   "39047": "Fayette",
    "39049": "Franklin",    "39051": "Fulton",      "39053": "Gallia",
    "39055": "Geauga",      "39057": "Greene",      "39059": "Guernsey",
    "39061": "Hamilton",    "39063": "Hancock",     "39065": "Hardin",
    "39067": "Harrison",    "39069": "Henry",       "39071": "Highland",
    "39073": "Hocking",     "39075": "Holmes",      "39077": "Huron",
    "39079": "Jackson",     "39081": "Jefferson",   "39083": "Knox",
    "39085": "Lake",        "39087": "Lawrence",    "39089": "Licking",
    "39091": "Logan",       "39093": "Lorain",      "39095": "Lucas",
    "39097": "Madison",     "39099": "Mahoning",    "39101": "Marion",
    "39103": "Medina",      "39105": "Meigs",       "39107": "Mercer",
    "39109": "Miami",       "39111": "Monroe",      "39113": "Montgomery",
    "39115": "Morgan",      "39117": "Morrow",      "39119": "Muskingum",
    "39121": "Noble",       "39123": "Ottawa",      "39125": "Paulding",
    "39127": "Perry",       "39129": "Pickaway",    "39131": "Pike",
    "39133": "Portage",     "39135": "Preble",      "39137": "Putnam",
    "39139": "Richland",    "39141": "Ross",        "39143": "Sandusky",
    "39145": "Scioto",      "39147": "Seneca",      "39149": "Shelby",
    "39151": "Stark",       "39153": "Summit",      "39155": "Trumbull",
    "39157": "Tuscarawas",  "39159": "Union",       "39161": "Van Wert",
    "39163": "Vinton",      "39165": "Warren",      "39167": "Washington",
    "39169": "Wayne",       "39171": "Williams",    "39173": "Wood",
    "39175": "Wyandot",

    # === New Hampshire (33) — 10 counties ===
    "33001": "Belknap",     "33003": "Carroll",     "33005": "Cheshire",
    "33007": "Coos",        "33009": "Grafton",     "33011": "Hillsborough",
    "33013": "Merrimack",   "33015": "Rockingham",  "33017": "Strafford",
    "33019": "Sullivan",

    # === Pennsylvania (42) — 67 counties ===
    "42001": "Adams",       "42003": "Allegheny",   "42005": "Armstrong",
    "42007": "Beaver",      "42009": "Bedford",     "42011": "Berks",
    "42013": "Blair",       "42015": "Bradford",    "42017": "Bucks",
    "42019": "Butler",      "42021": "Cambria",     "42023": "Cameron",
    "42025": "Carbon",      "42027": "Centre",      "42029": "Chester",
    "42031": "Clarion",     "42033": "Clearfield",  "42035": "Clinton",
    "42037": "Columbia",    "42039": "Crawford",    "42041": "Cumberland",
    "42043": "Dauphin",     "42045": "Delaware",    "42047": "Elk",
    "42049": "Erie",        "42051": "Fayette",     "42053": "Forest",
    "42055": "Franklin",    "42057": "Fulton",      "42059": "Greene",
    "42061": "Huntingdon",  "42063": "Indiana",     "42065": "Jefferson",
    "42067": "Juniata",     "42069": "Lackawanna",  "42071": "Lancaster",
    "42073": "Lawrence",    "42075": "Lebanon",     "42077": "Lehigh",
    "42079": "Luzerne",     "42081": "Lycoming",    "42083": "McKean",
    "42085": "Mercer",      "42087": "Mifflin",     "42089": "Monroe",
    "42091": "Montgomery",  "42093": "Montour",     "42095": "Northampton",
    "42097": "Northumberland", "42099": "Perry",    "42101": "Philadelphia",
    "42103": "Pike",        "42105": "Potter",      "42107": "Schuylkill",
    "42109": "Snyder",      "42111": "Somerset",    "42113": "Sullivan",
    "42115": "Susquehanna", "42117": "Tioga",       "42119": "Union",
    "42121": "Venango",     "42123": "Warren",      "42125": "Washington",
    "42127": "Wayne",       "42129": "Westmoreland", "42131": "Wyoming",
    "42133": "York",

    # === Colorado (08) — 64 counties ===
    "08001": "Adams",       "08003": "Alamosa",     "08005": "Arapahoe",
    "08007": "Archuleta",   "08009": "Baca",        "08011": "Bent",
    "08013": "Boulder",     "08014": "Broomfield",  "08015": "Chaffee",
    "08017": "Cheyenne",    "08019": "Clear Creek",  "08021": "Conejos",
    "08023": "Costilla",    "08025": "Crowley",     "08027": "Custer",
    "08029": "Delta",       "08031": "Denver",      "08033": "Dolores",
    "08035": "Douglas",     "08037": "Eagle",       "08039": "Elbert",
    "08041": "El Paso",     "08043": "Fremont",     "08045": "Garfield",
    "08047": "Gilpin",      "08049": "Grand",       "08051": "Gunnison",
    "08053": "Hinsdale",    "08055": "Huerfano",    "08057": "Jackson",
    "08059": "Jefferson",   "08061": "Kiowa",       "08063": "Kit Carson",
    "08065": "Lake",        "08067": "La Plata",    "08069": "Larimer",
    "08071": "Las Animas",  "08073": "Lincoln",     "08075": "Logan",
    "08077": "Mesa",        "08079": "Mineral",     "08081": "Moffat",
    "08083": "Montezuma",   "08085": "Montrose",    "08087": "Morgan",
    "08089": "Otero",       "08091": "Ouray",       "08093": "Park",
    "08095": "Phillips",    "08097": "Pitkin",      "08099": "Prowers",
    "08101": "Pueblo",      "08103": "Rio Blanco",  "08105": "Rio Grande",
    "08107": "Routt",       "08109": "Saguache",    "08111": "San Juan",
    "08113": "San Miguel",  "08115": "Sedgwick",    "08117": "Summit",
    "08119": "Teller",      "08121": "Washington",  "08123": "Weld",
    "08125": "Yuma",

    # === Wisconsin (55) — 72 counties ===
    "55001": "Adams",       "55003": "Ashland",     "55005": "Barron",
    "55007": "Bayfield",    "55009": "Brown",       "55011": "Buffalo",
    "55013": "Burnett",     "55015": "Calumet",     "55017": "Chippewa",
    "55019": "Clark",       "55021": "Columbia",    "55023": "Crawford",
    "55025": "Dane",        "55027": "Dodge",       "55029": "Door",
    "55031": "Douglas",     "55033": "Dunn",        "55035": "Eau Claire",
    "55037": "Florence",    "55039": "Fond du Lac", "55041": "Forest",
    "55043": "Grant",       "55045": "Green",       "55047": "Green Lake",
    "55049": "Iowa",        "55051": "Iron",        "55053": "Jackson",
    "55055": "Jefferson",   "55057": "Juneau",      "55059": "Kenosha",
    "55061": "Kewaunee",    "55063": "La Crosse",   "55065": "Lafayette",
    "55067": "Langlade",    "55069": "Lincoln",     "55071": "Manitowoc",
    "55073": "Marathon",    "55075": "Marinette",   "55077": "Marquette",
    "55078": "Menominee",   "55079": "Milwaukee",   "55081": "Monroe",
    "55083": "Oconto",      "55085": "Oneida",      "55087": "Outagamie",
    "55089": "Ozaukee",     "55091": "Pepin",       "55093": "Pierce",
    "55095": "Polk",        "55097": "Portage",     "55099": "Price",
    "55101": "Racine",      "55103": "Richland",    "55105": "Rock",
    "55107": "Rusk",        "55109": "St. Croix",   "55111": "Sauk",
    "55113": "Sawyer",      "55115": "Shawano",     "55117": "Sheboygan",
    "55119": "Taylor",      "55121": "Trempealeau", "55123": "Vernon",
    "55125": "Vilas",       "55127": "Walworth",    "55129": "Washburn",
    "55131": "Washington",  "55133": "Waukesha",    "55135": "Waupaca",
    "55137": "Waushara",    "55139": "Winnebago",   "55141": "Wood",

    # === Virginia (51) — 95 counties + 39 independent cities ===
    # Counties
    "51001": "Accomack",    "51003": "Albemarle",   "51005": "Alleghany",
    "51007": "Amelia",      "51009": "Amherst",     "51011": "Appomattox",
    "51013": "Arlington",   "51015": "Augusta",     "51017": "Bath",
    "51019": "Bedford",     "51021": "Bland",       "51023": "Botetourt",
    "51025": "Brunswick",   "51027": "Buchanan",    "51029": "Buckingham",
    "51031": "Campbell",    "51033": "Caroline",    "51035": "Carroll",
    "51037": "Charles City", "51039": "Charlotte",  "51041": "Chesterfield",
    "51043": "Clarke",      "51045": "Craig",       "51047": "Culpeper",
    "51049": "Cumberland",  "51051": "Dickenson",   "51053": "Dinwiddie",
    "51057": "Essex",       "51059": "Fairfax",     "51061": "Fauquier",
    "51063": "Floyd",       "51065": "Fluvanna",    "51067": "Franklin",
    "51069": "Frederick",   "51071": "Giles",       "51073": "Gloucester",
    "51075": "Goochland",   "51077": "Grayson",     "51079": "Greene",
    "51081": "Greensville", "51083": "Halifax",     "51085": "Hanover",
    "51087": "Henrico",     "51089": "Henry",       "51091": "Highland",
    "51093": "Isle of Wight", "51095": "James City", "51097": "King and Queen",
    "51099": "King George", "51101": "King William", "51103": "Lancaster",
    "51105": "Lee",         "51107": "Loudoun",     "51109": "Louisa",
    "51111": "Lunenburg",   "51113": "Madison",     "51115": "Mathews",
    "51117": "Mecklenburg", "51119": "Middlesex",   "51121": "Montgomery",
    "51125": "Nelson",      "51127": "New Kent",    "51131": "Northampton",
    "51133": "Northumberland", "51135": "Nottoway", "51137": "Orange",
    "51139": "Page",        "51141": "Patrick",     "51143": "Pittsylvania",
    "51145": "Powhatan",    "51147": "Prince Edward", "51149": "Prince George",
    "51153": "Prince William", "51155": "Pulaski",  "51157": "Rappahannock",
    "51159": "Richmond",    "51161": "Roanoke",     "51163": "Rockbridge",
    "51165": "Rockingham",  "51167": "Russell",     "51169": "Scott",
    "51171": "Shenandoah",  "51173": "Smyth",       "51175": "Southampton",
    "51177": "Spotsylvania", "51179": "Stafford",   "51181": "Surry",
    "51183": "Sussex",      "51185": "Tazewell",    "51187": "Warren",
    "51191": "Washington",  "51193": "Westmoreland", "51195": "Wise",
    "51197": "Wythe",       "51199": "York",
    # Independent cities (suffix " City" triggers omission of "Co." in label)
    "51510": "Alexandria City",      "51515": "Bedford City",
    "51520": "Bristol City",         "51530": "Buena Vista City",
    "51540": "Charlottesville City", "51550": "Chesapeake City",
    "51560": "Colonial Heights City", "51570": "Covington City",
    "51580": "Danville City",        "51590": "Emporia City",
    "51595": "Fairfax City",         "51600": "Falls Church City",
    "51610": "Franklin City",        "51620": "Fredericksburg City",
    "51630": "Galax City",           "51640": "Hampton City",
    "51650": "Harrisonburg City",    "51660": "Hopewell City",
    "51670": "Lexington City",       "51678": "Lynchburg City",
    "51683": "Manassas City",        "51685": "Manassas Park City",
    "51690": "Martinsville City",    "51700": "Newport News City",
    "51710": "Norfolk City",         "51720": "Norton City",
    "51730": "Petersburg City",      "51735": "Poquoson City",
    "51740": "Portsmouth City",      "51750": "Radford City",
    "51760": "Richmond City",        "51770": "Roanoke City",
    "51775": "Salem City",           "51790": "Staunton City",
    "51800": "Suffolk City",         "51810": "Virginia Beach City",
    "51820": "Waynesboro City",      "51830": "Williamsburg City",
    "51840": "Winchester City",

    # === Rhode Island (44) — 5 counties ===
    "44001": "Bristol",     "44003": "Kent",        "44005": "Newport",
    "44007": "Providence",  "44009": "Washington",

    # === Georgia (13) — 159 counties ===
    "13001": "Appling",     "13003": "Atkinson",    "13005": "Bacon",
    "13007": "Baker",       "13009": "Baldwin",     "13011": "Banks",
    "13013": "Barrow",      "13015": "Bartow",      "13017": "Ben Hill",
    "13019": "Berrien",     "13021": "Bibb",        "13023": "Bleckley",
    "13025": "Brantley",    "13027": "Brooks",      "13029": "Bryan",
    "13031": "Bulloch",     "13033": "Burke",       "13035": "Butts",
    "13037": "Calhoun",     "13039": "Camden",      "13043": "Candler",
    "13045": "Carroll",     "13047": "Catoosa",     "13049": "Charlton",
    "13051": "Chatham",     "13053": "Chattahoochee", "13055": "Chattooga",
    "13057": "Cherokee",    "13059": "Clarke",      "13061": "Clay",
    "13063": "Clayton",     "13065": "Clinch",      "13067": "Cobb",
    "13069": "Coffee",      "13071": "Colquitt",    "13073": "Columbia",
    "13075": "Cook",        "13077": "Coweta",      "13079": "Crawford",
    "13081": "Crisp",       "13083": "Dade",        "13085": "Dawson",
    "13087": "Decatur",     "13089": "DeKalb",      "13091": "Dodge",
    "13093": "Dooly",       "13095": "Dougherty",   "13097": "Douglas",
    "13099": "Early",       "13101": "Echols",      "13103": "Effingham",
    "13105": "Elbert",      "13107": "Emanuel",     "13109": "Evans",
    "13111": "Fannin",      "13113": "Fayette",     "13115": "Floyd",
    "13117": "Forsyth",     "13119": "Franklin",    "13121": "Fulton",
    "13123": "Gilmer",      "13125": "Glascock",    "13127": "Glynn",
    "13129": "Gordon",      "13131": "Grady",       "13133": "Greene",
    "13135": "Gwinnett",    "13137": "Habersham",   "13139": "Hall",
    "13141": "Hancock",     "13143": "Haralson",    "13145": "Harris",
    "13147": "Hart",        "13149": "Heard",       "13151": "Henry",
    "13153": "Houston",     "13155": "Irwin",       "13157": "Jackson",
    "13159": "Jasper",      "13161": "Jeff Davis",  "13163": "Jefferson",
    "13165": "Jenkins",     "13167": "Johnson",     "13169": "Jones",
    "13171": "Lamar",       "13173": "Lanier",      "13175": "Laurens",
    "13177": "Lee",         "13179": "Liberty",     "13181": "Lincoln",
    "13183": "Long",        "13185": "Lowndes",     "13187": "Lumpkin",
    "13189": "McDuffie",    "13191": "McIntosh",    "13193": "Macon",
    "13195": "Madison",     "13197": "Marion",      "13199": "Meriwether",
    "13201": "Miller",      "13205": "Mitchell",    "13207": "Monroe",
    "13209": "Montgomery",  "13211": "Morgan",      "13213": "Murray",
    "13215": "Muscogee",    "13217": "Newton",      "13219": "Oconee",
    "13221": "Oglethorpe",  "13223": "Paulding",    "13225": "Peach",
    "13227": "Pickens",     "13229": "Pierce",      "13231": "Pike",
    "13233": "Polk",        "13235": "Pulaski",     "13237": "Putnam",
    "13239": "Quitman",     "13241": "Rabun",       "13243": "Randolph",
    "13245": "Richmond",    "13247": "Rockdale",    "13249": "Schley",
    "13251": "Screven",     "13253": "Seminole",    "13255": "Spalding",
    "13257": "Stephens",    "13259": "Stewart",     "13261": "Sumter",
    "13263": "Talbot",      "13265": "Taliaferro",  "13267": "Tattnall",
    "13269": "Taylor",      "13271": "Telfair",     "13273": "Terrell",
    "13275": "Thomas",      "13277": "Tift",        "13279": "Toombs",
    "13281": "Towns",       "13283": "Treutlen",    "13285": "Troup",
    "13287": "Turner",      "13289": "Twiggs",      "13291": "Union",
    "13293": "Upson",       "13295": "Walker",      "13297": "Walton",
    "13299": "Ware",        "13301": "Warren",      "13303": "Washington",
    "13305": "Wayne",       "13307": "Webster",     "13309": "Wheeler",
    "13311": "White",       "13313": "Whitfield",   "13315": "Wilcox",
    "13317": "Wilkes",      "13319": "Wilkinson",   "13321": "Worth",
}


def _format_precinct_label(precinct_id: str) -> str:
    """Convert a bare precinct GEOID to a human-readable label.

    Expected format: '{state_fips_2}{county_fips_3}-{precinct_num}',
    e.g. '04013-0206' → 'Maricopa Co. Precinct 206'.
    Virginia independent cities omit 'Co.': '51640-005' → 'Hampton City Precinct 5'.
    Falls back to 'County {county_fips[2:]} Precinct {num}' for unlisted counties.
    """
    m = re.match(r"^(\d{5})-(.+)$", precinct_id)
    if not m:
        # Not the expected format — strip any embedded name and return as-is.
        parts = precinct_id.split(" ", 1)
        return parts[1].strip() if len(parts) > 1 else precinct_id
    county_fips, raw_num = m.group(1), m.group(2)
    precinct_num = str(int(raw_num)).zfill(3) if raw_num.isdigit() else raw_num
    county = _COUNTY_NAMES.get(county_fips)
    if county:
        # Independent cities already carry "City" in the name; skip "Co." suffix.
        if county.endswith(" City"):
            return f"{county} Precinct {precinct_num}"
        return f"{county} Co. Precinct {precinct_num}"
    return f"County {county_fips[2:]} Precinct {precinct_num}"


class PrecinctsAgent:
    """
    The Spatial Architect: Maps Census demographics onto Voting Precincts
    using dasymetric reaggregation (weighting).

    Crosswalk files (built by crosswalk_builder.py) map Census block groups to
    precinct boundaries with areal interpolation weights. This agent fetches
    block-group-level Census data, applies those weights, and reaggregates to
    the precinct level.
    """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_district_bg_geoids(
        state_fips: str, district_id: str, district_type: str
    ) -> set:
        """
        Returns the set of 12-character block group GEOIDs that fall within
        the target district, using the Census API nested geography predicate.

        Congressional districts are intentionally excluded from this Census API
        call. The ACS5 API only resolves block groups within the standard
        geographic hierarchy (state → county → tract → block group); congressional
        districts are not part of that hierarchy, so passing
        `in=state:XX congressional district:XX` with `for=block group:*` returns
        a 400 error. For congressional districts, district filtering happens
        spatially via the crosswalk file (built by crosswalk_builder.py) — either
        the district-specific crosswalk already scopes to the correct BGs, or the
        full-state crosswalk is intersected with precinct boundaries that lie within
        the district. This function returns an empty set for congressional so the
        caller falls through to that crosswalk-based path.

        Returns an empty set on failure so the caller can proceed without
        district filtering rather than crashing.
        """
        # The Census API does not support congressional district as a parent geography
        # for block groups. Return early and let the crosswalk handle district scoping.
        if district_type == "congressional":
            return set()

        if district_type == "state_senate":
            dist_num = district_id[len(state_fips) + 1:]      # strip "S" prefix
            in_pred = f"state:{state_fips} state legislative district (upper chamber):{dist_num}"
        elif district_type == "state_house":
            dist_num = district_id[len(state_fips) + 1:]      # strip "H" prefix
            in_pred = f"state:{state_fips} state legislative district (lower chamber):{dist_num}"
        else:
            logger.warning(f"Unrecognised district_type '{district_type}'; skipping district filter.")
            return set()

        try:
            response = requests.get(
                "https://api.census.gov/data/2022/acs/acs5",
                params={
                    "get": "NAME",
                    "for": "block group:*",
                    "in": in_pred,
                    "key": os.getenv("CENSUS_API_KEY"),
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            headers = data[0]
            geoids = set()
            for row in data[1:]:
                r = dict(zip(headers, row))
                # Reconstruct the 12-char GEOID: state(2)+county(3)+tract(6)+bg(1)
                geoid = (
                    r.get("state", "").zfill(2)
                    + r.get("county", "").zfill(3)
                    + r.get("tract", "").zfill(6)
                    + r.get("block group", "")
                )
                geoids.add(geoid)
            logger.info(f"  District {district_id}: {len(geoids)} block groups in scope.")
            return geoids
        except Exception as e:
            logger.warning(
                f"  Could not fetch BG list for district {district_id}: {e}. "
                "Proceeding without district filter."
            )
            return set()

    @staticmethod
    def _parse_precinct_name(precinct_geoid: str) -> str:
        """Extract a human-readable name from a full precinct GEOID string.

        When the GEOID encodes an embedded name ('01001-10 JONES COMM_ CTR_'),
        that name is returned directly. When there is no embedded name (bare
        GEOID like '04013-0206'), falls back to county FIPS lookup via
        _format_precinct_label to produce 'Maricopa Co. Precinct 206'.
        """
        parts = precinct_geoid.split(" ", 1)
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip()
        return _format_precinct_label(parts[0])

    @staticmethod
    def _compute_tract_education_weights(
        state_fips: str,
        edu_metrics: list,
        crosswalk: "pd.DataFrame",
    ) -> "pd.DataFrame | None":
        """
        Fetches B15003 education variables at Census tract level (ACS5 block-group
        limitation) and derives tract→precinct weights by summing the existing
        bg→precinct crosswalk weights up to the tract level.

        Returns a DataFrame indexed by precinct_geoid with weighted_<metric> columns,
        or None on failure. Core dasymetric logic is not used here — this is a
        simplified areal-weight approach applied at tract granularity.
        """
        # Expand multi-var education metrics into component friendly names
        component_names: list = []
        for m in edu_metrics:
            if m in MULTI_VAR_METRICS:
                for c in MULTI_VAR_METRICS[m]:
                    if c not in component_names:
                        component_names.append(c)
            elif m not in component_names:
                component_names.append(m)

        # Resolve component friendly names to Census codes (deduplicated)
        comp_to_code = {c: VOTER_DEMOGRAPHICS.get(c, c) for c in component_names}
        census_codes = list(dict.fromkeys(comp_to_code.values()))

        if not census_codes:
            return None

        try:
            response = requests.get(
                "https://api.census.gov/data/2022/acs/acs5",
                params={
                    "get": f"NAME,{','.join(census_codes)}",
                    "for": "tract:*",
                    "in":  f"state:{state_fips}",
                    "key": os.getenv("CENSUS_API_KEY"),
                },
                timeout=45,
            )
            response.raise_for_status()
            data    = response.json()
            headers = data[0]
            tract_df = pd.DataFrame(data[1:], columns=headers)
            tract_df["tract_geoid"] = (
                tract_df["state"].str.zfill(2)
                + tract_df["county"].str.zfill(3)
                + tract_df["tract"].str.zfill(6)
            )
            for code in census_codes:
                if code in tract_df.columns:
                    tract_df[code] = pd.to_numeric(tract_df[code], errors="coerce").fillna(0)
        except Exception as e:
            logger.warning(f"  Tract-level education data fetch failed: {e}")
            return None

        # Build synthetic columns for multi-var education metrics in tract_df
        for m in edu_metrics:
            if m in MULTI_VAR_METRICS:
                comp_codes = [VOTER_DEMOGRAPHICS.get(c, c) for c in MULTI_VAR_METRICS[m]]
                avail      = [c for c in comp_codes if c in tract_df.columns]
                if avail:
                    tract_df[m] = tract_df[avail].sum(axis=1)
            elif m in VOTER_DEMOGRAPHICS and VOTER_DEMOGRAPHICS[m] in tract_df.columns:
                tract_df[m] = tract_df[VOTER_DEMOGRAPHICS[m]]

        # Aggregate crosswalk from BG→precinct to tract→precinct by summing weights
        cw = crosswalk.copy()
        cw["tract_geoid"] = cw["bg_geoid"].str[:11]
        tract_weights = (
            cw.groupby(["tract_geoid", "precinct_geoid"])["weight"]
            .sum()
            .reset_index()
            .rename(columns={"weight": "tract_weight"})
        )

        edu_cols = [m for m in edu_metrics if m in tract_df.columns]
        if not edu_cols:
            logger.warning("  No education columns available in tract data after expansion.")
            return None

        merged = tract_weights.merge(
            tract_df[["tract_geoid"] + edu_cols],
            on="tract_geoid",
            how="left",
        )
        for m in edu_cols:
            merged[f"weighted_{m}"] = merged[m].fillna(0) * merged["tract_weight"]

        weighted_cols = [f"weighted_{m}" for m in edu_cols]
        return merged.groupby("precinct_geoid")[weighted_cols].sum()

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    @staticmethod
    def get_top_precincts(
        state_fips: str,
        district_id: str,
        district_type: str = "congressional",
        metrics: List[str] = None,
        top_n: int = 20,
        combined_primary_metrics: List[str] = None,
    ) -> list:
        """
        Returns the top N precincts ranked by the first metric in the list.

        Args:
            state_fips:    Zero-padded 2-digit FIPS string, e.g. "51"
            district_id:   GEOID string, e.g. "5107" for VA-07
            district_type: "congressional" | "state_senate" | "state_house"
            metrics:       List of friendly Census variable names from census_vars.py,
                           e.g. ["total_cvap", "black", "hispanic"].
                           Raw Census codes (e.g. "B01001_001E") also accepted.
            top_n:         Number of top precincts to return

        Returns a list of dicts with a predictable schema:
            {
                "precinct_geoid":      str,   # full GEOID from TopoJSON
                "precinct_name":       str,   # human-readable name parsed from GEOID
                "<metric_1>":          float, # weighted reaggregated value
                ...
                "approximate_boundary": bool  # True when official_boundary is False
            }
        """
        if metrics is None:
            metrics = ["total_vap"]

        # Always include total_vap so every output row carries the full VAP denominator.
        # Append rather than prepend so metrics[0] stays the caller's primary sort metric.
        if "total_vap" not in metrics:
            metrics = list(metrics) + ["total_vap"]

        # Split into block-group-available metrics and tract-only education metrics.
        # B15003 (educational attainment) is not available at block group resolution
        # in ACS5; those metrics are handled by a separate tract-level path below.
        bg_metrics  = [m for m in metrics if m not in TRACT_ONLY_METRICS]
        edu_metrics = [m for m in metrics if m in TRACT_ONLY_METRICS]

        # Expand BG multi-variable metrics into their leaf component friendly names.
        # Composite names (e.g. "youth_vap") must never appear in the Census API
        # request — the API only accepts real variable codes like B01001_007E.
        # Composite names are recovered in step 3 after the fetch, when component
        # columns are summed into a synthetic column and metric_to_code is updated.
        fetch_metrics: list = []
        for m in bg_metrics:
            if m in MULTI_VAR_METRICS:
                for comp in MULTI_VAR_METRICS[m]:
                    if comp not in fetch_metrics:
                        fetch_metrics.append(comp)
            elif m not in fetch_metrics:
                fetch_metrics.append(m)

        # Translate leaf friendly names to Census API codes for column lookup.
        # e.g. "hispanic_pop" → "B03003_003E", raw codes pass through unchanged.
        # Composite metric names are absent from fetch_metrics so they cannot
        # appear here and cannot leak into the Census API URL.
        metric_to_code = {m: VOTER_DEMOGRAPHICS.get(m, m) for m in fetch_metrics}

        # Some metrics are crosswalk-native: their values come from columns already
        # present in the crosswalk CSV (built by crosswalk_builder.py) rather than
        # fetched from the Census ACS API. "vap" → "bg_vap" is the primary example.
        # Sending these codes to the Census API would return a 400 error.
        CROSSWALK_NATIVE_CODES = {"bg_vap"}
        acs_metrics = [m for m in fetch_metrics if metric_to_code.get(m) not in CROSSWALK_NATIVE_CODES]
        # Always fetch at least one ACS variable so we have the BG geography columns
        if not acs_metrics:
            acs_metrics = ["total_population"]

        # 1. Fetch Census block-group data for ACS metrics
        raw_bg_data = DataFetcher.get_census_data(state_fips, acs_metrics, geo_level="precinct")
        if not raw_bg_data or "error" in raw_bg_data[0]:
            logger.error(f"Census fetch failed: {raw_bg_data}")
            return {"error": f"Census API failure: {raw_bg_data[0].get('error') if raw_bg_data else 'no data'}"}

        bg_df = pd.DataFrame(raw_bg_data)

        # Construct the 12-char bg_geoid from the component Census API fields.
        # The Census API returns state, county, tract, block group as separate columns —
        # there is no pre-built GEOID column in the response.
        bg_df["bg_geoid"] = (
            bg_df["state"].str.zfill(2)
            + bg_df["county"].str.zfill(3)
            + bg_df["tract"].str.zfill(6)
            + bg_df["block group"]
        )

        # 2. Filter to block groups within the target district before the crosswalk merge
        district_bg_geoids = PrecinctsAgent._get_district_bg_geoids(
            state_fips, district_id, district_type
        )
        if district_bg_geoids:
            bg_df = bg_df[bg_df["bg_geoid"].isin(district_bg_geoids)].copy()
            if bg_df.empty:
                logger.warning(f"No block groups matched district filter for {district_id}.")
                return {"error": f"No Census block groups found within district {district_id}."}
        else:
            logger.warning("District filter unavailable; using all state block groups.")

        # 3. Build synthetic columns for BG-level multi-var metrics.
        # Sum component Census code columns into a single column (e.g. "youth_vap")
        # so the dasymetric weighting step treats it like any other ACS variable.
        # Education multi-var metrics are excluded here — they use the tract path below.
        for mv_name, components in MULTI_VAR_METRICS.items():
            if mv_name in bg_metrics:
                comp_codes = [VOTER_DEMOGRAPHICS.get(c, c) for c in components]
                available  = [c for c in comp_codes if c in bg_df.columns]
                if available:
                    bg_df[mv_name] = (
                        bg_df[available].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
                    )
                    metric_to_code[mv_name] = mv_name  # point weighting step at the synthetic column
                else:
                    logger.warning(f"No component columns found for multi-var metric '{mv_name}'; skipping.")

        # 4. Load the crosswalk (built by crosswalk_builder.py).
        # Try district-specific crosswalk first (built with district_id arg); these
        # contain only BGs and precincts within the target district and give correct
        # results without relying on the Census API's unsupported BG-by-CD geography.
        # Fall back to the full-state crosswalk when no district-specific file exists.
        # Force bg_geoid to str: pandas auto-casts 12-digit GEOIDs to int64,
        # which would break the merge with bg_df where bg_geoid is always a string.
        district_crosswalk = f"data/crosswalks/{state_fips}_{district_id}_bg_to_precinct.csv"
        state_crosswalk    = f"data/crosswalks/{state_fips}_bg_to_precinct.csv"
        crosswalk_path     = district_crosswalk if file_exists(district_crosswalk) else state_crosswalk
        if crosswalk_path == district_crosswalk:
            logger.info(f"  Using district-specific crosswalk: {crosswalk_path}")
        else:
            logger.info(f"  District crosswalk not found; using state-level: {crosswalk_path}")
        try:
            crosswalk = read_dataframe(crosswalk_path, dtype={"bg_geoid": str})
        except FileNotFoundError:
            return {"coverage_note": (
                f"No crosswalk file found for state {state_fips} "
                f"(tried {district_crosswalk} and {state_crosswalk}). "
                "Run crosswalk_builder.build_crosswalk() to add coverage for this district."
            )}

        # Normalise official_boundary to bool (CSV reads it as string)
        crosswalk["official_boundary"] = (
            crosswalk["official_boundary"].astype(str).str.lower() == "true"
        )

        # Build a precinct_geoid → human-readable name lookup before the groupby
        # drops non-numeric columns. Prefer a dedicated TopoJSON-derived column
        # ('name' or 'precinct') when the crosswalk builder included one; fall back
        # to parsing the embedded name from the concatenated precinct_geoid string
        # (format: "{id} {name}", e.g. "01001-10 JONES COMM_ CTR_").
        _topo_name_col = next(
            (c for c in ("name", "precinct") if c in crosswalk.columns), None
        )
        if _topo_name_col:
            _precinct_name_map: dict = (
                crosswalk[["precinct_geoid", _topo_name_col]]
                .drop_duplicates("precinct_geoid")
                .set_index("precinct_geoid")[_topo_name_col]
                .to_dict()
            )
        else:
            _precinct_name_map = {}

        # 5. Merge block group Census data with crosswalk
        # Core dasymetric logic — do not change
        merged = bg_df.merge(crosswalk, on="bg_geoid")

        if merged.empty:
            return {"error": f"Crosswalk merge produced no rows for district {district_id}. "
                             "Verify that the crosswalk was built for this state."}

        # 6. Apply dasymetric weights per metric and reaggregate by precinct
        # weighted_value = block_group_value * (intersection_area / bg_total_area)
        # Do not change this logic
        for friendly_name, census_code in metric_to_code.items():
            if census_code in merged.columns:
                merged[f"weighted_{friendly_name}"] = (
                    pd.to_numeric(merged[census_code], errors="coerce").fillna(0)
                    * merged["weight"]
                )
            else:
                logger.warning(f"Column '{census_code}' not found in Census data; skipping metric '{friendly_name}'.")

        # Use bg_metrics (not full metrics) — edu metric weighted cols won't be in merged
        weighted_cols = [f"weighted_{m}" for m in bg_metrics if f"weighted_{m}" in merged.columns]

        # Aggregate weighted values by precinct.
        # When only education metrics were requested, bg_metrics is empty so we scaffold
        # an empty precinct index from the crosswalk to join education results onto.
        if weighted_cols:
            precinct_totals = merged.groupby("precinct_geoid")[weighted_cols].sum()
        else:
            precinct_totals = (
                merged[["precinct_geoid"]].drop_duplicates().set_index("precinct_geoid")
            )

        # Determine boundary quality per precinct:
        # approximate_boundary = True if ANY contributing BG has official_boundary=False
        boundary_flags = (
            merged.groupby("precinct_geoid")["official_boundary"]
            .all()
            .rename("all_official")
        )
        precinct_totals = precinct_totals.join(boundary_flags)
        precinct_totals["approximate_boundary"] = ~precinct_totals["all_official"].fillna(False)
        precinct_totals = precinct_totals.drop(columns=["all_official"])

        # 6b. Tract-level education metrics (B15003 — not available at block group in ACS5).
        # Fetches tract data, derives tract→precinct weights from the crosswalk, and joins
        # the resulting weighted columns into precinct_totals. Core dasymetric logic unchanged.
        if edu_metrics:
            logger.warning(
                "  Education metrics (B15003) are available at Census tract level only in ACS5. "
                "Applying simplified tract→precinct areal weighting — results are less granular "
                "than block-group targeting."
            )
            edu_data = PrecinctsAgent._compute_tract_education_weights(
                state_fips, edu_metrics, crosswalk
            )
            if edu_data is not None:
                precinct_totals = precinct_totals.join(edu_data, how="left")
                for m in edu_metrics:
                    col = f"weighted_{m}"
                    if col in precinct_totals.columns:
                        precinct_totals[col] = precinct_totals[col].fillna(0)
            else:
                logger.warning("  Tract-level education weighting failed; education metrics will be absent from output.")

        # 6c. Combined targeting metric (multi-demographic queries).
        # Use the MAX of the primary weighted columns so the sort reflects the
        # strongest single-group concentration in each precinct. Summing would
        # overcount — e.g. youth_vap + hispanic_vap double-counts voters who are
        # both young and Hispanic, pushing the aggregate above total_vap.
        if combined_primary_metrics:
            avail_combined = [
                f"weighted_{m}" for m in combined_primary_metrics
                if f"weighted_{m}" in precinct_totals.columns
            ]
            if avail_combined:
                precinct_totals["weighted_combined_target"] = precinct_totals[avail_combined].max(axis=1)

        use_combined_target = "weighted_combined_target" in precinct_totals.columns

        # 7. Rank by combined target (multi-demo) or primary metric (single demo)
        if use_combined_target:
            sort_col = "weighted_combined_target"
        elif f"weighted_{metrics[0]}" in precinct_totals.columns:
            sort_col = f"weighted_{metrics[0]}"
        else:
            sort_col = None

        if sort_col:
            precinct_totals = precinct_totals.sort_values(sort_col, ascending=False)

        # Count total unique precincts in crosswalk before truncating to top_n.
        # Used for data quality check below.
        total_precinct_count = len(precinct_totals)

        top_targets = precinct_totals.head(top_n).reset_index()

        # 8. Build standardised output schema
        results = []
        for _, row in top_targets.iterrows():
            raw_geoid = row["precinct_geoid"]
            precinct_id = raw_geoid.split(" ", 1)[0]
            _topo_name = _precinct_name_map.get(raw_geoid) or _precinct_name_map.get(precinct_id)
            # Use the TopoJSON name only when it is actually human-readable —
            # i.e. not identical to the bare GEOID and not a plain number.
            if _topo_name and _topo_name.strip() != precinct_id and not _topo_name.strip().isdigit():
                precinct_name = _topo_name
            else:
                precinct_name = _format_precinct_label(precinct_id)
            record = {
                "precinct_geoid": raw_geoid,
                "precinct_id":    precinct_id,
                "precinct_name":  precinct_name,
            }
            # User-requested metrics (total_vap gets its own standardised key below)
            for metric in metrics:
                if metric == "total_vap":
                    continue
                wcol = f"weighted_{metric}"
                if wcol in row.index:
                    record[metric] = round(float(row[wcol]), 2)

            # Always-present targeting columns
            total_vap_val = float(row.get("weighted_total_vap", 0) or 0)
            if use_combined_target:
                # weighted_combined_target = max(primary1, primary2) — no cap needed.
                target_val = float(row.get("weighted_combined_target", 0) or 0)
            else:
                target_val = float(row.get(f"weighted_{metrics[0]}", 0) or 0)

            record["total_vap"]              = round(total_vap_val, 2)
            record["target_demographic_vap"] = round(target_val, 2)
            record["target_demographic_pct"] = (
                round(target_val / total_vap_val * 100, 2) if total_vap_val > 0 else 0.0
            )
            record["penetration_rate"] = (
                round(target_val / total_vap_val, 4) if total_vap_val > 0 else 0.0
            )
            record["approximate_boundary"] = bool(row.get("approximate_boundary", False))
            results.append(record)

        # 9. Data quality check: fewer than 100 precincts suggests ward/municipality-level
        # granularity rather than individual polling-precinct granularity.
        data_quality_note = None
        if total_precinct_count < 100:
            data_quality_note = (
                "Precinct data may be reporting at ward or municipality level rather than "
                "individual polling precinct level for this state. Targeting results reflect "
                "broader geographic units and may be less granular than expected."
            )
            logger.warning(
                f"  Data quality: only {total_precinct_count} precincts in crosswalk for "
                f"district {district_id} — results may reflect ward/municipality-level units."
            )

        return {
            "precincts":          results,
            "precinct_count":     total_precinct_count,
            "data_quality_note":  data_quality_note,
            "tract_fallback_used": bool(edu_metrics),
        }

    # ------------------------------------------------------------------
    # LangGraph node wrapper
    # ------------------------------------------------------------------

    @staticmethod
    def run(state: AgentState) -> dict:
        """
        LangGraph node wrapper. Extracts precinct targeting parameters from
        the user's query via LLM, calls get_top_precincts(), and writes
        results to AgentState.
        """
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            openai_api_key=os.environ["OPENAI_API_KEY"],
        )

        extraction_prompt = f"""
Extract precinct targeting parameters from this query. Return ONLY these lines, no extra text.

Query: "{state['query']}"

STATE: [full state name or abbreviation, e.g. "Virginia" or "VA"]
DISTRICT_TYPE: [congressional | state_senate | state_house]
DISTRICT_NUM: [integer district number]
METRICS: [comma-separated Census variable names from this list: total_cvap, total_population, black, hispanic, white, median_income, poverty_total, unemployed — choose what is relevant to the query]
TOP_N: [integer number of precincts to return, default 20]
"""
        try:
            raw = llm.invoke(extraction_prompt).content.strip()
        except Exception as e:
            return {
                "errors":        [f"PrecinctsAgent: LLM extraction failed — {e}"],
                "active_agents": ["precincts"],
            }

        params = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                params[key.strip().upper()] = val.strip().strip('"')

        # Resolve state FIPS
        state_name = params.get("STATE", "")
        state_fips = GeographyStandardizer.STATE_FIPS.get(state_name.lower())
        if not state_fips:
            return {
                "errors":        [f"PrecinctsAgent: Could not resolve state FIPS for '{state_name}'."],
                "active_agents": ["precincts"],
            }

        district_type = params.get("DISTRICT_TYPE", "congressional").lower()

        # Demographic intent is set by intent_router_node in manager.py via a keyword
        # scan of the query — no extra LLM call required. It overrides whatever METRICS
        # the LLM extracted, ensuring the targeting metric always matches the user's ask.
        # Combined intents (e.g. "black+hispanic") are joined with "+" and split here.
        demographic_intent = (state.get("demographic_intent") or "default").lower()
        intents = demographic_intent.split("+") if "+" in demographic_intent else [demographic_intent]

        # Collect the union of metrics across all matched intents (order preserved, deduplicated)
        metrics: list = []
        combined_primary_metrics: list = []
        for intent in intents:
            intent_metrics = _DEMOGRAPHIC_METRICS.get(intent, _DEMOGRAPHIC_METRICS["default"])
            primary = intent_metrics[0] if intent_metrics else None
            if primary and primary not in combined_primary_metrics:
                combined_primary_metrics.append(primary)
            for m in intent_metrics:
                if m not in metrics:
                    metrics.append(m)

        if len(intents) > 1:
            demographic_profile = " | ".join(
                _DEMOGRAPHIC_PROFILES[i] for i in intents if i in _DEMOGRAPHIC_PROFILES
            )
        else:
            demographic_profile = _DEMOGRAPHIC_PROFILES.get(demographic_intent, _DEMOGRAPHIC_PROFILES["default"])
            combined_primary_metrics = None  # single intent: no synthetic combined column needed

        try:
            dist_num = normalize_district(params.get("DISTRICT_NUM", 0))
            top_n    = int(params.get("TOP_N", 20))
        except ValueError:
            dist_num = 1  # default to at-large on unrecognizable input
            top_n    = 20

        # Build GEOID for the target district
        geoid = GeographyStandardizer.convert_to_geoid(state_name, dist_num, district_type)
        if isinstance(geoid, dict):
            return {
                "errors":        [f"PrecinctsAgent: {geoid.get('error')}"],
                "active_agents": ["precincts"],
            }

        output = PrecinctsAgent.get_top_precincts(
            state_fips, geoid, district_type, metrics, top_n,
            combined_primary_metrics=combined_primary_metrics,
        )

        # Coverage-miss path: crosswalk file doesn't exist yet for this district.
        # Return a non-fatal structured entry so the rest of the pipeline continues.
        if "coverage_note" in output:
            logger.warning(
                "PrecinctsAgent: no crosswalk for %s — returning empty precincts entry. %s",
                geoid, output["coverage_note"],
            )
            return {
                "structured_data": [{
                    "agent":         "precincts",
                    "state_fips":    state_fips,
                    "district_type": district_type,
                    "district_id":   geoid,
                    "precincts":     [],
                    "precinct_count": 0,
                    "coverage_note": output["coverage_note"],
                }],
                "errors": [
                    "Precinct-level targeting is not available for this district yet — "
                    "win number, research, opposition research, and messaging are still available. "
                    "Contact us to request crosswalk coverage for this district."
                ],
                "active_agents": ["precincts"],
            }

        # Error path: get_top_precincts returns {"error": "..."} on failure
        if "error" in output:
            return {
                "errors":        [f"PrecinctsAgent: {output['error']}"],
                "active_agents": ["precincts"],
            }

        precincts           = output["precincts"]
        precinct_count      = output["precinct_count"]
        data_quality_note   = output["data_quality_note"]
        tract_fallback_used = output.get("tract_fallback_used", False)

        state_update: dict = {
            "structured_data": [{
                "agent":         "precincts",
                # Geographic context written here so downstream agents (win_number,
                # messaging, cost_calculator) can read it without re-extracting from query
                "state_fips":    state_fips,
                "district_type": district_type,
                "district_id":   geoid,
                "precincts":     precincts,
                "precinct_count": precinct_count,
                "demographic_profile": {
                    "intent":      demographic_intent,
                    "metrics":     metrics,
                    "explanation": demographic_profile,
                },
            }],
            "active_agents": ["precincts"],
        }

        if data_quality_note:
            state_update["structured_data"][0]["data_quality_note"] = data_quality_note
            state_update["errors"] = [f"PrecinctsAgent: {data_quality_note}"]

        if tract_fallback_used:
            state_update["structured_data"][0]["tract_fallback_note"] = (
                "College enrollment (B14001_005E) and/or education attainment (B15003) "
                "data were sourced from Census tract level (ACS5 block-group data unavailable). "
                "Results are less spatially granular than block-group targeting."
            )

        if len(intents) > 1:
            state_update["structured_data"][0]["combined_demographics_note"] = (
                f"Multi-demographic targeting: combined {' + '.join(intents)} groups. "
                f"Precincts ranked by the larger of: {', '.join(combined_primary_metrics or [])}. "
                "Each demographic's VAP is shown as a separate column. "
                "target_demographic_vap reflects the dominant group (not a sum) to avoid "
                "double-counting voters who appear in multiple demographic groups."
            )

        return state_update
