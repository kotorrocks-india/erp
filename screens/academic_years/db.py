# screens/academic_years/db.py
# SIMPLIFIED VERSION - Using direct batch_term_dates, no calendar profiles/assignments
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Connection
import json
import datetime

# -----------------------------
# Low-level execution helpers
# -----------------------------

def _exec(conn: Connection, sql: str, params: Optional[Dict[str, Any]] = None):
    return conn.execute(sa_text(sql), params or {})

def _table_exists(conn: Connection, table: str) -> bool:
    try:
        rows = conn.execute(sa_text(f"PRAGMA table_info({table})")).fetchall()
        return len(rows) > 0
    except Exception:
        return False

def _col_exists(conn: Connection, table: str, col: str) -> bool:
    try:
        rows = conn.execute(sa_text(f"PRAGMA table_info({table})")).fetchall()
        names = {r[1].lower() for r in rows}
        return col.lower() in names
    except Exception:
        return False

# -----------------------------
# Academic Years (CRUD + utils) - UNCHANGED
# -----------------------------

def get_all_ays(
    conn: Connection,
    status_filter: Optional[List[str]] = None,
    search_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "academic_years"):
        return []
    where = ["1=1"]
    params: Dict[str, Any] = {}
    if status_filter:
        allowed = [s for s in status_filter if s in ("planned", "open", "closed")]
        if allowed:
            where.append("status IN :st")
            params["st"] = tuple(allowed)
    if search_query:
        where.append("ay_code LIKE :q")
        params["q"] = f"%{search_query}%"
    rows = _exec(
        conn,
        """
        SELECT ay_code AS code, start_date, end_date, status, updated_at
        FROM academic_years
        WHERE """ + " AND ".join(where) + """
        ORDER BY start_date DESC
    """,
        params,
    ).fetchall()
    return [dict(getattr(r, "_mapping", r)) for r in rows]

def get_ay_by_code(conn: Connection, code: str) -> Optional[Dict[str, Any]]:
    if not _table_exists(conn, "academic_years"):
        return None
    row = _exec(
        conn,
        """
        SELECT ay_code AS code, start_date, end_date, status, updated_at
        FROM academic_years WHERE ay_code=:c
    """,
        {"c": code},
    ).fetchone()
    return dict(getattr(row, "_mapping", row)) if row else None

def get_latest_ay_code(conn: Connection) -> Optional[str]:
    if not _table_exists(conn, "academic_years"):
        return None
    row = _exec(
        conn,
        """
        SELECT ay_code FROM academic_years
        WHERE start_date IS NOT NULL
        ORDER BY start_date DESC LIMIT 1
    """,
    ).fetchone()
    return row[0] if row else None

def _log_ay_audit(
    conn: Connection,
    ay_code: str,
    action: str,
    actor: str,
    note: Optional[str] = None,
    changed_fields: Optional[str] = None,
):
    if not _table_exists(conn, "academic_years_audit"):
        return
    _exec(
        conn,
        """
        INSERT INTO academic_years_audit(ay_code, action, note, changed_fields, actor)
        VALUES (:ayc, :act, :note, :fields, :actor)
    """,
        {"ayc": ay_code, "act": action, "note": note, "fields": changed_fields, "actor": actor},
    )

def insert_ay(
    conn: Connection,
    ay_code: str,
    start_date,
    end_date,
    status: str = "planned",
    actor: str = "system",
) -> None:
    _exec(
        conn,
        """
        INSERT INTO academic_years(ay_code, start_date, end_date, status)
        VALUES (:c, :s, :e, :st)
    """,
        {"c": ay_code, "s": start_date, "e": end_date, "st": status},
    )
    _log_ay_audit(
        conn,
        ay_code,
        "create",
        actor,
        note=f"Created with dates {start_date} to {end_date}",
    )

