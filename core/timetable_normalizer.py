# core/timetable_normalizer.py
"""
Timetable Normalizer & Conflict Checker
---------------------------------------

Converts weekly_subject_distribution (slide 22) into a normalized,
slot-level representation (normalized_weekly_assignment) and runs
basic conflict checks, logging issues into timetable_conflicts.

Key concepts:

- weekly_subject_distribution:
    One row per (subject_offering, division), with:
      * Mon–Sat period counts or all-day block flags
      * Module dates / week range (optional)
      * Credit allocation + teaching load units
      * Faculty ids (JSON array) and room / lab info

- normalized_weekly_assignment:
    One row per "occupied slot":
      * Context (AY, degree, program, branch, CG, year, term, division)
      * offering_id, subject_code, subject_type
      * faculty_id (one per row)
      * day_of_week (1 = Mon, 6 = Sat)
      * period_index (1-based index for normal slots)
      * span_length (number of periods covered)
      * is_all_day_block (special flag for whole-day studios)
      * optional module/week scope and room/lab

- timetable_conflicts:
    Simple log of conflicts detected at slot-level:
      * conflict_type: e.g. 'faculty_double_booking', 'room_double_booking'
      * context + faculty_id / room_code
      * day_of_week, period_index
      * normalized_assignment_id (one of the offenders)
      * details: free-text description

USAGE (from a Streamlit screen or a backend job):

    from core.timetable_normalizer import (
        rebuild_normalized_for_context,
        detect_conflicts_for_context,
        rebuild_and_check_for_context,
    )

    engine = get_engine()

    rebuild_and_check_for_context(
        engine,
        ay_label="AY2024-25",
        degree_code="BARCH",
        year=4,
        term=1,
        program_code=None,
        branch_code=None,
        division_code="A",
    )

Design choices:
- day_of_week: 1 = Monday, ..., 6 = Saturday
- period_index: 1-based for "normal" slots.
- For all-day blocks, we set:
    is_all_day_block = 1
    period_index     = 0   (special value for "whole day")
    span_length      = 0   (or 1; we use 0 to signal it's not a normal period span)
"""


from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

DAY_FIELD_MAP: Dict[int, str] = {
    1: "mon_periods",
    2: "tue_periods",
    3: "wed_periods",
    4: "thu_periods",
    5: "fri_periods",
    6: "sat_periods",
}


@dataclass
class ContextFilter:
    ay_label: str
    degree_code: str
    year: int
    term: int
    program_code: Optional[str] = None
    branch_code: Optional[str] = None
    division_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_distribution_rows(
    engine: Engine,
    ctx: ContextFilter,
) -> List[Dict[str, Any]]:
    """
    Load weekly_subject_distribution rows for a given context.

    We intentionally keep this context fairly minimal; more fine-grained
    filtering (e.g. by CG) can be added later.
    """
    sql = sa_text(
        """
        SELECT
            id,
            offering_id,
            ay_label,
            degree_code,
            program_code,
            branch_code,
            curriculum_group_code,
            year,
            term,
            division_code,
            subject_code,
            subject_type,
            managed_in_elective_tt,
            slot_model,
            mon_periods,
            tue_periods,
            wed_periods,
            thu_periods,
            fri_periods,
            sat_periods,
            is_all_day_elective_block,
            extended_afternoon_days,
            module_start_date,
            module_end_date,
            week_start,
            week_end,
            credit_allocation_method,
            teaching_load_units_per_week,
            faculty_ids,
            room_code,
            lab_code,
            room_notes,
            notes
        FROM weekly_subject_distribution
        WHERE ay_label    = :ay_label
          AND degree_code = :degree_code
          AND year        = :year
          AND term        = :term
          AND (:program_code IS NULL OR program_code = :program_code)
          AND (:branch_code  IS NULL OR branch_code  = :branch_code)
          AND (:division_code IS NULL OR division_code = :division_code)
        """
    )
    params = {
        "ay_label": ctx.ay_label,
        "degree_code": ctx.degree_code,
        "year": ctx.year,
        "term": ctx.term,
        "program_code": ctx.program_code,
        "branch_code": ctx.branch_code,
        "division_code": ctx.division_code,
    }

    with engine.begin() as conn:
        rows = conn.execute(sql, params).mappings().all()

    result: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        # Parse JSON-ish fields
        if d.get("faculty_ids"):
            try:
                d["faculty_ids"] = json.loads(d["faculty_ids"])
            except Exception:
                d["faculty_ids"] = []
        if d.get("extended_afternoon_days"):
            try:
                d["extended_afternoon_days"] = json.loads(
                    d["extended_afternoon_days"]
                )
            except Exception:
                d["extended_afternoon_days"] = []
        result.append(d)
    return result


