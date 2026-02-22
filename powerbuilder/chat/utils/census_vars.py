# powerbuilder/chat/utils/census_vars.py

# --- BASIC DEMOGRAPHICS ---
CENSUS_DEMOGRAPHICS = {
    "total_population": "B01003_001E",
    "median_age": "B01002_001E",
    "white": "B03002_003E",
    "black": "B03002_004E",
    "hispanic": "B03002_012E",
}

# --- SOCIOECONOMIC & HOUSING ---
# These variables help with economic messaging and precinct targeting
SOCIOECONOMIC_VARS = {
    # Housing Tenure
    "homeowners": "B25003_002E",
    "renters": "B25003_003E",
    "avg_household_size": "B25010_001E",
    
    # Education (Ages 25+)
    "bach_degree": "B15003_022E",
    "high_school_grad": "B15003_017E",
    "no_high_school": "B15003_002E",

    # Poverty & Employment
    "poverty_total": "B17001_002E",
    "unemployed": "S2301_C04_001E",
    "median_income": "B19013_001E",
}

# --- SOCIAL SERVICES & HEALTH ---
# Critical for identifying high-need or service-reliant populations
SOCIAL_SERVICES_VARS = {
    "food_stamps_snap": "B22001_002E",  # Households receiving SNAP
    "medicaid_coverage": "B27010_018E",  # Public health insurance (Low-income)
    "medicare_coverage": "B27010_019E",  # Public health insurance (Age 65+)
    "social_security": "B19055_001E",    # Households with Social Security income
}

# --- RACE & GENDER CROSS-TABS ---
# Table Iterations (A through I) for B01001 (Sex by Age)
RACE_TABLES = {
    "total": "B01001",      # All races
    "white": "B01001A",     # White Alone
    "black": "B01001B",     # Black/African American Alone
    "native": "B01001C",    # American Indian/Alaska Native Alone
    "asian": "B01001D",     # Asian Alone
    "islander": "B01001E",  # Native Hawaiian/Pacific Islander Alone
    "other": "B01001F",     # Some Other Race Alone
    "multi": "B01001G",     # Two or More Races
    "white_nh": "B01001H",  # White Alone, Not Hispanic
    "latino": "B01001I"     # Hispanic or Latino (Any Race)
}

# Age Brackets within those Race Tables
# These follow the standard Census offsets for gendered age groups
SEX_AGE_OFFSETS = {
    "male": {
        "total": "002", "18_19": "007", "20": "008", "21": "009", 
        "22_24": "010", "25_29": "011", "30_34": "012", "35_44": "013", 
        "45_54": "014", "55_64": "015", "65_74": "016", "75_84": "017", "85_plus": "018"
    },
    "female": {
        "total": "020", "18_19": "025", "20": "026", "21": "027", 
        "22_24": "028", "25_29": "029", "30_34": "030", "35_44": "031", 
        "45_54": "032", "55_64": "033", "65_74": "034", "75_84": "035", "85_plus": "036"
    }
}

# --- ANCESTRY & ETHNICITY ---
# Specific ancestries from B04006
ANCESTRY_MAP = {
    "irish": "007", "italian": "010", "german": "006", "arab": "014",
    "egyptian": "015", "syrian": "018", "palestinian": "017",
    "korean": "050", "chinese": "040"
}

# MASTER VARIABLE LIST (Combining all for the get_census_data mapping)
VOTER_DEMOGRAPHICS = {
    **CENSUS_DEMOGRAPHICS, 
    **SOCIOECONOMIC_VARS, 
    **SOCIAL_SERVICES_VARS
}