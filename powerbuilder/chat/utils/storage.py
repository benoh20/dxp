# powerbuilder/chat/utils/storage.py
"""
Unified storage abstraction layer.

All file reads and writes in the pipeline go through this module so the same
code runs unchanged in local development and in production on S3.

Backend selection
-----------------
Set the STORAGE_BACKEND environment variable:
  'local' (default) — all operations hit the local filesystem directly.
  's3'              — mapped paths go to S3; everything else falls back to local.

S3 path mapping rules (evaluated in order, relative paths only)
---------------------------------------------------------------
  data/election_results/* → election_results/*    (per-state master CSVs)
  data/crosswalks/*       → crosswalks/*           (BG-to-precinct crosswalk files)
  chat/precinct_shapefiles/* → shapefiles/*        (TopoJSON and other spatial files)
  data/cook_ratings.json  → cook_ratings.json      (Cook Political static ratings)

Any path that does NOT match one of the rules above is always handled by the
local filesystem, even when STORAGE_BACKEND='s3'. This covers temporary caches
(data/medsl_cache/) and any other local-only artifacts.

S3 credentials (required when STORAGE_BACKEND='s3')
----------------------------------------------------
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME

Public API
----------
  read_file(path)              -> bytes
  write_file(path, contents)   -> None
  file_exists(path)            -> bool
  read_dataframe(path, **kw)   -> pd.DataFrame   (kwargs forwarded to pd.read_csv/read_excel)
  write_dataframe(path, df)    -> None            (always index=False)
  read_geodataframe(path, **kw)-> gpd.GeoDataFrame  (uses sync_to_local internally)
  list_files(prefix)           -> list[str]
  sync_to_local(path)          -> str             (abs local path; downloads from S3 if needed)
"""

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()

# AWS / S3 credentials — only required when STORAGE_BACKEND == 's3'
_AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID")
_AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
_AWS_REGION            = os.environ.get("AWS_REGION", "us-east-1")
_S3_BUCKET_NAME        = os.environ.get("S3_BUCKET_NAME")

# Project root — two levels above this file (chat/utils/ → powerbuilder/)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# Local directory for sync_to_local() downloads
_LOCAL_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "cache")


# ---------------------------------------------------------------------------
# Path mapping helpers
# ---------------------------------------------------------------------------

def _to_s3_key(path: str) -> Optional[str]:
    """
    Map a relative local path to an S3 key.

    Returns None for paths that do not match any mapping rule — callers
    must then fall back to the local filesystem.

    Mapping rules (applied to forward-slash-normalised relative paths):
      data/election_results/* → election_results/*
      data/crosswalks/*       → crosswalks/*
      chat/precinct_shapefiles/* → shapefiles/*
      data/cook_ratings.json  → cook_ratings.json
    """
    p = path.replace("\\", "/")
    if p.startswith("data/election_results/"):
        return "election_results/" + p[len("data/election_results/"):]
    if p.startswith("data/crosswalks/"):
        return "crosswalks/" + p[len("data/crosswalks/"):]
    if p.startswith("chat/precinct_shapefiles/"):
        return "shapefiles/" + p[len("chat/precinct_shapefiles/"):]
    if p == "data/cook_ratings.json":
        return "cook_ratings.json"
    return None


def _to_local_path(path: str) -> str:
    """Resolve a path to an absolute local filesystem path."""
    if os.path.isabs(path):
        return path
    return os.path.join(_PROJECT_ROOT, path)


def _sync_cache_path(s3_key: str) -> str:
    """Return the local cache path for a given S3 key (flat, no subdirs)."""
    safe_name = s3_key.replace("/", "_")
    return os.path.join(_LOCAL_CACHE_DIR, safe_name)


# ---------------------------------------------------------------------------
# S3 client (lazy, singleton)
# ---------------------------------------------------------------------------

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=_AWS_ACCESS_KEY_ID,
            aws_secret_access_key=_AWS_SECRET_ACCESS_KEY,
            region_name=_AWS_REGION,
        )
    return _s3_client