def update_ay_dates(
    conn: Connection,
    ay_code: str,
    start_date,
    end_date,
    actor: str = "system",
) -> None:
    _exec(
        conn,
        """
        UPDATE academic_years
           SET start_date=:s, end_date=:e, updated_at=CURRENT_TIMESTAMP
         WHERE ay_code=:c
    """,
        {"c": ay_code, "s": start_date, "e": end_date},
    )
    _log_ay_audit(
        conn,
        ay_code,
        "edit",
        actor,
        changed_fields=f'{{"start_date": "{start_date}", "end_date": "{end_date}"}}',
    )

def update_ay_status(
    conn: Connection,
    ay_code: str,
    new_status: str,
    actor: str = "system",
    reason: Optional[str] = None,
) -> None:
    _exec(
        conn,
        """
        UPDATE academic_years
           SET status=:st, updated_at=CURRENT_TIMESTAMP
         WHERE ay_code=:c
    """,
        {"c": ay_code, "st": new_status},
    )
    _log_ay_audit(
        conn,
        ay_code,
        new_status,
        actor,
        note=f"Changed status to {new_status}",
        changed_fields=f'{{"status": "{new_status}"}}',
    )

def delete_ay(conn: Connection, ay_code: str, actor: str = "system") -> None:
    _log_ay_audit(conn, ay_code, "delete", actor, note="Record deleted")
    _exec(conn, "DELETE FROM academic_years WHERE ay_code=:c", {"c": ay_code})

def check_overlap(
    conn: Connection,
    start_date,
    end_date,
    exclude_code: Optional[str] = None,
) -> Optional[str]:
    if not _table_exists(conn, "academic_years"):
        return None
    row = _exec(
        conn,
        """
        SELECT ay_code
          FROM academic_years
         WHERE (:exclude IS NULL OR ay_code <> :exclude)
           AND start_date IS NOT NULL
           AND end_date   IS NOT NULL
           AND start_date < end_date
           AND start_date <= :end
           AND end_date   >= :start
         ORDER BY start_date DESC
         LIMIT 1
    """,
        {"exclude": exclude_code, "start": start_date, "end": end_date},
    ).fetchone()
    return row[0] if row else None

# -----------------------------
# Degrees / Programs / Branches - UNCHANGED
# -----------------------------

def get_all_degrees(conn: Connection) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "degrees"):
        return []
    rows = _exec(
        conn,
        """
        SELECT code
          FROM degrees
         WHERE active=1
         ORDER BY sort_order, code
    """,
    ).fetchall()
    return [dict(code=r[0]) for r in rows]

def get_degree_duration(conn: Connection, degree_code: str) -> int:
    default_duration = 10
    if not _table_exists(conn, "degree_semester_struct"):
        return default_duration
    if not _col_exists(conn, "degree_semester_struct", "years"):
        return default_duration
    row = _exec(
        conn,
        """
        SELECT years 
        FROM degree_semester_struct 
        WHERE degree_code=:c AND active=1
    """,
        {"c": degree_code},
    ).fetchone()
    if row and row[0] and row[0] > 0:
        return int(row[0])
    else:
        return default_duration

def get_degree_terms_per_year(conn: Connection, degree_code: str) -> int:
    default_terms = 2
    if not _table_exists(conn, "degree_semester_struct"):
        return default_terms
    if not _col_exists(conn, "degree_semester_struct", "terms_per_year"):
        return default_terms
    row = _exec(
        conn,
        """
        SELECT terms_per_year 
        FROM degree_semester_struct 
        WHERE degree_code=:c AND active=1
    """,
        {"c": degree_code},
    ).fetchone()
    if row and row[0] and row[0] > 0:
        return int(row[0])
    else:
        return default_terms

def get_programs_for_degree(conn: Connection, degree_code: str) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "programs"):
        return []
    rows = _exec(
        conn,
        """
        SELECT program_code
          FROM programs
         WHERE lower(degree_code)=lower(:d) AND active=1
         ORDER BY sort_order, program_code
    """,
        {"d": degree_code},
    ).fetchall()
    return [dict(program_code=r[0]) for r in rows]