def _delete_normalized_rows(
    engine: Engine,
    ctx: ContextFilter,
) -> None:
    """
    Remove existing normalized_weekly_assignment rows for this context.

    This lets rebuild_normalized_for_context be idempotent: each call
    wipes and re-emits the normalized rows.
    """
    sql = sa_text(
        """
        DELETE FROM normalized_weekly_assignment
        WHERE ay_label    = :ay_label
          AND degree_code = :degree_code
          AND year        = :year
          AND term        = :term
          AND (:program_code IS NULL OR program_code = :program_code)
          AND (:branch_code  IS NULL OR branch_code  = :branch_code)
          AND (:division_code IS NULL OR division_code = :division_code)
        """
    )
    params = {
        "ay_label": ctx.ay_label,
        "degree_code": ctx.degree_code,
        "year": ctx.year,
        "term": ctx.term,
        "program_code": ctx.program_code,
        "branch_code": ctx.branch_code,
        "division_code": ctx.division_code,
    }
    with engine.begin() as conn:
        conn.execute(sql, params)


def _iter_slots_for_distribution_row(
    row: Dict[str, Any],
) -> Iterable[Dict[str, Any]]:
    """
    Expand a weekly_subject_distribution row into slot-level dicts.

    Conventions:
    - day_of_week: 1 = Mon, ..., 6 = Sat.
    - period_index: 1-based for normal slots.
    - span_length: always 1 for quick_counts; for more advanced models,
      we can extend this to represent multi-period spans.
    - All-day blocks:
        is_all_day_block = 1
        period_index     = 0
        span_length      = 0
    """
    slot_model = row.get("slot_model") or "quick_counts"
    is_all_day = bool(row.get("is_all_day_elective_block"))

    # If this row is managed in a separate elective timetable,
    # we don't emit any normalized rows here.
    if row.get("managed_in_elective_tt"):
        return

    faculty_ids: List[str] = row.get("faculty_ids") or []
    if not faculty_ids:
        # For conflict detection, we still want one row even if faculty is
        # not assigned yet; but in practice you might choose to skip these.
        faculty_ids = [None]  # type: ignore[list-item]

    common = {
        "ay_label": row["ay_label"],
        "degree_code": row["degree_code"],
        "program_code": row.get("program_code"),
        "branch_code": row.get("branch_code"),
        "curriculum_group_code": row.get("curriculum_group_code"),
        "year": row["year"],
        "term": row["term"],
        "division_code": row.get("division_code"),
        "offering_id": row["offering_id"],
        "subject_code": row["subject_code"],
        "subject_type": row["subject_type"],
        "module_start_date": row.get("module_start_date"),
        "module_end_date": row.get("module_end_date"),
        "week_start": row.get("week_start"),
        "week_end": row.get("week_end"),
        "room_code": row.get("room_code"),
        "lab_code": row.get("lab_code"),
    }

    if slot_model == "quick_counts":
        # Simple case: Mon–Sat counts, each period is 1 slot.
        for day in range(1, 7):
            field = DAY_FIELD_MAP[day]
            count = int(row.get(field) or 0)

            if is_all_day and count > 0:
                # Represent as a whole-day block; one slot per faculty
                for fid in faculty_ids:
                    yield {
                        **common,
                        "faculty_id": fid,
                        "day_of_week": day,
                        "period_index": 0,
                        "span_length": 0,
                        "is_all_day_block": 1,
                    }
                continue

            # Normal quick-count expansion
            for p in range(1, count + 1):
                for fid in faculty_ids:
                    yield {
                        **common,
                        "faculty_id": fid,
                        "day_of_week": day,
                        "period_index": p,
                        "span_length": 1,
                        "is_all_day_block": 0,
                    }

    else:
        # 'explicit_slots' model is not yet fully specified in your YAML,
        # so as a placeholder we treat it the same as quick_counts.
        # Later, you can add a JSON field (e.g. per_day_slots) and decode
        # it here to emit arbitrary slot patterns.
        for day in range(1, 7):
            field = DAY_FIELD_MAP[day]
            count = int(row.get(field) or 0)
            for p in range(1, count + 1):
                for fid in faculty_ids:
                    yield {
                        **common,
                        "faculty_id": fid,
                        "day_of_week": day,
                        "period_index": p,
                        "span_length": 1,
                        "is_all_day_block": 0,
                    }