# ---------------------------------------------------------------------------
# Core I/O
# ---------------------------------------------------------------------------

def read_file(path: str) -> bytes:
    """
    Read file contents as raw bytes.

    In S3 mode, mapped paths are fetched from S3. On S3 failure the function
    logs a warning and falls back to the local filesystem. Unmapped paths
    always use the local filesystem.
    """
    if STORAGE_BACKEND == "s3":
        key = _to_s3_key(path)
        if key:
            try:
                s3 = _get_s3_client()
                obj = s3.get_object(Bucket=_S3_BUCKET_NAME, Key=key)
                return obj["Body"].read()
            except Exception as exc:
                logger.warning(
                    f"Storage: S3 read failed for s3://{_S3_BUCKET_NAME}/{key} "
                    f"— falling back to local ({exc})"
                )
    with open(_to_local_path(path), "rb") as fh:
        return fh.read()


def write_file(path: str, contents: bytes) -> None:
    """
    Write raw bytes to a file.

    In S3 mode, mapped paths are uploaded to S3. Unmapped paths use the
    local filesystem. Parent directories are created automatically for
    local writes.
    """
    if STORAGE_BACKEND == "s3":
        key = _to_s3_key(path)
        if key:
            s3 = _get_s3_client()
            s3.put_object(Bucket=_S3_BUCKET_NAME, Key=key, Body=contents)
            return
    local = _to_local_path(path)
    parent = os.path.dirname(local)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(local, "wb") as fh:
        fh.write(contents)


def file_exists(path: str) -> bool:
    """
    Return True if the file exists.

    In S3 mode, mapped paths are checked in S3 first (HEAD request). If the
    HEAD request fails (including a 404), falls back to the local filesystem.
    Unmapped paths always check the local filesystem.
    """
    if STORAGE_BACKEND == "s3":
        key = _to_s3_key(path)
        if key:
            try:
                _get_s3_client().head_object(Bucket=_S3_BUCKET_NAME, Key=key)
                return True
            except Exception:
                pass
    return os.path.exists(_to_local_path(path))


# ---------------------------------------------------------------------------
# DataFrame I/O
# ---------------------------------------------------------------------------

def _infer_pandas_reader(path: str):
    """Return (reader_fn, is_excel) based on file extension."""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel, True
    return pd.read_csv, False


def read_dataframe(path: str, **kwargs):
    """
    Read a file into a pandas DataFrame.

    Format is inferred from the file extension:
      .csv / .tab / .tsv  → pd.read_csv  (comma-separated by default)
      .xlsx / .xls        → pd.read_excel

    Extra keyword arguments are forwarded directly to the pandas reader,
    allowing callers to pass dtype=, encoding=, low_memory=, sep=, etc.

    In S3 mode, mapped paths are read from S3 into a BytesIO buffer. On
    S3 failure the function falls back to the local filesystem. Unmapped
    paths always use the local filesystem.
    """
    import pandas as pd

    reader, is_excel = _infer_pandas_reader(path)

    if STORAGE_BACKEND == "s3":
        key = _to_s3_key(path)
        if key:
            try:
                s3  = _get_s3_client()
                obj = s3.get_object(Bucket=_S3_BUCKET_NAME, Key=key)
                buf = io.BytesIO(obj["Body"].read())
                return reader(buf, **kwargs)
            except Exception as exc:
                logger.warning(
                    f"Storage: S3 read_dataframe failed for s3://{_S3_BUCKET_NAME}/{key} "
                    f"— falling back to local ({exc})"
                )

    return reader(_to_local_path(path), **kwargs)