def get_branches_for_degree_program(
    conn: Connection,
    degree_code: str,
    program_code: Optional[str],
) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "branches"):
        return []
    if _col_exists(conn, "branches", "program_id") and _table_exists(conn, "programs"):
        if program_code:
            rows = _exec(
                conn,
                """
                SELECT b.branch_code
                  FROM branches b
                  JOIN programs p ON p.id=b.program_id
                 WHERE lower(p.degree_code)=lower(:d)
                   AND lower(p.program_code)=lower(:p)
                   AND b.active=1
                 ORDER BY b.sort_order, b.branch_code
            """,
                {"d": degree_code, "p": program_code},
            ).fetchall()
        else:
            rows = _exec(
                conn,
                """
                SELECT b.branch_code
                  FROM branches b
                  JOIN programs p ON p.id=b.program_id
                 WHERE lower(p.degree_code)=lower(:d)
                   AND b.active=1
                 ORDER BY b.sort_order, b.branch_code
            """,
                {"d": degree_code},
            ).fetchall()
        return [dict(branch_code=r[0]) for r in rows]
    if program_code and _col_exists(conn, "branches", "program_code"):
        rows = _exec(
            conn,
            """
            SELECT branch_code
              FROM branches
             WHERE lower(degree_code)=lower(:d)
               AND lower(program_code)=lower(:p)
               AND active=1
             ORDER BY sort_order, branch_code
        """,
            {"d": degree_code, "p": program_code},
        ).fetchall()
    else:
        rows = _exec(
            conn,
            """
            SELECT branch_code
              FROM branches
             WHERE lower(degree_code)=lower(:d) AND active=1
             ORDER BY sort_order, branch_code
        """,
            {"d": degree_code},
        ).fetchall()
    return [dict(branch_code=r[0]) for r in rows]

# -----------------------------
# Binding / Scope Helpers (NEW)
# -----------------------------

def get_degree_binding_info(conn: Connection, degree_code: str) -> Dict[str, Any]:
    """
    Returns binding configuration for a degree.

    {
        "binding_mode": "degree" | "program" | "branch",
        "cg_program": 0/1,
        "cg_branch": 0/1,
    }

    - binding_mode comes from semester_binding (if present), default "degree"
    - cg_program / cg_branch come from degrees table (if present), default 0
    """
    degree_code = (degree_code or "").strip()

    # Default binding
    binding_mode = "degree"

    # 1️⃣ Resolve binding_mode from semester_binding, if available
    if degree_code and _table_exists(conn, "semester_binding"):
        row = _exec(
            conn,
            """
            SELECT binding_mode
              FROM semester_binding
             WHERE lower(degree_code) = lower(:d)
             LIMIT 1
            """,
            {"d": degree_code},
        ).fetchone()
        if row and row[0] in ("degree", "program", "branch"):
            binding_mode = row[0]

    cg_program = 0
    cg_branch = 0

    # 2️⃣ Optional flags from degrees.cg_program / degrees.cg_branch
    if degree_code and _table_exists(conn, "degrees"):
        if _col_exists(conn, "degrees", "cg_program"):
            row = _exec(
                conn,
                """
                SELECT cg_program
                  FROM degrees
                 WHERE lower(code) = lower(:d)
                 LIMIT 1
                """,
                {"d": degree_code},
            ).fetchone()
            if row and row[0]:
                try:
                    cg_program = int(row[0] or 0)
                except Exception:
                    cg_program = 1

        if _col_exists(conn, "degrees", "cg_branch"):
            row = _exec(
                conn,
                """
                SELECT cg_branch
                  FROM degrees
                 WHERE lower(code) = lower(:d)
                 LIMIT 1
                """,
                {"d": degree_code},
            ).fetchone()
            if row and row[0]:
                try:
                    cg_branch = int(row[0] or 0)
                except Exception:
                    cg_branch = 1

    return {
        "binding_mode": binding_mode,
        "cg_program": cg_program,
        "cg_branch": cg_branch,
    }

