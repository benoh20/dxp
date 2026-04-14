# powerbuilder/chat/utils/crosswalk_builder.py
"""
Builds block-group-to-precinct areal interpolation crosswalk files.

Sources:
  - NYT 2024 precinct TopoJSON (precinct boundaries + vote results)
  - Census TIGER/Line 2022 block group shapefiles (downloaded per state)

Output per state: data/crosswalks/{state_fips}_bg_to_precinct.csv
  Columns: bg_geoid, precinct_geoid, weight, official_boundary

Weight definition:
  weight = intersection_area / block_group_total_area
  All weights for a given block group sum to 1.0 (subject to boundary alignment).

Prioritizes correctness: uses full areal intersection, not centroid approximation.
"""

import json
import logging
import os

import geopandas as gpd
import pandas as pd
from shapely.validation import make_valid

from .district_standardizer import GeographyStandardizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

TOPOJSON_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../precinct_shapefiles/2024precincts-with-results.topojson")
)

CROSSWALK_DIR = "data/crosswalks"

# TIGER/Line 2022 block group shapefiles — one per state, matches ACS5 2022 Census data
TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2022/BG/tl_2022_{state_fips}_bg.zip"

# Albers Equal Area Conic — accurate for area calculations across CONUS.
# Alaska and Hawaii introduce minor distortion but weights are relative within a state,
# so the impact on correctness is negligible.
AREA_CRS = "EPSG:5070"

# Warn when a block group's weights deviate from 1.0 by more than this threshold.
# Values above zero but below 1% typically indicate floating-point edge slivers.
# Values above 1% indicate genuine boundary misalignment between TopoJSON and TIGER.
WEIGHT_TOLERANCE = 0.01

# ---------------------------------------------------------------------------
# Lookup tables derived from district_standardizer.py
# ---------------------------------------------------------------------------

# {fips: "VA"} — used to convert input FIPS to the state abbreviation field in TopoJSON
FIPS_TO_ABBR = {
    fips: abbr.upper()
    for abbr, fips in GeographyStandardizer.STATE_FIPS.items()
    if len(abbr) == 2
}

# {"VA": fips} — used in build_all_states() to go from TopoJSON abbreviation back to FIPS
ABBR_TO_FIPS = {abbr: fips for fips, abbr in FIPS_TO_ABBR.items()}

# ---------------------------------------------------------------------------
# TopoJSON parsing
# ---------------------------------------------------------------------------

def _read_topojson(path: str) -> gpd.GeoDataFrame:
    """
    Read a TopoJSON file into a GeoDataFrame.

    Tries geopandas/fiona first (zero extra dependencies). Falls back to the
    `topojson` library if fiona's TopoJSON driver is unavailable. Raises
    RuntimeError with install instructions if both fail.
    """
    with open(path) as f:
        raw = json.load(f)

    # Infer layer name from the first key under "objects"
    objects = raw.get("objects", {})
    if not objects:
        raise ValueError(f"No 'objects' found in TopoJSON at {path}")
    layer_name = next(iter(objects))

    # Attempt 1: geopandas / fiona (GDAL TopoJSON driver)
    try:
        gdf = gpd.read_file(path, layer=layer_name)
        logger.debug(f"Read TopoJSON via geopandas/fiona (layer: '{layer_name}').")
        return gdf
    except Exception as fiona_err:
        logger.debug(f"geopandas/fiona read failed ({fiona_err}), trying topojson library.")

    # Attempt 2: topojson Python library
    try:
        import topojson as tp  # pip install topojson
        topo = tp.Topology(raw, prequantize=False)
        gdf = topo.to_gdf()
        logger.debug("Read TopoJSON via topojson library.")
        return gdf
    except ImportError:
        pass
    except Exception as topo_err:
        logger.debug(f"topojson library read failed: {topo_err}")

    raise RuntimeError(
        f"Could not parse TopoJSON at {path}. "
        "Install the topojson package as a fallback: pip install topojson"
    )

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fix_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Repair invalid geometries and drop null/empty ones."""
    gdf = gdf.copy()
    gdf["geometry"] = gdf["geometry"].apply(
        lambda g: make_valid(g) if g is not None and not g.is_valid else g
    )
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def _load_precincts_for_state(state_fips: str, all_precincts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Filter a pre-loaded precinct GeoDataFrame to one state.

    Returns a GeoDataFrame with columns: precinct_geoid, official_boundary, geometry.
    The precinct_geoid preserves the full GEOID string from the TopoJSON
    (format: "{5-digit county FIPS}-{precinct ID} {NAME}", e.g. "01001-10 JONES COMM_ CTR_").
    """
    abbr = FIPS_TO_ABBR.get(state_fips)
    if not abbr:
        raise ValueError(f"No state abbreviation found for FIPS '{state_fips}'.")

    state_gdf = all_precincts[all_precincts["state"].str.upper() == abbr].copy()
    if state_gdf.empty:
        logger.warning(f"No precincts found for {abbr} (FIPS: {state_fips}) in TopoJSON.")
        return state_gdf

    # Normalize GEOID column name to precinct_geoid
    geoid_col = "GEOID" if "GEOID" in state_gdf.columns else "geoid"
    state_gdf = state_gdf.rename(columns={geoid_col: "precinct_geoid"})

    state_gdf = _fix_geometries(state_gdf)
    logger.info(f"  {len(state_gdf)} precincts loaded for {abbr}.")
    return state_gdf[["precinct_geoid", "official_boundary", "geometry"]]


