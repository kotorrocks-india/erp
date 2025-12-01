# screens/academic_years/utils.py
from __future__ import annotations

import re
import datetime
import logging
import json
import streamlit as st

logger = logging.getLogger(__name__)

# --- Fallback error handler (if faculty utils not available) ---
try:
    from screens.faculty.utils import _handle_error  # type: ignore
except Exception:  # pragma: no cover - fallback
    def _handle_error(e: Exception, user_message: str = "An error occurred.") -> None:
        logger.error(user_message, exc_info=True)
        st.error(user_message)


# --------------------------------------------------------------------
# Academic year helpers - ENHANCED VERSION (No schema changes needed)
# --------------------------------------------------------------------

# Regular AY pattern: Allows "AY" prefix (optional), dash or slash separator
# Examples: 2025-26, 2025/26, AY2025-26, AY2025/26
AY_CODE_PATTERN = re.compile(r"^(?:[Aa][Yy])?\d{4}[-/]\d{2}$")

# Short-term course pattern: ST prefix followed by 4-digit year
# Example: ST2025
ST_COURSE_PATTERN = re.compile(r"^[Ss][Tt]\d{4}$")


def is_valid_ay_code(ay_code: str) -> bool:
    """
    Validate the basic AY code shape.
    Accepts:
    - Regular AY: 2025-26, 2025/26, AY2025-26, AY2025/26
    - Short-term: ST2025, st2025
    """
    if not ay_code:
        return False
    return bool(AY_CODE_PATTERN.match(ay_code) or ST_COURSE_PATTERN.match(ay_code))


def is_short_term_course(ay_code: str) -> bool:
    """Check if the AY code represents a short-term course."""
    return bool(ay_code and ST_COURSE_PATTERN.match(ay_code))


def parse_ay_code(ay_code: str) -> dict:
    """
    Parse an AY code and return its components.
    
    Returns:
    -------
    dict with keys:
        - is_short_term: bool
        - start_year: int
        - end_year: int (same as start_year for short-term)
        - prefix: str ("AY", "ST", or "")
        - separator: str ("-", "/", or "")
        - formatted_code: str (normalized format)
    """
    if not ay_code:
        return None
    
    code = str(ay_code).strip()
    
    # Check for short-term course
    if ST_COURSE_PATTERN.match(code):
        year = int(code[-4:])
        return {
            "is_short_term": True,
            "start_year": year,
            "end_year": year,
            "prefix": code[:2].upper(),
            "separator": "",
            "formatted_code": f"ST{year}"
        }
    
    # Check for regular AY
    if AY_CODE_PATTERN.match(code):
        # Extract prefix (AY or empty)
        prefix = ""
        if code.upper().startswith("AY"):
            prefix = "AY"
            code = code[2:]
        
        # Determine separator
        separator = "-" if "-" in code else "/"
        
        # Split and parse years
        parts = code.split(separator)
        start_year = int(parts[0])
        end_year_short = int(parts[1])
        
        # Convert 2-digit year to 4-digit
        # Assume years are in 2000s range
        end_year = 2000 + end_year_short
        
        return {
            "is_short_term": False,
            "start_year": start_year,
            "end_year": end_year,
            "prefix": prefix,
            "separator": separator,
            "formatted_code": f"{prefix}{start_year}{separator}{end_year_short:02d}"
        }
    
    return None


def validate_ay_code_structure(ay_code: str) -> list[str]:
    """
    Validate AY code structure and return any errors.
    
    Returns:
    -------
    List of error messages (empty if valid)
    """
    errors = []
    
    if not ay_code:
        errors.append("AY Code is required.")
        return errors
    
    parsed = parse_ay_code(ay_code)
    if not parsed:
        errors.append(
            "Invalid AY Code format. Use: 2025-26, 2025/26, AY2025-26, "
            "AY2025/26 (for regular) or ST2025 (for short-term courses)."
        )
        return errors
    
    # Validate year continuity for regular AY
    if not parsed["is_short_term"]:
        if parsed["end_year"] != parsed["start_year"] + 1:
            errors.append(
                f"End year must be exactly one year after start year. "
                f"Expected {parsed['start_year'] + 1}, got {parsed['end_year']}."
            )
    
    return errors


def validate_date_format(date_str: str) -> bool:
    """True if date_str is ISO-8601 (YYYY-MM-DD)."""
    try:
        datetime.date.fromisoformat(date_str)
        return True
    except Exception:
        return False