def build_scope_code(
    degree_code: str,
    binding_mode: str = "degree",
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
) -> Optional[str]:
    """
    Build a *calendar scope key* for use in batch_term_dates.degree_code.

    We deliberately *encode* program / branch into the degree_code field,
    without changing the schema:

        Degree scope : BSC
        Program scope: BSC|P:COMP
        Branch scope : BSC|P:COMP|B:AI

    Returns None if the required components for the chosen binding_mode
    are missing, so the caller can show a friendly message.
    """
    base = (degree_code or "").strip()
    if not base:
        return None

    mode = (binding_mode or "degree").lower()

    if mode == "degree":
        return base

    if mode == "program":
        if not program_code:
            return None
        return f"{base}|P:{program_code}"

    if mode == "branch":
        if not (program_code and branch_code):
            return None
        return f"{base}|P:{program_code}|B:{branch_code}"

    # Fallback: unknown binding → treat as degree-level
    return base

def extract_base_degree_code(scope_code: str) -> str:
    """
    Given a scope key like 'BSC|P:COMP|B:AI', return just the base degree code ('BSC').

    This is useful when batch-level tables (like degree_batches, student_enrollments)
    still use the *real* degree_code, while batch_term_dates may use scoped codes.
    """
    if not scope_code:
        return ""
    # Everything before first '|' is the base degree code.
    return str(scope_code).split("|", 1)[0]

# -----------------------------
# NEW: Direct Batch Term Dates Functions
# -----------------------------