def _load_block_groups(state_fips: str) -> gpd.GeoDataFrame:
    """
    Download Census TIGER/Line 2022 block group boundaries for a state.

    Returns a GeoDataFrame with columns: bg_geoid, geometry.
    bg_geoid is the 12-character Census identifier:
    {state(2)}{county(3)}{tract(6)}{block_group(1)}
    """
    url = TIGER_URL.format(state_fips=state_fips)
    logger.info(f"  Downloading Census block group boundaries: {url}")

    bg_gdf = gpd.read_file(url)

    # TIGER uses "GEOID" for the 12-digit block group identifier
    bg_gdf = bg_gdf.rename(columns={"GEOID": "bg_geoid"})
    bg_gdf = _fix_geometries(bg_gdf)

    logger.info(f"  {len(bg_gdf)} block groups loaded.")
    return bg_gdf[["bg_geoid", "geometry"]]


def _validate_weights(intersected: gpd.GeoDataFrame, bg_count: int) -> None:
    """
    Log warnings for block groups whose weights deviate from 1.0.

    Two distinct warning cases:
      - No intersection at all: block group has no matching precinct (water, unpopulated land)
      - Partial coverage: weights sum to a value that deviates from 1.0 by > WEIGHT_TOLERANCE,
        indicating boundary misalignment between the TopoJSON and TIGER/Line
    """
    weight_sums = intersected.groupby("bg_geoid")["weight"].sum()

    covered_count = len(weight_sums)
    uncovered_count = bg_count - covered_count
    if uncovered_count > 0:
        logger.warning(
            f"  {uncovered_count} of {bg_count} block groups had no precinct intersection. "
            "This is expected for water bodies and unpopulated areas."
        )

    bad = weight_sums[abs(weight_sums - 1.0) > WEIGHT_TOLERANCE]
    if not bad.empty:
        logger.warning(
            f"  {len(bad)} block groups have weight sums deviating from 1.0 by "
            f">{WEIGHT_TOLERANCE:.0%} — likely boundary misalignment between "
            f"TopoJSON and TIGER/Line. Max deviation: {abs(bad - 1.0).max():.4f}. "
            f"Affected BGs (first 10): {bad.index.tolist()[:10]}"
            f"{'...' if len(bad) > 10 else ''}"
        )

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def build_crosswalk(state_fips: str, all_precincts: gpd.GeoDataFrame = None) -> bool:
    """
    Build the block-group-to-precinct crosswalk for one state.

    Args:
        state_fips:     Zero-padded 2-digit FIPS string, e.g. "51" for Virginia.
        all_precincts:  Optional pre-loaded full precinct GeoDataFrame. When calling
                        build_crosswalk() for a single state, pass None and the
                        TopoJSON will be loaded automatically. When calling from
                        build_all_states(), pass the pre-loaded GDF to avoid
                        re-reading the file for every state.

    Returns True on success, False on failure.
    Output: data/crosswalks/{state_fips}_bg_to_precinct.csv
    """
    os.makedirs(CROSSWALK_DIR, exist_ok=True)
    abbr = FIPS_TO_ABBR.get(state_fips, state_fips)
    logger.info(f"\n--- Building crosswalk for {abbr} (FIPS: {state_fips}) ---")

    try:
        # 1. Load precincts
        if all_precincts is None:
            logger.info("  Loading TopoJSON (single-state mode)...")
            all_precincts = _read_topojson(TOPOJSON_PATH)

        precincts = _load_precincts_for_state(state_fips, all_precincts)
        if precincts.empty:
            return False

        # 2. Download Census block group boundaries
        block_groups = _load_block_groups(state_fips)
        if block_groups.empty:
            logger.error(f"  No block groups returned for state {state_fips}.")
            return False

        # 3. Project both to equal-area CRS for accurate area calculations
        precincts_proj = precincts.to_crs(AREA_CRS)
        bg_proj = block_groups.to_crs(AREA_CRS)

        # 4. Record block group total areas before intersection
        bg_proj = bg_proj.copy()
        bg_proj["bg_area"] = bg_proj.geometry.area

        # 5. Spatial intersection — every (BG, precinct) pair that overlaps
        logger.info(
            f"  Computing spatial intersection "
            f"({len(bg_proj)} BGs × {len(precincts_proj)} precincts)..."
        )
        intersected = gpd.overlay(
            bg_proj[["bg_geoid", "bg_area", "geometry"]],
            precincts_proj[["precinct_geoid", "official_boundary", "geometry"]],
            how="intersection",
            keep_geom_type=False,
        )

        # 6. Calculate intersection areas and weights
        intersected["intersection_area"] = intersected.geometry.area
        intersected["weight"] = intersected["intersection_area"] / intersected["bg_area"]

        # Drop zero-area slivers from floating-point edge effects
        intersected = intersected[intersected["weight"] > 1e-9].copy()

        if intersected.empty:
            logger.error(f"  No BG-precinct intersections found for {state_fips}. "
                         "Check that precinct and block group boundaries overlap.")
            return False

        # 7. Validate weight sums per block group
        _validate_weights(intersected, bg_count=len(bg_proj))

        # 8. Save crosswalk CSV
        output_path = os.path.join(CROSSWALK_DIR, f"{state_fips}_bg_to_precinct.csv")
        result = intersected[["bg_geoid", "precinct_geoid", "weight", "official_boundary"]].copy()
        result["weight"] = result["weight"].round(6)
        result = result.sort_values(["bg_geoid", "weight"], ascending=[True, False])
        result.to_csv(output_path, index=False)

        logger.info(
            f"  Saved {len(result)} BG-precinct pairs to {output_path}. "
            f"({result['bg_geoid'].nunique()} BGs, {result['precinct_geoid'].nunique()} precincts)"
        )
        return True

    except Exception as e:
        logger.error(f"  Failed to build crosswalk for {state_fips}: {e}", exc_info=True)
        return False


def build_all_states() -> dict:
    """
    Build crosswalks for every state present in the TopoJSON file.

    Loads the TopoJSON once, then iterates through all unique state abbreviations.
    Returns a dict of {state_fips: success_bool}.
    """
    logger.info(f"Loading TopoJSON from {TOPOJSON_PATH} ...")
    all_precincts = _read_topojson(TOPOJSON_PATH)

    abbrs = sorted(all_precincts["state"].str.upper().unique())
    logger.info(f"Found {len(abbrs)} states in TopoJSON: {abbrs}")

    results = {}
    for abbr in abbrs:
        fips = ABBR_TO_FIPS.get(abbr)
        if not fips:
            logger.warning(f"No FIPS found for abbreviation '{abbr}', skipping.")
            results[abbr] = False
            continue
        results[fips] = build_crosswalk(fips, all_precincts=all_precincts)

    succeeded = sum(v for v in results.values())
    logger.info(f"\nBuild complete: {succeeded}/{len(results)} states succeeded.")
    return results