def _insert_normalized_slots(
    engine: Engine,
    slots: Iterable[Dict[str, Any]],
) -> int:
    """
    Bulk-insert slot-level rows into normalized_weekly_assignment.

    Returns: number of rows inserted.
    """
    slots_list = list(slots)
    if not slots_list:
        return 0

    sql = sa_text(
        """
        INSERT INTO normalized_weekly_assignment (
            ay_label,
            degree_code,
            program_code,
            branch_code,
            curriculum_group_code,
            year,
            term,
            division_code,
            offering_id,
            subject_code,
            subject_type,
            faculty_id,
            day_of_week,
            period_index,
            span_length,
            is_all_day_block,
            module_start_date,
            module_end_date,
            week_start,
            week_end,
            room_code,
            lab_code
        ) VALUES (
            :ay_label,
            :degree_code,
            :program_code,
            :branch_code,
            :curriculum_group_code,
            :year,
            :term,
            :division_code,
            :offering_id,
            :subject_code,
            :subject_type,
            :faculty_id,
            :day_of_week,
            :period_index,
            :span_length,
            :is_all_day_block,
            :module_start_date,
            :module_end_date,
            :week_start,
            :week_end,
            :room_code,
            :lab_code
        )
        """
    )

    with engine.begin() as conn:
        conn.execute(sql, slots_list)
    return len(slots_list)


def _delete_conflicts_for_context(engine: Engine, ctx: ContextFilter) -> None:
    """
    Remove previously logged conflicts for this context.
    """
    sql = sa_text(
        """
        DELETE FROM timetable_conflicts
        WHERE ay_label    = :ay_label
          AND degree_code = :degree_code
          AND year        = :year
          AND term        = :term
          AND (:program_code IS NULL OR program_code = :program_code)
          AND (:branch_code  IS NULL OR branch_code  = :branch_code)
          AND (:division_code IS NULL OR division_code = :division_code)
        """
    )
    params = {
        "ay_label": ctx.ay_label,
        "degree_code": ctx.degree_code,
        "year": ctx.year,
        "term": ctx.term,
        "program_code": ctx.program_code,
        "branch_code": ctx.branch_code,
        "division_code": ctx.division_code,
    }
    with engine.begin() as conn:
        conn.execute(sql, params)


def _fetch_normalized_rows(
    engine: Engine,
    ctx: ContextFilter,
) -> List[Dict[str, Any]]:
    """
    Fetch normalized_weekly_assignment rows for a given context.
    """
    sql = sa_text(
        """
        SELECT
            id,
            ay_label,
            degree_code,
            program_code,
            branch_code,
            curriculum_group_code,
            year,
            term,
            division_code,
            offering_id,
            subject_code,
            subject_type,
            faculty_id,
            day_of_week,
            period_index,
            span_length,
            is_all_day_block,
            module_start_date,
            module_end_date,
            week_start,
            week_end,
            room_code,
            lab_code
        FROM normalized_weekly_assignment
        WHERE ay_label    = :ay_label
          AND degree_code = :degree_code
          AND year        = :year
          AND term        = :term
          AND (:program_code IS NULL OR program_code = :program_code)
          AND (:branch_code  IS NULL OR branch_code  = :branch_code)
          AND (:division_code IS NULL OR division_code = :division_code)
        """
    )
    params = {
        "ay_label": ctx.ay_label,
        "degree_code": ctx.degree_code,
        "year": ctx.year,
        "term": ctx.term,
        "program_code": ctx.program_code,
        "branch_code": ctx.branch_code,
        "division_code": ctx.division_code,
    }

    with engine.begin() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


