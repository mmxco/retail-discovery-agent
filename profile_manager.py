"""
Persistent Target Account Profile Manager
Handles reading, writing, updating, and deleting custom prospect profiles
in a local JSON file (saved_profiles.json).
"""

import os
import json
import logging
import tempfile
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "saved_profiles.json"
)


def load_saved_profiles(filepath: str = DEFAULT_PROFILES_FILE) -> Dict[str, Dict[str, Any]]:
    """
    Loads saved target account profiles from the local JSON file.
    Returns a dictionary of {profile_key: profile_data_dict}.
    """
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning(f"Unexpected data format in {filepath}, expected dict, got {type(data)}")
            return {}
    except Exception as e:
        logger.error(f"Error loading saved profiles from {filepath}: {e}")
        return {}


def save_profile(
    profile_data: Dict[str, Any],
    profile_key: Optional[str] = None,
    filepath: str = DEFAULT_PROFILES_FILE,
) -> str:
    """
    Saves or updates a target account profile in the local JSON storage.
    If profile_key is not specified, derives one from the DBA/brand name or domain:
    '[Saved] {dba}'

    Returns the assigned profile_key.
    """
    profiles = load_saved_profiles(filepath)

    dba = (profile_data.get("dba") or "").strip()
    domain = (profile_data.get("domain") or "").strip()

    if not profile_key:
        display_name = dba or domain or "Unnamed Prospect"
        if not display_name.startswith("[Saved] "):
            profile_key = f"[Saved] {display_name}"
        else:
            profile_key = display_name

    # Standardize data structure
    cleaned_profile = {
        "domain": domain,
        "corporate_url": (profile_data.get("corporate_url") or "").strip(),
        "dba": dba,
        "careers_url": (profile_data.get("careers_url") or "").strip(),
        "revenue": (profile_data.get("revenue") or "").strip(),
        "headcount": (profile_data.get("headcount") or "").strip(),
        "bdr_notes": (profile_data.get("bdr_notes") or "").strip(),
    }

    profiles[profile_key] = cleaned_profile

    _write_profiles_atomically(profiles, filepath)
    logger.info(f"Successfully saved profile: {profile_key}")
    return profile_key


def delete_profile(profile_key: str, filepath: str = DEFAULT_PROFILES_FILE) -> bool:
    """
    Deletes a target account profile from local JSON storage.
    Returns True if deleted, False if not found.
    """
    profiles = load_saved_profiles(filepath)
    if profile_key in profiles:
        del profiles[profile_key]
        _write_profiles_atomically(profiles, filepath)
        logger.info(f"Successfully deleted profile: {profile_key}")
        return True
    return False


def _write_profiles_atomically(profiles: Dict[str, Dict[str, Any]], filepath: str) -> None:
    """Writes the profiles dictionary to disk atomically to prevent corruption."""
    dir_name = os.path.dirname(filepath) or "."
    os.makedirs(dir_name, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, filepath)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
