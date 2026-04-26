# powerbuilder/chat/utils/census_vars.py

# --- BASIC DEMOGRAPHICS ---
CENSUS_DEMOGRAPHICS = {
    "total_population": "B01003_001E",
    "total_cvap": "B29001_001E",  # Citizen VAP — tract level only; not available at block group
    "vap": "bg_vap",              # Voting Age Population 18+ from 2020 Decennial PL94-171 (P0030001);
                                  # stored in the crosswalk CSV by crosswalk_builder.py, not fetched from ACS
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

# --- DEMOGRAPHIC TARGETING GROUPS ---

# Age cohorts 18-29 from B01001 (Sex by Age), male then female.
#   007/031=18-19, 008/032=20, 009/033=21, 010/034=22-24, 011/035=25-29
# Summed by PrecinctsAgent into the synthetic "youth_vap" metric.
YOUTH_VAP_VARS: dict[str, str] = {
    "youth_m_18_19": "B01001_007E",
    "youth_m_20":    "B01001_008E",
    "youth_m_21":    "B01001_009E",
    "youth_m_22_24": "B01001_010E",
    "youth_m_25_29": "B01001_011E",
    "youth_f_18_19": "B01001_031E",
    "youth_f_20":    "B01001_032E",
    "youth_f_21":    "B01001_033E",
    "youth_f_22_24": "B01001_034E",
    "youth_f_25_29": "B01001_035E",
}

# Seniors 65+ from B01001, male (020-025) and female (044-049).
SENIOR_VAP_VARS: dict[str, str] = {
    "senior_m_65_66": "B01001_020E",
    "senior_m_67_69": "B01001_021E",
    "senior_m_70_74": "B01001_022E",
    "senior_m_75_79": "B01001_023E",
    "senior_m_80_84": "B01001_024E",
    "senior_m_85p":   "B01001_025E",
    "senior_f_65_66": "B01001_044E",
    "senior_f_67_69": "B01001_045E",
    "senior_f_70_74": "B01001_046E",
    "senior_f_75_79": "B01001_047E",
    "senior_f_80_84": "B01001_048E",
    "senior_f_85p":   "B01001_049E",
}

# B15003 Educational Attainment — TRACT LEVEL ONLY in ACS5 (not available at block group).
# PrecinctsAgent detects these and routes them through a separate tract-level fetch path.

# No HS diploma: no schooling (002) through 12th grade no diploma (016)
NO_HS_DIPLOMA_VARS: dict[str, str] = {
    "edu_no_school":  "B15003_002E",
    "edu_nursery":    "B15003_003E",
    "edu_kinder":     "B15003_004E",
    "edu_g1":         "B15003_005E",
    "edu_g2":         "B15003_006E",
    "edu_g3":         "B15003_007E",
    "edu_g4":         "B15003_008E",
    "edu_g5":         "B15003_009E",
    "edu_g6":         "B15003_010E",
    "edu_g7":         "B15003_011E",
    "edu_g8":         "B15003_012E",
    "edu_g9":         "B15003_013E",
    "edu_g10":        "B15003_014E",
    "edu_g11":        "B15003_015E",
    "edu_g12_no_dip": "B15003_016E",
}

# Some college / associate's degree (019-021)
SOME_COLLEGE_VARS: dict[str, str] = {
    "edu_some_col_lt1": "B15003_019E",
    "edu_some_col_1p":  "B15003_020E",
    "edu_associates":   "B15003_021E",
}

# Graduate and professional degrees (023-025)
GRADUATE_DEGREE_VARS: dict[str, str] = {
    "edu_masters":      "B15003_023E",
    "edu_professional": "B15003_024E",
    "edu_doctorate":    "B15003_025E",
}

# B15003 top-level names and all their component keys — PrecinctsAgent uses this set
# to route education metrics through the tract-level fallback instead of the BG path.
TRACT_ONLY_METRICS: frozenset = frozenset({
    "no_hs_diploma", "some_college", "graduate_degree",
    "graduate_educated", "bachelors_degree",
    "college_enrolled",  # B14001_005E — enrolled in college; ACS5 block-group data unavailable
    *NO_HS_DIPLOMA_VARS.keys(),
    *SOME_COLLEGE_VARS.keys(),
    *GRADUATE_DEGREE_VARS.keys(),
})

# Multi-variable metrics: each key maps to a list of component friendly names to sum.
# Components must be keys in VOTER_DEMOGRAPHICS (single-code vars).
# PrecinctsAgent expands these before fetching Census data.
MULTI_VAR_METRICS: dict[str, list[str]] = {
    "youth_vap":         list(YOUTH_VAP_VARS.keys()),
    "senior_vap":        list(SENIOR_VAP_VARS.keys()),
    "aapi":              ["asian_pop", "nhpi_pop"],
    "no_hs_diploma":     list(NO_HS_DIPLOMA_VARS.keys()),
    "some_college":      list(SOME_COLLEGE_VARS.keys()),
    "graduate_degree":   list(GRADUATE_DEGREE_VARS.keys()),
    # graduate_educated = bachelor's + all graduate/professional degrees
    "graduate_educated": ["bachelors_degree"] + list(GRADUATE_DEGREE_VARS.keys()),
}

# Single-variable targeting metrics for demographic-specific precinct ranking.
TARGETING_VARS: dict[str, str] = {
    # College / youth
    "college_enrolled": "B14001_005E",  # Enrolled in college or graduate school
    # Race / ethnicity
    "hispanic_pop":     "B03003_003E",  # Hispanic or Latino (B03003)
    "black_pop":        "B02001_003E",  # Black or African American alone (B02001)
    "asian_pop":        "B02001_005E",  # Asian alone
    "native_pop":       "B02001_004E",  # American Indian and Alaska Native alone
    "nhpi_pop":         "B02001_006E",  # Native Hawaiian and Pacific Islander alone
    "multiracial_pop":  "B02001_008E",  # Two or more races
    "white_nh_pop":     "B03002_003E",  # White alone, not Hispanic (B03002)
    "foreign_born_pop": "B05002_013E",  # Foreign-born population (B05002)
    # Education — TRACT LEVEL ONLY (see TRACT_ONLY_METRICS)
    "bachelors_degree": "B15003_022E",  # Bachelor's degree
    # Economic
    "poverty_pop":  "B17001_002E",  # Households below poverty line (alias for poverty_total)
    "owner_pop":    "B25003_002E",  # Owner-occupied units (alias for homeowners)
    "renter_pop":   "B25003_003E",  # Renter-occupied units
    # Veterans
    "veteran_pop":  "B21001_002E",  # Civilian veterans (B21001)
    # VAP alias for default targeting (crosswalk-native, same underlying data as "vap")
    "total_vap":    "bg_vap",
}

# MASTER VARIABLE LIST (combining all groups for get_census_data mapping)
VOTER_DEMOGRAPHICS = {
    **CENSUS_DEMOGRAPHICS,
    **SOCIOECONOMIC_VARS,
    **SOCIAL_SERVICES_VARS,
    **YOUTH_VAP_VARS,
    **SENIOR_VAP_VARS,
    **NO_HS_DIPLOMA_VARS,
    **SOME_COLLEGE_VARS,
    **GRADUATE_DEGREE_VARS,
    **TARGETING_VARS,
}