def parse_date_range(start_date, end_date):
    """Parse date range - original function preserved for compatibility."""
    return start_date, end_date


def validate_ay_dates(
    start_date: datetime.date,
    end_date: datetime.date,
    ay_code: str = None
) -> list[str]:
    """
    Comprehensive validation of AY dates.
    
    MODIFIED: Year alignment checks are now WARNINGS only, not blocking errors.
    
    Checks:
    - Start date is before end date (ERROR)
    - Duration doesn't exceed 365 days (WARNING)
    - Dates align with AY code years (WARNING - not blocking)
    - For short-term: both dates must be in the same year (WARNING)
    """
    errors = []
    
    if not start_date or not end_date:
        errors.append("Both start and end dates are required.")
        return errors
    
    # Check date order - BLOCKING ERROR
    if start_date >= end_date:
        errors.append("Start date must be before end date.")
        return errors
    
    # Calculate duration
    duration = (end_date - start_date).days
    
    # Duration check - WARNING only
    if duration > 365:
        # Using info emoji to indicate this is a warning, not an error
        pass  # Don't add to errors list - just log it
        logger.warning(f"Duration ({duration} days) exceeds 365 days for AY {ay_code}")
    
    # If AY code is provided, validate alignment - ALL AS WARNINGS
    if ay_code:
        parsed = parse_ay_code(ay_code)
        if parsed:
            if parsed["is_short_term"]:
                # Short-term: both dates should ideally be in the specified year
                expected_year = parsed["start_year"]
                if start_date.year != expected_year or end_date.year != expected_year:
                    # WARNING only - log but don't block
                    logger.warning(
                        f"Short-term course {ay_code}: dates span outside {expected_year} "
                        f"(start: {start_date.year}, end: {end_date.year})"
                    )
            else:
                # Regular AY: dates should ideally span the specified years
                start_year = parsed["start_year"]
                end_year = parsed["end_year"]
                
                # Year alignment checks - WARNING only
                if start_date.year < start_year - 1 or start_date.year > start_year:
                    logger.warning(
                        f"For {ay_code}, start date year is {start_date.year}, "
                        f"expected around {start_year}"
                    )
                
                if end_date.year < end_year or end_date.year > end_year + 1:
                    logger.warning(
                        f"For {ay_code}, end date year is {end_date.year}, "
                        f"expected around {end_year}"
                    )
    
    return errors  # Only blocking errors, no warnings


def _get_year_from_ay_code(ay_code: str) -> int | None:
    """
    Extract the 4-digit "start year" from an AY code.

    Examples
    --------
    - "2025-26"      -> 2025
    - "AY2025/26"    -> 2025
    - "ST2025"       -> 2025
    """
    parsed = parse_ay_code(ay_code)
    return parsed["start_year"] if parsed else None


def get_next_ay_code(current_ay_code: str, format_preference: str = "auto") -> str | None:
    """
    Generates the next AY code from a given code.
    
    Parameters:
    ----------
    current_ay_code : str
        Current AY code
    format_preference : str
        "dash" for "-", "slash" for "/", "auto" to preserve current format
    
    Returns:
    -------
    Next AY code in the specified format, or None if invalid
    """
    parsed = parse_ay_code(current_ay_code)
    if not parsed:
        return None
    
    if parsed["is_short_term"]:
        # Next short-term is next year
        next_year = parsed["start_year"] + 1
        return f"ST{next_year}"
    else:
        # Next regular AY
        next_start = parsed["start_year"] + 1
        next_end = parsed["end_year"] + 1
        
        # Determine separator
        if format_preference == "auto":
            sep = parsed["separator"]
        else:
            sep = "-" if format_preference == "dash" else "/"
        
        # Preserve prefix if present
        prefix = parsed["prefix"]
        
        return f"{prefix}{next_start}{sep}{next_end % 100:02d}"


def generate_ay_range(start_ay: str, num_years: int) -> list[str]:
    """
    Generate a list of consecutive AY codes starting from `start_ay`.

    Example
    -------
    generate_ay_range("2024-25", 3) -> ["2024-25", "2025-26", "2026-27"]
    generate_ay_range("ST2024", 3) -> ["ST2024", "ST2025", "ST2026"]
    """
    if not is_valid_ay_code(start_ay):
        return []
    
    out: list[str] = []
    cur = start_ay
    for _ in range(num_years):
        out.append(cur)
        cur = get_next_ay_code(cur, format_preference="auto")
        if not cur:
            break
    return out