def _atomic_slots_for_row(
    row: Dict[str, Any],
) -> Iterable[Tuple[int, int]]:
    """
    Expand a normalized_weekly_assignment row into atomic slots for
    conflict checks.

    Returns tuples (day_of_week, period_index).

    For:
    - Normal rows: one or more slots based on span_length.
    - All-day blocks: we treat 'period_index = 0' as a single atomic
      whole-day slot; it will conflict with any other all-day block
      with same day_of_week (and same faculty/room).
    """
    day = row["day_of_week"]
    base_period = int(row["period_index"])
    span = int(row.get("span_length") or 1)
    is_all_day = bool(row.get("is_all_day_block"))

    if is_all_day:
        yield (day, 0)
        return

    if span <= 1:
        yield (day, base_period)
        return

    for p in range(base_period, base_period + span):
        yield (day, p)


def _log_conflicts(
    engine: Engine,
    ctx: ContextFilter,
    conflicts: List[Dict[str, Any]],
) -> None:
    """
    Insert conflict rows into timetable_conflicts.
    """
    if not conflicts:
        return

    sql = sa_text(
        """
        INSERT INTO timetable_conflicts (
            ay_label,
            degree_code,
            program_code,
            branch_code,
            year,
            term,
            division_code,
            conflict_type,
            faculty_id,
            room_code,
            day_of_week,
            period_index,
            normalized_assignment_id,
            details
        ) VALUES (
            :ay_label,
            :degree_code,
            :program_code,
            :branch_code,
            :year,
            :term,
            :division_code,
            :conflict_type,
            :faculty_id,
            :room_code,
            :day_of_week,
            :period_index,
            :normalized_assignment_id,
            :details
        )
        """
    )

    with engine.begin() as conn:
        conn.execute(sql, conflicts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rebuild_normalized_for_context(
    engine: Engine,
    ay_label: str,
    degree_code: str,
    year: int,
    term: int,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    division_code: Optional[str] = None,
) -> int:
    """
    Rebuild normalized_weekly_assignment for a given context:

        (ay_label, degree_code, year, term[, program_code, branch_code, division_code])

    Steps:
    1) Clear existing normalized rows for this context.
    2) Fetch weekly_subject_distribution rows.
    3) Expand each into slot-level records.
    4) Insert all into normalized_weekly_assignment.

    Returns:
        Number of normalized rows inserted.
    """
    ctx = ContextFilter(
        ay_label=ay_label,
        degree_code=degree_code,
        year=year,
        term=term,
        program_code=program_code,
        branch_code=branch_code,
        division_code=division_code,
    )

    # 1) Delete existing
    _delete_normalized_rows(engine, ctx)

    # 2) Fetch distribution rows
    rows = _fetch_distribution_rows(engine, ctx)

    # 3) Expand to slots
    all_slots: List[Dict[str, Any]] = []
    for r in rows:
        all_slots.extend(list(_iter_slots_for_distribution_row(r)))

    # 4) Insert
    inserted = _insert_normalized_slots(engine, all_slots)
    return inserted


def detect_conflicts_for_context(
    engine: Engine,
    ay_label: str,
    degree_code: str,
    year: int,
    term: int,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    division_code: Optional[str] = None,
) -> int:
    """
    Detect basic timetable conflicts for a given context and write them
    into timetable_conflicts.

    Currently checks:
    - Faculty double-booking:
        two or more normalized rows with same faculty_id, day_of_week
        and overlapping atomic slot (period_index).
    - Room double-booking:
        two or more normalized rows with same room_code, day_of_week
        and overlapping atomic slot.

    Returns:
        Number of conflict rows inserted.
    """
    ctx = ContextFilter(
        ay_label=ay_label,
        degree_code=degree_code,
        year=year,
        term=term,
        program_code=program_code,
        branch_code=branch_code,
        division_code=division_code,
    )

    # 1) Clear existing conflicts
    _delete_conflicts_for_context(engine, ctx)

    # 2) Fetch normalized rows
    rows = _fetch_normalized_rows(engine, ctx)

    # Build maps: (faculty_id, day, period) → [row_ids]
    faculty_slots: Dict[Tuple[str, int, int], List[int]] = {}
    room_slots: Dict[Tuple[str, int, int], List[int]] = {}

    id_to_row: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        row_id = int(row["id"])
        id_to_row[row_id] = row

        # Faculty key
        fid = row.get("faculty_id")
        if fid:
            for day, p in _atomic_slots_for_row(row):
                key = (fid, day, p)
                faculty_slots.setdefault(key, []).append(row_id)

        # Room key
        room = row.get("room_code")
        if room:
            for day, p in _atomic_slots_for_row(row):
                key = (room, day, p)
                room_slots.setdefault(key, []).append(row_id)

    conflicts_to_insert: List[Dict[str, Any]] = []

    # 3) Faculty conflicts
    for (fid, day, p), ids in faculty_slots.items():
        if len(ids) <= 1:
            continue
        # Conflict detected
        involved = [id_to_row[i] for i in ids]
        first = involved[0]
        details = {
            "type": "faculty_double_booking",
            "faculty_id": fid,
            "day_of_week": day,
            "period_index": p,
            "normalized_ids": ids,
            "subjects": [r["subject_code"] for r in involved],
            "divisions": [r.get("division_code") for r in involved],
        }
        conflicts_to_insert.append(
            {
                "ay_label": first["ay_label"],
                "degree_code": first["degree_code"],
                "program_code": first.get("program_code"),
                "branch_code": first.get("branch_code"),
                "year": first["year"],
                "term": first["term"],
                "division_code": first.get("division_code"),
                "conflict_type": "faculty_double_booking",
                "faculty_id": fid,
                "room_code": None,
                "day_of_week": day,
                "period_index": p,
                "normalized_assignment_id": first["id"],
                "details": json.dumps(details),
            }
        )

    # 4) Room conflicts
    for (room, day, p), ids in room_slots.items():
        if len(ids) <= 1:
            continue
        involved = [id_to_row[i] for i in ids]
        first = involved[0]
        details = {
            "type": "room_double_booking",
            "room_code": room,
            "day_of_week": day,
            "period_index": p,
            "normalized_ids": ids,
            "subjects": [r["subject_code"] for r in involved],
            "divisions": [r.get("division_code") for r in involved],
            "faculty_ids": [r.get("faculty_id") for r in involved],
        }
        conflicts_to_insert.append(
            {
                "ay_label": first["ay_label"],
                "degree_code": first["degree_code"],
                "program_code": first.get("program_code"),
                "branch_code": first.get("branch_code"),
                "year": first["year"],
                "term": first["term"],
                "division_code": first.get("division_code"),
                "conflict_type": "room_double_booking",
                "faculty_id": None,
                "room_code": room,
                "day_of_week": day,
                "period_index": p,
                "normalized_assignment_id": first["id"],
                "details": json.dumps(details),
            }
        )

    _log_conflicts(engine, ctx, conflicts_to_insert)
    return len(conflicts_to_insert)


def rebuild_and_check_for_context(
    engine: Engine,
    ay_label: str,
    degree_code: str,
    year: int,
    term: int,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    division_code: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Convenience wrapper:

    1) Rebuild normalized_weekly_assignment for this context.
    2) Detect conflicts and log them.

    Returns:
        (normalized_rows_inserted, conflicts_logged)
    """
    n_slots = rebuild_normalized_for_context(
        engine,
        ay_label=ay_label,
        degree_code=degree_code,
        year=year,
        term=term,
        program_code=program_code,
        branch_code=branch_code,
        division_code=division_code,
    )

    n_conflicts = detect_conflicts_for_context(
        engine,
        ay_label=ay_label,
        degree_code=degree_code,
        year=year,
        term=term,
        program_code=program_code,
        branch_code=branch_code,
        division_code=division_code,
    )

    return n_slots, n_conflicts