def write_dataframe(path: str, df) -> None:
    """
    Write a pandas DataFrame to a file (index=False always).

    Format is inferred from the file extension (.xlsx/.xls → Excel; all
    others → CSV). In S3 mode, mapped paths are uploaded to S3; unmapped
    paths and local mode write to the local filesystem.
    """
    import pandas as pd

    ext = os.path.splitext(path)[1].lower()
    is_excel = ext in (".xlsx", ".xls")

    if STORAGE_BACKEND == "s3":
        key = _to_s3_key(path)
        if key:
            buf = io.BytesIO()
            if is_excel:
                df.to_excel(buf, index=False)
            else:
                df.to_csv(buf, index=False)
            buf.seek(0)
            _get_s3_client().put_object(
                Bucket=_S3_BUCKET_NAME, Key=key, Body=buf.read()
            )
            return

    local = _to_local_path(path)
    parent = os.path.dirname(local)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if is_excel:
        df.to_excel(local, index=False)
    else:
        df.to_csv(local, index=False)


# ---------------------------------------------------------------------------
# GeoDataFrame I/O  (geopandas / fiona require a real file path)
# ---------------------------------------------------------------------------

def read_geodataframe(path: str, **kwargs):
    """
    Read a spatial file into a geopandas GeoDataFrame.

    Because geopandas/fiona requires a real filesystem path, this function
    always calls sync_to_local() first to ensure a local copy exists, then
    delegates to gpd.read_file(). Extra kwargs (e.g. layer=) are forwarded.
    """
    import geopandas as gpd
    local_path = sync_to_local(path)
    return gpd.read_file(local_path, **kwargs)


# ---------------------------------------------------------------------------
# Directory listing
# ---------------------------------------------------------------------------

def list_files(prefix: str) -> list:
    """
    Return a list of relative file paths whose path starts with prefix.

    In S3 mode, the prefix is mapped to an S3 key prefix and the bucket is
    listed. On failure, falls back to the local filesystem. In local mode (or
    for unmapped prefixes), the local directory is walked recursively.

    Returned paths use forward slashes and are relative to the project root.
    """
    if STORAGE_BACKEND == "s3":
        key_prefix = _to_s3_key(prefix)
        if key_prefix is not None:
            try:
                s3        = _get_s3_client()
                paginator = s3.get_paginator("list_objects_v2")
                keys      = []
                for page in paginator.paginate(Bucket=_S3_BUCKET_NAME, Prefix=key_prefix):
                    for obj in page.get("Contents", []):
                        keys.append(obj["Key"])
                return keys
            except Exception as exc:
                logger.warning(
                    f"Storage: S3 list_files failed for prefix '{key_prefix}' "
                    f"— falling back to local ({exc})"
                )

    local_dir = _to_local_path(prefix)
    if not os.path.isdir(local_dir):
        return []
    result = []
    for root, _, files in os.walk(local_dir):
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, _PROJECT_ROOT).replace("\\", "/")
            result.append(rel_path)
    return result


# ---------------------------------------------------------------------------
# Local sync  (for libraries that need a real file path)
# ---------------------------------------------------------------------------

def sync_to_local(path: str) -> str:
    """
    Ensure a file is available on the local filesystem and return its
    absolute path.

    Local mode: resolves the path against the project root and returns
    the absolute path without any network I/O.

    S3 mode: if the path maps to an S3 key, the file is downloaded to
    data/cache/ (flat directory, no subdirectories) the first time it
    is requested. Subsequent calls return the cached path without re-
    downloading. If the path does not map to S3, resolves locally.

    Use this function before passing a path to geopandas, fiona, or any
    other library that requires a real filesystem path.
    """
    if STORAGE_BACKEND != "s3":
        return _to_local_path(path)

    key = _to_s3_key(path)
    if not key:
        return _to_local_path(path)

    local_cache = _sync_cache_path(key)

    if not os.path.exists(local_cache):
        os.makedirs(_LOCAL_CACHE_DIR, exist_ok=True)
        logger.info(
            f"Storage: syncing s3://{_S3_BUCKET_NAME}/{key} → {local_cache}"
        )
        _get_s3_client().download_file(_S3_BUCKET_NAME, key, local_cache)

    return local_cache