def format_ay_code(
    start_year: int,
    is_short_term: bool = False,
    prefix: bool = True,
    separator: str = "-"
) -> str:
    """
    Generate a properly formatted AY code.
    
    Parameters:
    ----------
    start_year : int
        The starting year
    is_short_term : bool
        Whether this is a short-term course
    prefix : bool
        Whether to include "AY" or "ST" prefix
    separator : str
        "-" or "/" (ignored for short-term)
    
    Returns:
    -------
    Formatted AY code
    """
    if is_short_term:
        return f"ST{start_year}" if prefix else f"{start_year}"
    else:
        end_year = start_year + 1
        pfx = "AY" if prefix else ""
        return f"{pfx}{start_year}{separator}{end_year % 100:02d}"


def get_ay_status_display(status: str) -> str:
    """Return a user-friendly display for AY status."""
    icons = {
        "planned": "🟡 Planned",
        "open": "🟢 Open",
        "closed": "🔴 Closed"
    }
    return icons.get(status, status)


# --------------------------------------------------------------------
# Calendar profile helpers
# --------------------------------------------------------------------


def _mmdd_to_date(
    ay_start_year: int,
    mmdd: str,
    anchor_mmdd: str | None = None,
) -> datetime.date:
    """
    Map "MM-DD" to a concrete date within the AY span.

    If `anchor_mmdd` is provided, we treat that month/day as the boundary
    between "this AY's calendar year" and "next AY's calendar year":

        - Dates >= anchor_mmdd belong to `ay_start_year`
        - Dates <  anchor_mmdd belong to `ay_start_year + 1`

    This lets a profile whose anchor is "06-15" (June 15) represent an
    AY that runs June -> next April, for example.

    If no anchor is provided, we fall back to the previous behaviour
    where July (month=7) is the year boundary.
    """
    mm, dd = map(int, mmdd.split("-"))

    if anchor_mmdd:
        a_mm, a_dd = map(int, anchor_mmdd.split("-"))
        if (mm, dd) >= (a_mm, a_dd):
            year = ay_start_year
        else:
            year = ay_start_year + 1
    else:
        # Legacy behaviour: everything from July onwards is in ay_start_year
        year = ay_start_year if mm >= 7 else ay_start_year + 1

    return datetime.date(year, mm, dd)


def compute_term_windows_for_ay(
    profile: dict,
    ay_code: str,
    shift_days: int = 0,
) -> list[dict]:
    """
    Given a stored calendar profile (with JSON spec) and AY code, produce
    concrete term windows:

        [{ "label", "start_date", "end_date" }, ...]

    The profile is expected to contain:
        - term_spec_json: JSON list of {label, start_mmdd, end_mmdd}
        - anchor_mmdd:    string "MM-DD" used as year boundary (optional)

    The same logic applies to *all* terms in the profile, not just a
    specific semester (e.g. 9 or 10).
    """
    if not is_valid_ay_code(ay_code):
        raise ValueError("Invalid AY code.")
    if shift_days < -30 or shift_days > 30:
        raise ValueError("shift_days must be between -30 and +30.")

    # May raise if malformed, intentionally.
    spec = json.loads(profile.get("term_spec_json") or "[]")

    ay_start_year = _get_year_from_ay_code(ay_code)
    if ay_start_year is None:
        raise ValueError("Invalid AY code format for year extraction.")

    anchor_mmdd = profile.get("anchor_mmdd")

    results: list[dict] = []
    for idx, term in enumerate(spec):
        label = term.get("label") or f"Term {idx + 1}"
        start_mmdd = term["start_mmdd"]
        end_mmdd = term["end_mmdd"]

        start_dt = _mmdd_to_date(ay_start_year, start_mmdd, anchor_mmdd)
        end_dt = _mmdd_to_date(ay_start_year, end_mmdd, anchor_mmdd)

        # If computed end < start (e.g. a wrap over New Year), bump end one year.
        if end_dt < start_dt:
            end_dt = datetime.date(end_dt.year + 1, end_dt.month, end_dt.day)

        if shift_days:
            delta = datetime.timedelta(days=shift_days)
            start_dt += delta
            end_dt += delta

        results.append(
            {
                "label": label,
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat(),
            }
        )

    return results