def get_batch_term_dates(
    conn: Connection,
    degree_code: str,
    batch_code: str,
    ay_code: str,
    year_of_study: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get term dates for a specific batch/AY, optionally filtered by year.
    This REPLACES compute_terms_with_validation.
    """
    if not _table_exists(conn, "batch_term_dates"):
        return []
    
    where = ["degree_code = :d", "batch_code = :b", "ay_code = :ay"]
    params = {"d": degree_code, "b": batch_code, "ay": ay_code}
    
    if year_of_study is not None:
        where.append("year_of_study = :y")
        params["y"] = year_of_study
    
    rows = _exec(
        conn,
        f"""
        SELECT year_of_study, term_number, term_label, start_date, end_date
        FROM batch_term_dates
        WHERE {" AND ".join(where)}
        ORDER BY year_of_study, term_number
        """,
        params
    ).fetchall()
    
    results = []
    for r in rows:
        results.append({
            "year_of_study": r[0],
            "term_number": r[1],
            "label": r[2],
            "start_date": r[3],
            "end_date": r[4]
        })
    
    return results

def compute_terms_with_validation(
    conn: Connection,
    ay_code: str,
    degree_code: str,
    program_code: Optional[str],
    branch_code: Optional[str],
    progression_year: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    COMPATIBILITY WRAPPER for existing code.
    Now uses batch_term_dates instead of calendar profiles.
    
    Note: Since batch_term_dates is batch-specific, we need to know which batch.
    For the Assignment Preview (Batch Mode), the batch is selected by user.
    For Year/Semester Mode, we can't preview without knowing the batch.
    """
    warnings = []
    
    # We need to determine which batch to use
    # For now, return empty with a warning if we can't determine batch
    warnings.append(
        "⚠️ Term calculation now requires a specific batch. "
        "Use 'Batch Mode' in Assignment Preview to see actual term dates."
    )
    
    return [], warnings

# -----------------------------
# Batch / Student Helpers - UNCHANGED
# -----------------------------

def _db_get_batches_for_degree(
    conn: Connection,
    degree_code: str,
) -> List[Dict[str, Any]]:
    """Get all batches for a degree."""
    if not _table_exists(conn, "degree_batches"):
        return []
    
    rows = _exec(
        conn,
        """
        SELECT batch_code AS code, batch_name AS name
        FROM degree_batches
        WHERE degree_code = :d
        ORDER BY batch_code DESC
        """,
        {"d": degree_code}
    ).fetchall()
    
    return [dict(getattr(r, "_mapping", r)) for r in rows]

def _db_check_batch_has_students(
    conn: Connection,
    degree_code: str,
    batch_code: str,
) -> bool:
    """Check if batch has enrolled students."""
    if not _table_exists(conn, "student_enrollments"):
        return False
    if not _col_exists(conn, "student_enrollments", "batch"):
        return False
    
    row = _exec(
        conn,
        """
        SELECT 1 FROM student_enrollments
        WHERE degree_code = :d AND batch = :b
        LIMIT 1
        """,
        {"d": degree_code, "b": batch_code},
    ).fetchone()
    
    return row is not None

def get_semester_mapping_for_year(
    conn: Connection,
    degree_code: str,
    year_index: int,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
) -> Dict[int, Dict[str, Any]]:
    """
    Returns semester label mapping from semesters table.
    UNCHANGED - still used for semester labels.
    """
    if not _table_exists(conn, "semesters"):
        return {}
    
    binding_mode = "degree"
    if _table_exists(conn, "semester_binding"):
        row = _exec(
            conn,
            """
            SELECT binding_mode
              FROM semester_binding
             WHERE lower(degree_code)=lower(:d)
             LIMIT 1
        """,
            {"d": degree_code},
        ).fetchone()
        if row and row[0] in ("degree", "program", "branch"):
            binding_mode = row[0]
    
    program_id = None
    branch_id = None
    
    if binding_mode in ("program", "branch") and program_code:
        if _table_exists(conn, "programs") and _col_exists(conn, "programs", "program_code"):
            prow = _exec(
                conn,
                """
                SELECT id FROM programs
                 WHERE lower(degree_code)=lower(:d)
                   AND lower(program_code)=lower(:p)
                 LIMIT 1
            """,
                {"d": degree_code, "p": program_code},
            ).fetchone()
            if prow:
                program_id = prow[0]
    
    if binding_mode == "branch" and branch_code:
        if _table_exists(conn, "branches") and _col_exists(conn, "branches", "branch_code"):
            if program_id is not None:
                brow = _exec(
                    conn,
                    """
                    SELECT id FROM branches
                     WHERE lower(branch_code)=lower(:b)
                       AND program_id=:pid
                     LIMIT 1
                """,
                    {"b": branch_code, "pid": program_id},
                ).fetchone()
            else:
                brow = _exec(
                    conn,
                    """
                    SELECT b.id FROM branches b
                      JOIN programs p ON p.id=b.program_id
                     WHERE lower(b.branch_code)=lower(:b)
                       AND lower(p.degree_code)=lower(:d)
                     LIMIT 1
                """,
                    {"b": branch_code, "d": degree_code},
                ).fetchone()
            if brow:
                branch_id = brow[0]
    
    where = ["degree_code = :d", "year_index = :y", "active = 1"]
    params: Dict[str, Any] = {"d": degree_code, "y": year_index}
    
    if binding_mode == "degree":
        where.append("program_id IS NULL")
        where.append("branch_id IS NULL")
    elif binding_mode == "program" and program_id is not None:
        where.append("program_id = :pid")
        params["pid"] = program_id
    elif binding_mode == "branch" and branch_id is not None:
        where.append("branch_id = :bid")
        params["bid"] = branch_id
    
    rows = _exec(
        conn,
        f"""
        SELECT term_index, semester_number, label
          FROM semesters
         WHERE {' AND '.join(where)}
         ORDER BY term_index
        """,
        params,
    ).fetchall()
    
    mapping: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        try:
            m = getattr(r, "_mapping", r)
            term_idx = int(m["term_index"])
            sem_num = int(m["semester_number"])
            label = str(m["label"])
        except Exception:
            term_idx = int(r[0])
            sem_num = int(r[1])
            label = str(r[2])
        mapping[term_idx] = {
            "semester_number": sem_num,
            "label": label,
        }
    return mapping

# -----------------------------
# REMOVED FUNCTIONS (no longer needed)
# -----------------------------
# - get_assignable_calendar_profiles()
# - get_calendar_profile_by_id()
# - get_profile_term_count()
# - insert_calendar_profile()
# - insert_calendar_assignment()
# - _resolve_calendar_profile()
# - _get_default_calendar_code()
# - _get_calendar_profile_by_code()
