# screens/students/page.py
# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE STUDENT MANAGEMENT MODULE
# Features:
# - Students Preview with cohort filtering
# - Single Student Create/Edit
# - Division Editor with delete, audit, copy from previous
# - Division Assignment
# - Bulk Operations
# - Comprehensive Settings
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import traceback
from typing import Optional, Any, List, Dict, Tuple
from datetime import datetime
import pandas as pd

import streamlit as st
import sqlalchemy
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine, Connection


# ════════════════════════════════════════════════════════════════════════════════
# SETTINGS HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _get_setting(conn: Connection, key: str, default: Any = None) -> Any:
    """Gets a setting value from the database."""
    try:
        row = conn.execute(
            sa_text("SELECT value FROM app_settings WHERE key = :key"),
            {"key": key}
        ).fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return default


def _set_setting(conn: Connection, key: str, value: Any):
    """Saves a setting value to the database."""
    conn.execute(sa_text("""
        INSERT INTO app_settings (key, value)
        VALUES (:key, :value)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """), {"key": key, "value": str(value)})


def _init_settings_table(conn: Connection) -> None:
    try:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """))
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════════
# SMALL HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _k(s: str) -> str:
    """Per-page key namespace to avoid collisions."""
    return f"students__{s}"


def _ensure_engine(engine: Optional[Engine]) -> Engine:
    if engine is not None:
        return engine
    from core.settings import load_settings
    from core.db import get_engine
    settings = load_settings()
    return get_engine(settings.db.url)


def _table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            sa_text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": name},
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _students_tables_exist(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            return _table_exists(conn, "student_profiles")
    except Exception:
        return False


def _students_tables_snapshot(engine: Engine) -> None:
    with st.expander("Database snapshot (students tables)", expanded=False):
        try:
            with engine.connect() as conn:
                names = (
                    "student_profiles", "student_enrollments", "student_initial_credentials",
                    "student_custom_profile_fields", "student_custom_profile_data",
                    "degrees", "programs", "branches", "degree_batches", "app_settings",
                    "division_master", "division_assignment_audit", "division_audit_log"
                )
                info = {n: _table_exists(conn, n) for n in names}
                st.write(info)
                if info.get("student_profiles"):
                    total = conn.execute(sa_text("SELECT COUNT(*) FROM student_profiles")).scalar() or 0
                    st.caption(f"student_profiles count: {total}")
        except Exception:
            st.warning("Could not probe students tables.")
            st.code(traceback.format_exc())


# ════════════════════════════════════════════════════════════════════════════════
# BULK OPERATIONS IMPORT
# ════════════════════════════════════════════════════════════════════════════════

_bulk_err = None
_render_bulk_ops = None
try:
    from screens.students.bulk_ops import render as _render_bulk_ops
except Exception as _e:
    _bulk_err = _e


# ════════════════════════════════════════════════════════════════════════════════
# DIVISION MANAGEMENT HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _ensure_division_tables(engine: Engine):
    """Ensure all division-related tables exist."""
    with engine.begin() as conn:
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                degree_code TEXT NOT NULL,
                batch TEXT,
                current_year INTEGER,
                division_code TEXT NOT NULL,
                division_name TEXT NOT NULL,
                capacity INTEGER,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(degree_code, batch, current_year, division_code)
            )
        """))
        
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                degree_code TEXT,
                batch TEXT,
                current_year INTEGER,
                division_code TEXT,
                note TEXT,
                actor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_assignment_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                from_division_code TEXT,
                to_division_code TEXT,
                reason TEXT,
                assigned_by TEXT,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _get_divisions_for_scope(conn: Connection, degree_code: str, batch: str = None, year: int = None) -> List[Dict[str, Any]]:
    """Get divisions for a given scope."""
    query = "SELECT id, division_code, division_name, capacity, active FROM division_master WHERE degree_code = :degree"
    params = {"degree": degree_code}
    
    if batch:
        query += " AND batch = :batch"
        params["batch"] = batch
    if year:
        query += " AND current_year = :year"
        params["year"] = year
    
    query += " ORDER BY division_code"
    rows = conn.execute(sa_text(query), params).fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2], "capacity": r[3], "active": r[4]} for r in rows]


def _get_division_student_count(conn: Connection, degree_code: str, batch: str, year: int, division_code: str) -> int:
    """Get count of students in a division."""
    count = conn.execute(sa_text("""
        SELECT COUNT(*) FROM student_enrollments
        WHERE degree_code = :degree AND batch = :batch AND current_year = :year 
          AND division_code = :div AND is_primary = 1
    """), {"degree": degree_code, "batch": batch, "year": year, "div": division_code}).scalar()
    return count or 0


def _log_division_audit(conn: Connection, action: str, degree: str, batch: str, year: int, div_code: str, note: str):
    """Log division changes to audit table."""
    try:
        conn.execute(sa_text("""
            INSERT INTO division_audit_log (action, degree_code, batch, current_year, division_code, note, actor, created_at)
            VALUES (:action, :degree, :batch, :year, :code, :note, :actor, CURRENT_TIMESTAMP)
        """), {"action": action, "degree": degree, "batch": batch, "year": year, "code": div_code, "note": note, "actor": None})
    except:
        pass


def _create_division(conn: Connection, degree_code: str, batch: str, year: int,
                     division_code: str, division_name: str, capacity: int = None) -> Tuple[bool, str]:
    """Create a new division with audit logging."""
    try:
        existing = conn.execute(sa_text("""
            SELECT 1 FROM division_master
            WHERE degree_code = :degree AND batch = :batch AND current_year = :year AND division_code = :code
        """), {"degree": degree_code, "batch": batch, "year": year, "code": division_code}).fetchone()
        
        if existing:
            return False, f"Division '{division_code}' already exists"
        
        conn.execute(sa_text("""
            INSERT INTO division_master (degree_code, batch, current_year, division_code, division_name, capacity, active)
            VALUES (:degree, :batch, :year, :code, :name, :capacity, 1)
        """), {"degree": degree_code, "batch": batch, "year": year, "code": division_code, "name": division_name, "capacity": capacity})
        
        _log_division_audit(conn, "CREATE", degree_code, batch, year, division_code, f"Created: {division_name}, capacity: {capacity}")
        return True, f"Created division: {division_code}"
    except Exception as e:
        return False, str(e)


def _update_division(conn: Connection, division_id: int, division_name: str = None,
                     capacity: int = None, active: bool = None) -> Tuple[bool, str]:
    """Update division with audit logging."""
    try:
        old = conn.execute(sa_text(
            "SELECT division_code, division_name, capacity, active, degree_code, batch, current_year FROM division_master WHERE id = :id"
        ), {"id": division_id}).fetchone()
        
        if not old:
            return False, "Division not found"
        
        updates, params = [], {"id": division_id}
        changes = []
        
        if division_name is not None and division_name != old[1]:
            updates.append("division_name = :name")
            params["name"] = division_name
            changes.append(f"name: {old[1]} → {division_name}")
        
        if capacity is not None and capacity != old[2]:
            updates.append("capacity = :capacity")
            params["capacity"] = capacity
            changes.append(f"capacity: {old[2]} → {capacity}")
        
        if active is not None and active != bool(old[3]):
            updates.append("active = :active")
            params["active"] = 1 if active else 0
            changes.append(f"active: {old[3]} → {active}")
        
        if updates:
            conn.execute(sa_text(f"UPDATE division_master SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), params)
            _log_division_audit(conn, "UPDATE", old[4], old[5], old[6], old[0], "; ".join(changes))
        
        return True, "Updated"
    except Exception as e:
        return False, str(e)


def _delete_division(conn: Connection, division_id: int, division_code: str) -> Tuple[bool, str]:
    """Delete division with audit logging."""
    count = conn.execute(sa_text(
        "SELECT COUNT(*) FROM student_enrollments WHERE division_code = :div AND is_primary = 1"
    ), {"div": division_code}).scalar() or 0
    
    if count > 0:
        return False, f"Cannot delete: {count} students assigned"
    
    old = conn.execute(sa_text(
        "SELECT degree_code, batch, current_year FROM division_master WHERE id = :id"
    ), {"id": division_id}).fetchone()
    
    conn.execute(sa_text("DELETE FROM division_master WHERE id = :id"), {"id": division_id})
    
    if old:
        _log_division_audit(conn, "DELETE", old[0], old[1], old[2], division_code, "Division deleted")
    
    return True, "Division deleted"


def _copy_divisions_from_previous(conn: Connection, degree_code: str,
                                   from_batch: str, to_batch: str, to_year: int) -> Tuple[bool, str]:
    """Copy divisions from a previous batch/AY to current."""
    try:
        source_divs = conn.execute(sa_text("""
            SELECT division_code, division_name, capacity FROM division_master
            WHERE degree_code = :degree AND batch = :from_batch AND active = 1
        """), {"degree": degree_code, "from_batch": from_batch}).fetchall()
        
        if not source_divs:
            return False, f"No divisions found in {from_batch}"
        
        copied = 0
        for div in source_divs:
            exists = conn.execute(sa_text("""
                SELECT 1 FROM division_master WHERE degree_code = :d AND batch = :b AND current_year = :y AND division_code = :c
            """), {"d": degree_code, "b": to_batch, "y": to_year, "c": div[0]}).fetchone()
            
            if not exists:
                conn.execute(sa_text("""
                    INSERT INTO division_master (degree_code, batch, current_year, division_code, division_name, capacity, active)
                    VALUES (:d, :b, :y, :code, :name, :cap, 1)
                """), {"d": degree_code, "b": to_batch, "y": to_year, "code": div[0], "name": div[1], "cap": div[2]})
                copied += 1
        
        _log_division_audit(conn, "COPY", degree_code, to_batch, to_year, "*", f"Copied {copied} divisions from {from_batch}")
        return True, f"Copied {copied} divisions from {from_batch}"
    except Exception as e:
        return False, str(e)


def _assign_student_division(conn: Connection, enrollment_id: int, from_div: str, to_div: str, reason: str):
    """Assign student to division with audit."""
    conn.execute(sa_text("""
        UPDATE student_enrollments SET division_code = :div, updated_at = CURRENT_TIMESTAMP WHERE id = :eid
    """), {"div": to_div, "eid": enrollment_id})
    
    row = conn.execute(sa_text("SELECT student_profile_id FROM student_enrollments WHERE id = :id"), {"id": enrollment_id}).fetchone()
    if row:
        conn.execute(sa_text("""
            INSERT INTO division_assignment_audit (student_profile_id, enrollment_id, from_division_code, to_division_code, reason)
            VALUES (:pid, :eid, :from, :to, :reason)
        """), {"pid": row[0], "eid": enrollment_id, "from": from_div, "to": to_div, "reason": reason})


# ════════════════════════════════════════════════════════════════════════════════
# DIVISION EDITOR UI
# ════════════════════════════════════════════════════════════════════════════════

def _render_division_editor(engine: Engine):
    """Complete Division Editor with CRUD, copy, and audit."""
    st.markdown("### 🏫 Division Editor")
    
    _ensure_division_tables(engine)
    
    col1, col2, col3 = st.columns(3)
    
    with engine.connect() as conn:
        degrees = [d[0] for d in conn.execute(sa_text(
            "SELECT code FROM degrees WHERE active = 1 ORDER BY sort_order, code"
        )).fetchall()]
    
    if not degrees:
        st.warning("No active degrees. Create degrees first.")
        return
    
    with col1:
        sel_degree = st.selectbox("Degree", degrees, key=_k("dived_deg"))
    
    with engine.connect() as conn:
        batches = [b[0] for b in conn.execute(sa_text("""
            SELECT DISTINCT batch FROM student_enrollments WHERE degree_code = :d AND batch IS NOT NULL
            UNION SELECT batch_code FROM degree_batches WHERE degree_code = :d AND active = 1
            ORDER BY 1 DESC
        """), {"d": sel_degree}).fetchall()]
    
    with col2:
        if not batches:
            st.warning("No batches found")
            return
        sel_batch = st.selectbox("Batch", batches, key=_k("dived_batch"))
    
    with engine.connect() as conn:
        years = [y[0] for y in conn.execute(sa_text("""
            SELECT DISTINCT current_year FROM student_enrollments 
            WHERE degree_code = :d AND batch = :b AND current_year IS NOT NULL
            UNION SELECT year_number FROM degree_year_scaffold WHERE degree_code = :d
            ORDER BY 1
        """), {"d": sel_degree, "b": sel_batch}).fetchall()]
        if not years:
            dur = conn.execute(sa_text("SELECT years FROM degree_semester_struct WHERE degree_code = :d"), {"d": sel_degree}).fetchone()
            years = list(range(1, (dur[0] if dur else 4) + 1))
    
    with col3:
        sel_year = st.selectbox("Year", years, key=_k("dived_year"))
    
    st.divider()
    
    tab_list, tab_create, tab_copy, tab_audit = st.tabs(["📋 Divisions", "➕ Create", "📑 Copy from Previous", "📜 Audit Log"])
    
    with tab_list:
        with engine.connect() as conn:
            divs = conn.execute(sa_text("""
                SELECT id, division_code, division_name, capacity, active FROM division_master
                WHERE degree_code = :d AND batch = :b AND current_year = :y ORDER BY division_code
            """), {"d": sel_degree, "b": sel_batch, "y": sel_year}).fetchall()
        
        if not divs:
            st.info("No divisions defined. Use 'Create' tab to add.")
        else:
            for div in divs:
                div_id, div_code, div_name, div_cap, div_active = div
                with engine.connect() as conn:
                    student_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div_code)
                
                with st.expander(f"**{div_code}** - {div_name} | Students: {student_count} | {'✅ Active' if div_active else '❌ Inactive'}"):
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    
                    with c1:
                        new_name = st.text_input("Name", div_name, key=f"dn_{div_id}")
                    with c2:
                        new_cap = st.number_input("Capacity", value=div_cap or 0, min_value=0, key=f"dc_{div_id}")
                    with c3:
                        new_active = st.checkbox("Active", value=bool(div_active), key=f"da_{div_id}")
                    with c4:
                        if st.button("💾 Save", key=f"ds_{div_id}"):
                            with engine.begin() as conn:
                                _update_division(conn, div_id, new_name, new_cap or None, new_active)
                            st.success("Updated")
                            st.cache_data.clear()
                            st.rerun()
                    
                    st.divider()
                    if student_count == 0:
                        if st.button(f"🗑️ Delete {div_code}", key=f"dd_{div_id}", type="secondary"):
                            with engine.begin() as conn:
                                ok, msg = _delete_division(conn, div_id, div_code)
                            if ok:
                                st.success(msg)
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(msg)
                    else:
                        st.caption(f"⚠️ Cannot delete: {student_count} students assigned. Reassign them first.")
    
    with tab_create:
        st.markdown(f"**Creating for:** {sel_degree} / {sel_batch} / Year {sel_year}")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            new_code = st.text_input("Division Code*", placeholder="A, B, C", key=_k("new_dc"))
        with c2:
            new_name = st.text_input("Division Name*", placeholder="Division A", key=_k("new_dn"))
        with c3:
            new_cap = st.number_input("Capacity", min_value=0, value=60, key=_k("new_dcap"))
        
        if st.button("➕ Create Division", type="primary", key=_k("btn_create_div")):
            if not new_code or not new_name:
                st.error("Code and name required")
            else:
                with engine.begin() as conn:
                    ok, msg = _create_division(conn, sel_degree, sel_batch, sel_year,
                                               new_code.strip().upper(), new_name.strip(), new_cap or None)
                if ok:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(msg)
    
    with tab_copy:
        st.markdown("Copy division structure from a previous batch/AY")
        
        other_batches = [b for b in batches if b != sel_batch]
        if not other_batches:
            st.info("No other batches available to copy from")
        else:
            from_batch = st.selectbox("Copy FROM Batch", other_batches, key=_k("copy_from"))
            
            with engine.connect() as conn:
                preview = conn.execute(sa_text("""
                    SELECT division_code, division_name, capacity FROM division_master
                    WHERE degree_code = :d AND batch = :b AND active = 1 ORDER BY division_code
                """), {"d": sel_degree, "b": from_batch}).fetchall()
            
            if preview:
                st.dataframe([{"Code": p[0], "Name": p[1], "Capacity": p[2]} for p in preview], hide_index=True)
                
                if st.button(f"📑 Copy {len(preview)} divisions to {sel_batch}/Year {sel_year}", type="primary"):
                    with engine.begin() as conn:
                        ok, msg = _copy_divisions_from_previous(conn, sel_degree, from_batch, sel_batch, sel_year)
                    if ok:
                        st.success(msg)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.warning(f"No active divisions in {from_batch}")
    
    with tab_audit:
        with engine.connect() as conn:
            try:
                logs = conn.execute(sa_text("""
                    SELECT action, division_code, batch, current_year, note, actor, created_at 
                    FROM division_audit_log WHERE degree_code = :d ORDER BY created_at DESC LIMIT 50
                """), {"d": sel_degree}).fetchall()
                
                if logs:
                    st.dataframe([{
                        "Action": l[0], "Division": l[1], "Batch": l[2], "Year": l[3],
                        "Note": l[4], "By": l[5], "At": l[6]
                    } for l in logs], hide_index=True, use_container_width=True)
                else:
                    st.info("No audit records yet")
            except Exception as e:
                st.info(f"Audit table not initialized: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# DIVISION ASSIGNMENT UI
# ════════════════════════════════════════════════════════════════════════════════

# Complete _render_division_assignment function
# Replace the existing function in page.py with this complete version

# Complete _render_division_assignment function
# Replace the existing function in page.py with this complete version

def _render_division_assignment(engine: Engine):
    """Assign students to divisions."""
    st.markdown("### 📋 Division Assignment")
    st.caption("Assign or reassign students to divisions")
    
    _ensure_division_tables(engine)
    
    col1, col2, col3 = st.columns(3)
    
    with engine.connect() as conn:
        degrees = [d[0] for d in conn.execute(sa_text(
            "SELECT code FROM degrees WHERE active = 1 ORDER BY code"
        )).fetchall()]
    
    if not degrees:
        st.warning("No active degrees. Create degrees first.")
        return
    
    with col1:
        sel_degree = st.selectbox("Degree", degrees, key=_k("da_deg"))
    
    with engine.connect() as conn:
        batches = [b[0] for b in conn.execute(sa_text("""
            SELECT DISTINCT batch FROM student_enrollments WHERE degree_code = :d AND batch IS NOT NULL ORDER BY batch DESC
        """), {"d": sel_degree}).fetchall()]
    
    with col2:
        if not batches:
            st.warning("No batches with students")
            return
        sel_batch = st.selectbox("Batch", batches, key=_k("da_batch"))
    
    with engine.connect() as conn:
        years = [y[0] for y in conn.execute(sa_text("""
            SELECT DISTINCT current_year FROM student_enrollments 
            WHERE degree_code = :d AND batch = :b AND current_year IS NOT NULL ORDER BY current_year
        """), {"d": sel_degree, "b": sel_batch}).fetchall()]
    
    with col3:
        if not years:
            st.warning("No years found")
            return
        sel_year = st.selectbox("Year", years, key=_k("da_year"))
    
    # Check if this is a divisionless batch
    with engine.connect() as conn:
        divisionless = _get_setting(conn, f"divisionless_{sel_degree}_{sel_batch}_{sel_year}", "False") == "True"
    
    if divisionless:
        st.info("ℹ️ This batch/year is configured as **divisionless** (no division assignments needed).")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Enable Divisions for this Batch/Year", key=_k("enable_divs")):
                with engine.begin() as conn:
                    _set_setting(conn, f"divisionless_{sel_degree}_{sel_batch}_{sel_year}", "False")
                st.success("Divisions enabled")
                st.rerun()
        with col2:
            with engine.connect() as conn:
                student_count = conn.execute(sa_text("""
                    SELECT COUNT(*) FROM student_enrollments
                    WHERE degree_code = :d AND batch = :b AND current_year = :y AND is_primary = 1
                """), {"d": sel_degree, "b": sel_batch, "y": sel_year}).scalar() or 0
            st.metric("Students in this batch", student_count)
        return
    
    with engine.connect() as conn:
        divisions = conn.execute(sa_text("""
            SELECT division_code, division_name, capacity FROM division_master
            WHERE degree_code = :d AND batch = :b AND current_year = :y AND active = 1 ORDER BY division_code
        """), {"d": sel_degree, "b": sel_batch, "y": sel_year}).fetchall()
    
    if not divisions:
        st.warning("⚠️ No divisions defined for this degree/batch/year.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏫 Go to Division Editor", key=_k("goto_editor"), type="primary"):
                st.info("👉 Navigate to: **Settings tab → Division Editor**")
        with col2:
            if st.button("🚫 Mark as Divisionless Batch", key=_k("mark_divisionless")):
                with engine.begin() as conn:
                    _set_setting(conn, f"divisionless_{sel_degree}_{sel_batch}_{sel_year}", "True")
                st.success("✅ Marked as divisionless batch - no division assignments required")
                st.rerun()
        
        st.divider()
        st.info("""
### Options:
1. **Create Divisions** - Use Division Editor to define divisions (A, B, C, etc.)
2. **Mark as Divisionless** - If this batch doesn't need divisions
        """)
        return
    
    div_options = ["-- Unassigned --"] + [f"{d[0]} - {d[1]}" for d in divisions]
    div_codes = [None] + [d[0] for d in divisions]
    
    st.divider()
    
    # ============================================================================
    # AUTO-ASSIGNMENT SECTION
    # ============================================================================
    with st.expander("🎯 Auto-Assign Students to Divisions", expanded=False):
        st.markdown("#### Automatic Division Assignment")
        st.caption("Automatically distribute unassigned students across divisions based on capacity settings")
        
        with engine.connect() as conn:
            unassigned_count = conn.execute(sa_text("""
                SELECT COUNT(*) FROM student_enrollments
                WHERE degree_code = :d AND batch = :b AND current_year = :y 
                  AND (division_code IS NULL OR division_code = '') AND is_primary = 1
            """), {"d": sel_degree, "b": sel_batch, "y": sel_year}).scalar() or 0
        
        if unassigned_count == 0:
            st.success("✅ All students are already assigned to divisions!")
        else:
            st.info(f"📊 **{unassigned_count}** unassigned students found")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                sort_by = st.selectbox(
                    "Sort students by",
                    ["student_id", "name", "roll_number", "random"],
                    help="Order in which students will be assigned to divisions",
                    key=_k("auto_sort")
                )
            
            with col2:
                strategy = st.selectbox(
                    "Assignment strategy",
                    ["fill_sequential", "distribute_evenly"],
                    format_func=lambda x: "📋 Fill divisions sequentially (A, then B, then C...)" if x == "fill_sequential" 
                                         else "⚖️ Distribute evenly across all divisions",
                    key=_k("auto_strategy")
                )
            
            with col3:
                max_per_division = st.number_input(
                    "Max students per division",
                    min_value=1,
                    max_value=500,
                    value=30,
                    step=5,
                    help="Override division capacity temporarily for this assignment (does not change master capacity)",
                    key=_k("auto_max_per_div")
                )
            
            st.divider()
            
            # Show division capacities with override info
            st.markdown("**📊 Current Division Status:**")
            
            # Show override info if different from stored capacity
            use_override = st.checkbox(
                "Override division capacities with custom limit",
                value=False,
                help="Temporarily use the max students per division setting above instead of stored capacities",
                key=_k("use_override")
            )
            
            if use_override:
                st.info(f"ℹ️ Using **{max_per_division}** as capacity limit for all divisions (overriding stored capacities)")
            else:
                st.caption("Using stored division capacities (or no limit if not set)")
            
            if len(divisions) <= 6:
                cap_cols = st.columns(len(divisions))
                for idx, div in enumerate(divisions):
                    with cap_cols[idx]:
                        with engine.connect() as conn:
                            current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div[0])
                        
                        # Determine effective capacity
                        if use_override:
                            effective_capacity = max_per_division
                        else:
                            effective_capacity = div[2] if div[2] else None
                        
                        capacity_display = effective_capacity if effective_capacity else "∞"
                        
                        if effective_capacity:
                            percentage = (current_count / effective_capacity) * 100 if effective_capacity > 0 else 0
                            available = max(0, effective_capacity - current_count)
                        else:
                            available = "Unlimited"
                        
                        st.metric(
                            label=f"**{div[0]}** - {div[1]}",
                            value=f"{current_count}",
                            delta=f"/ {capacity_display} ({available} slots)" if effective_capacity else "No limit",
                        )
            else:
                # Table view for many divisions
                div_data = []
                for div in divisions:
                    with engine.connect() as conn:
                        current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div[0])
                    
                    # Determine effective capacity
                    if use_override:
                        effective_capacity = max_per_division
                    else:
                        effective_capacity = div[2] if div[2] else None
                    
                    capacity_display = effective_capacity if effective_capacity else "No limit"
                    available = (effective_capacity - current_count) if effective_capacity else "Unlimited"
                    
                    div_data.append({
                        "Division": div[0],
                        "Name": div[1],
                        "Current": current_count,
                        "Capacity": capacity_display,
                        "Available": available
                    })
                st.dataframe(div_data, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # Strategy explanation
            if strategy == "fill_sequential":
                st.info(f"""
**📋 Fill Sequential Strategy:**
- Fills Division A to {max_per_division if use_override else 'capacity'} (e.g., {max_per_division} students)
- Then moves to Division B and fills it
- Then Division C, and so on
- Best for: Maintaining full divisions, easier classroom management
                """)
            else:
                st.info(f"""
**⚖️ Distribute Evenly Strategy:**
- Round-robin distribution across all divisions
- Tries to balance student count across divisions
- Respects {max_per_division if use_override else 'division'} capacity limits
- Best for: Equal class sizes, balanced workload
                """)
            
            auto_reason = st.text_input(
                "Assignment reason* (for audit trail)",
                value="Automatic distribution by capacity",
                placeholder="e.g., Initial assignment for new batch, Rebalancing after transfers",
                key=_k("auto_reason")
            )
            
            col1, col2 = st.columns([2, 1])
            with col1:
                if st.button("🎯 Auto-Assign Students", type="primary", key=_k("auto_assign_btn"), use_container_width=True):
                    if not auto_reason:
                        st.error("⚠️ Please provide a reason for audit trail")
                    else:
                        try:
                            with engine.begin() as conn:
                                # Get unassigned students
                                if sort_by == "random":
                                    order_clause = "RANDOM()"
                                else:
                                    order_clause = f"p.{sort_by}"
                                
                                students = conn.execute(sa_text(f"""
                                    SELECT e.id, e.student_profile_id, p.student_id, p.name
                                    FROM student_enrollments e
                                    JOIN student_profiles p ON p.id = e.student_profile_id
                                    WHERE e.degree_code = :d AND e.batch = :b AND e.current_year = :y 
                                      AND (e.division_code IS NULL OR e.division_code = '')
                                      AND e.is_primary = 1
                                    ORDER BY {order_clause}
                                """), {"d": sel_degree, "b": sel_batch, "y": sel_year}).fetchall()
                                
                                if not students:
                                    st.warning("No unassigned students found")
                                else:
                                    assigned_count = 0
                                    skipped_count = 0
                                    assignment_details = []
                                    
                                    if strategy == "fill_sequential":
                                        # Fill each division to capacity before moving to next
                                        student_idx = 0
                                        
                                        for div in divisions:
                                            div_code = div[0]
                                            div_name = div[1]
                                            div_capacity = div[2]
                                            
                                            # Determine effective capacity
                                            if use_override:
                                                effective_capacity = max_per_division
                                            else:
                                                effective_capacity = div_capacity
                                            
                                            current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div_code)
                                            
                                            # Calculate how many more students this division can take
                                            if effective_capacity:
                                                available_slots = effective_capacity - current_count
                                                if available_slots <= 0:
                                                    assignment_details.append(f"⏭️ {div_code} - Already at capacity ({current_count}/{effective_capacity})")
                                                    continue
                                            else:
                                                available_slots = len(students) - student_idx  # No limit, take all remaining
                                            
                                            # Assign students to this division
                                            div_assigned = 0
                                            while student_idx < len(students) and available_slots > 0:
                                                student = students[student_idx]
                                                _assign_student_division(
                                                    conn, 
                                                    student[0],  # enrollment_id
                                                    None,  # from_division
                                                    div_code,  # to_division
                                                    auto_reason
                                                )
                                                assigned_count += 1
                                                div_assigned += 1
                                                student_idx += 1
                                                available_slots -= 1
                                            
                                            if div_assigned > 0:
                                                new_total = current_count + div_assigned
                                                assignment_details.append(
                                                    f"✅ {div_code} - {div_name}: Assigned {div_assigned} students ({current_count} → {new_total}" + 
                                                    (f"/{effective_capacity})" if effective_capacity else ")")
                                                )
                                            
                                            if student_idx >= len(students):
                                                break
                                        
                                        skipped_count = len(students) - assigned_count
                                    
                                    else:  # distribute_evenly
                                        # Round-robin distribution
                                        div_idx = 0
                                        div_assignment_counts = {d[0]: 0 for d in divisions}
                                        
                                        for student in students:
                                            # Find next division with capacity
                                            attempts = 0
                                            assigned_this_student = False
                                            
                                            while attempts < len(divisions):
                                                div = divisions[div_idx % len(divisions)]
                                                div_code = div[0]
                                                div_capacity = div[2]
                                                
                                                # Determine effective capacity
                                                if use_override:
                                                    effective_capacity = max_per_division
                                                else:
                                                    effective_capacity = div_capacity
                                                
                                                current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div_code)
                                                
                                                # Check if division has capacity
                                                if not effective_capacity or current_count < effective_capacity:
                                                    _assign_student_division(
                                                        conn,
                                                        student[0],  # enrollment_id
                                                        None,  # from_division
                                                        div_code,  # to_division
                                                        auto_reason
                                                    )
                                                    assigned_count += 1
                                                    div_assignment_counts[div_code] += 1
                                                    div_idx += 1
                                                    assigned_this_student = True
                                                    break
                                                else:
                                                    # This division is full, try next
                                                    div_idx += 1
                                                    attempts += 1
                                            
                                            if not assigned_this_student:
                                                # All divisions are full
                                                skipped_count += 1
                                        
                                        # Build assignment details
                                        for div in divisions:
                                            div_code = div[0]
                                            div_name = div[1]
                                            count = div_assignment_counts.get(div_code, 0)
                                            if count > 0:
                                                current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, div_code)
                                                
                                                # Determine effective capacity for display
                                                if use_override:
                                                    effective_capacity = max_per_division
                                                else:
                                                    effective_capacity = div[2]
                                                
                                                assignment_details.append(
                                                    f"✅ {div_code} - {div_name}: Assigned {count} students (now {current_count}" +
                                                    (f"/{effective_capacity})" if effective_capacity else ")")
                                                )
                                    
                                    # Show results
                                    if assigned_count > 0:
                                        st.success(f"✅ **Successfully assigned {assigned_count} students to divisions!**")
                                        
                                        with st.expander("📋 Assignment Details", expanded=True):
                                            for detail in assignment_details:
                                                st.markdown(detail)
                                    
                                    if skipped_count > 0:
                                        st.warning(f"⚠️ **{skipped_count} students could not be assigned** (all divisions at capacity)")
                                        st.info("💡 Tip: Increase division capacities or create new divisions to accommodate more students")
                                    
                                    st.cache_data.clear()
                                    
                                    # Auto-refresh after 2 seconds
                                    import time
                                    time.sleep(2)
                                    st.rerun()
                        
                        except Exception as e:
                            st.error(f"❌ Auto-assignment failed: {e}")
                            import traceback
                            with st.expander("🐛 Error Details"):
                                st.code(traceback.format_exc())
            
            with col2:
                if st.button("🔄 Refresh Counts", key=_k("refresh_counts")):
                    st.rerun()
    
    st.divider()
    
    # ============================================================================
    # FILTER AND DISPLAY STUDENTS
    # ============================================================================
    
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        filter_div = st.selectbox("Filter by Division", ["All"] + [d[0] for d in divisions] + ["Unassigned"], key=_k("da_filter"))
    
    with filter_col2:
        search_term = st.text_input("Search student", placeholder="ID, Name, or Email", key=_k("da_search"))
    
    with engine.connect() as conn:
        query = """
            SELECT p.id, e.id as eid, p.student_id, p.name, p.email, e.division_code, e.program_code, e.branch_code
            FROM student_enrollments e
            JOIN student_profiles p ON p.id = e.student_profile_id
            WHERE e.degree_code = :d AND e.batch = :b AND e.current_year = :y AND e.is_primary = 1
        """
        params = {"d": sel_degree, "b": sel_batch, "y": sel_year}
        
        if filter_div == "Unassigned":
            query += " AND (e.division_code IS NULL OR e.division_code = '')"
        elif filter_div != "All":
            query += " AND e.division_code = :div"
            params["div"] = filter_div
        
        if search_term:
            query += " AND (p.student_id LIKE :search OR p.name LIKE :search OR p.email LIKE :search)"
            params["search"] = f"%{search_term}%"
        
        query += " ORDER BY p.student_id"
        students = conn.execute(sa_text(query), params).fetchall()
    
    if not students:
        st.info("ℹ️ No students found with selected filters")
        return
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**📊 {len(students)} students found**")
    with col2:
        if filter_div == "Unassigned" and len(students) > 0:
            st.caption(f"💡 Use auto-assign above")
    
    st.divider()
    
    # ============================================================================
    # BULK ASSIGNMENT
    # ============================================================================
    
    with st.expander("📄 Bulk Assignment", expanded=False):
        st.caption("Assign all filtered students to a single division")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            bulk_div = st.selectbox("Assign all filtered students to:", div_options, key=_k("bulk_div"))
        
        with col2:
            bulk_reason = st.text_input("Reason*", placeholder="Bulk reassignment", key=_k("bulk_reason"))
        
        if st.button("✅ Apply to All Filtered Students", type="primary", key=_k("bulk_apply")):
            if not bulk_reason:
                st.error("⚠️ Reason is required for audit trail")
            else:
                target_code = div_codes[div_options.index(bulk_div)]
                
                # Check capacity if target has one
                if target_code:
                    target_div = next((d for d in divisions if d[0] == target_code), None)
                    if target_div and target_div[2]:  # Has capacity limit
                        with engine.connect() as conn:
                            current_count = _get_division_student_count(conn, sel_degree, sel_batch, sel_year, target_code)
                        
                        new_total = current_count + len(students)
                        if new_total > target_div[2]:
                            st.warning(f"⚠️ Warning: This will exceed capacity ({new_total}/{target_div[2]})")
                            if not st.checkbox("Proceed anyway", key=_k("bulk_override")):
                                return
                
                with engine.begin() as conn:
                    for s in students:
                        _assign_student_division(conn, s[1], s[5], target_code, bulk_reason)
                
                st.success(f"✅ Assigned {len(students)} students to {bulk_div}")
                st.cache_data.clear()
                st.rerun()
    
    st.divider()
    
    # ============================================================================
    # INDIVIDUAL ASSIGNMENT
    # ============================================================================
    
    st.markdown("#### 👤 Individual Assignment")
    st.caption("Manually assign or reassign individual students")
    
    # Use enumerate to get an index 'idx' to ensure unique keys
    display_limit = 50
    for idx, s in enumerate(students[:display_limit]):
        pid, eid, sid, name, email, curr_div, prog, branch = s
        col1, col2, col3 = st.columns([3, 2, 1])
        
        with col1:
            st.markdown(f"**{sid}** - {name}")
            prog_display = prog if prog else "-"
            branch_display = branch if branch else "-"
            curr_div_display = curr_div if curr_div else "⚠️ Unassigned"
            st.caption(f"{prog_display}/{branch_display} | Current: {curr_div_display}")
        
        with col2:
            curr_idx = div_codes.index(curr_div) if curr_div in div_codes else 0
            new_div = st.selectbox("Division", div_options, index=curr_idx, key=f"da_{eid}_{idx}", label_visibility="collapsed")
        
        with col3:
            if new_div != div_options[curr_idx]:
                if st.button("💾", key=f"das_{eid}_{idx}", help="Save assignment"):
                    target_code = div_codes[div_options.index(new_div)]
                    with engine.begin() as conn:
                        _assign_student_division(conn, eid, curr_div, target_code, "Manual reassignment via Division Assignment")
                    st.success("✅ Saved")
                    st.cache_data.clear()
                    st.rerun()
    
    if len(students) > display_limit:
        st.caption(f"ℹ️ Showing {display_limit} of {len(students)} students. Use filters to narrow down.")
        st.info("💡 **Tip:** Use the Auto-Assign feature above for bulk assignments, or filter by division to see specific groups.")
        
# ════════════════════════════════════════════════════════════════════════════════
# SINGLE STUDENT CREATE/EDIT
# ════════════════════════════════════════════════════════════════════════════════

def _render_student_editor(engine: Engine):
    """Create or edit a single student."""
    st.markdown("### 👤 Student Editor")
    
    mode = st.radio("Mode", ["Create New", "Edit Existing"], horizontal=True, key=_k("se_mode"))
    
    st.divider()
    
    profile_id, enrollment_id = None, None
    student = None
    
    if mode == "Edit Existing":
        search = st.text_input("Search by Student ID or Email", key=_k("se_search"))
        
        if search:
            with engine.connect() as conn:
                student = conn.execute(sa_text("""
                    SELECT p.id, p.student_id, p.name, p.email, p.phone, p.status, p.dob, p.gender,
                           e.id as eid, e.degree_code, e.batch, e.current_year, e.program_code,
                           e.branch_code, e.division_code, e.roll_number, e.enrollment_status
                    FROM student_profiles p
                    LEFT JOIN student_enrollments e ON p.id = e.student_profile_id AND e.is_primary = 1
                    WHERE p.student_id = :s OR p.email = :s
                """), {"s": search.strip()}).fetchone()
            
            if not student:
                st.warning("Student not found")
                return
            
            st.success(f"Found: {student[2]} ({student[1]})")
            profile_id, enrollment_id = student[0], student[8]
        else:
            st.info("Enter student ID or email to search")
            return
    
    st.markdown("#### Profile Information")
    col1, col2 = st.columns(2)
    
    with col1:
        f_sid = st.text_input("Student ID*", value=student[1] if student else "", key=_k("se_sid"), disabled=(mode == "Edit Existing"))
        f_name = st.text_input("Name*", value=student[2] if student else "", key=_k("se_name"))
        f_email = st.text_input("Email*", value=student[3] if student else "", key=_k("se_email"))
        f_phone = st.text_input("Phone", value=student[4] or "" if student else "", key=_k("se_phone"))
    
    with col2:
        statuses = ["Good", "Hold", "Left", "Transferred", "Graduated", "Deceased", "YearDrop"]
        curr_status_idx = statuses.index(student[5]) if student and student[5] in statuses else 0
        f_status = st.selectbox("Status", statuses, index=curr_status_idx, key=_k("se_status"))
        f_dob = st.text_input("Date of Birth (YYYY-MM-DD)", value=student[6] or "" if student else "", key=_k("se_dob"))
        f_gender = st.selectbox("Gender", ["", "Male", "Female", "Other"], 
                                index=["", "Male", "Female", "Other"].index(student[7]) if student and student[7] in ["", "Male", "Female", "Other"] else 0,
                                key=_k("se_gender"))
    
    st.markdown("#### Enrollment Information")
    col1, col2 = st.columns(2)
    
    with engine.connect() as conn:
        degrees = [d[0] for d in conn.execute(sa_text("SELECT code FROM degrees WHERE active = 1 ORDER BY code")).fetchall()]
    
    if not degrees:
        st.warning("No degrees available")
        return
    
    with col1:
        curr_deg_idx = degrees.index(student[9]) if student and student[9] in degrees else 0
        f_degree = st.selectbox("Degree*", degrees, index=curr_deg_idx, key=_k("se_degree"))
        
        with engine.connect() as conn:
            batches = [b[0] for b in conn.execute(sa_text(
                "SELECT batch_code FROM degree_batches WHERE degree_code = :d AND active = 1 ORDER BY batch_code DESC"
            ), {"d": f_degree}).fetchall()]
            if not batches:
                batches = [b[0] for b in conn.execute(sa_text(
                    "SELECT DISTINCT batch FROM student_enrollments WHERE degree_code = :d AND batch IS NOT NULL ORDER BY batch DESC"
                ), {"d": f_degree}).fetchall()]
        
        if batches:
            curr_batch_idx = batches.index(student[10]) if student and student[10] in batches else 0
            f_batch = st.selectbox("Batch*", batches, index=curr_batch_idx, key=_k("se_batch"))
        else:
            f_batch = st.text_input("Batch*", value=student[10] if student else "", key=_k("se_batch_txt"))
        
        f_year = st.number_input("Year*", min_value=1, max_value=10, value=student[11] if student and student[11] else 1, key=_k("se_year"))
    
    with col2:
        f_roll = st.text_input("Roll Number", value=student[15] or "" if student else "", key=_k("se_roll"))
        
        with engine.connect() as conn:
            divisions = [""] + [d[0] for d in conn.execute(sa_text("""
                SELECT division_code FROM division_master
                WHERE degree_code = :d AND batch = :b AND current_year = :y AND active = 1 ORDER BY division_code
            """), {"d": f_degree, "b": f_batch, "y": f_year}).fetchall()]
        
        curr_div_idx = divisions.index(student[14]) if student and student[14] in divisions else 0
        f_div = st.selectbox("Division", divisions, index=curr_div_idx, key=_k("se_div"))
        
        enroll_statuses = ["active", "inactive", "graduated", "withdrawn"]
        curr_es_idx = enroll_statuses.index(student[16]) if student and student[16] in enroll_statuses else 0
        f_enroll_status = st.selectbox("Enrollment Status", enroll_statuses, index=curr_es_idx, key=_k("se_estatus"))
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Save Student", type="primary", key=_k("se_save")):
            if not f_sid or not f_name or not f_email or not f_degree or not f_batch:
                st.error("Required fields: Student ID, Name, Email, Degree, Batch")
                return
            
            try:
                with engine.begin() as conn:
                    if profile_id:
                        # Get old status for audit
                        old_status = conn.execute(sa_text("SELECT status FROM student_profiles WHERE id = :id"), 
                                                 {"id": profile_id}).fetchone()
                        old_status_val = old_status[0] if old_status else None
                        
                        # Update profile
                        conn.execute(sa_text("""
                            UPDATE student_profiles SET name = :n, email = :e, phone = :p, status = :s, 
                                   dob = :dob, gender = :g, updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                        """), {"n": f_name, "e": f_email, "p": f_phone or None, "s": f_status,
                               "dob": f_dob or None, "g": f_gender or None, "id": profile_id})
                        
                        # Log status change if different
                        if old_status_val and old_status_val != f_status:
                            conn.execute(sa_text("""
                                INSERT INTO student_status_audit (student_profile_id, from_status, to_status, reason, changed_by)
                                VALUES (:pid, :from, :to, :reason, :by)
                            """), {"pid": profile_id, "from": old_status_val, "to": f_status, 
                                   "reason": "Edited via Student Editor", "by": None})
                        
                        if enrollment_id:
                            conn.execute(sa_text("""
                                UPDATE student_enrollments SET degree_code = :d, batch = :b, current_year = :y,
                                       division_code = :div, roll_number = :roll, enrollment_status = :es, updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                            """), {"d": f_degree, "b": f_batch, "y": f_year, "div": f_div or None,
                                   "roll": f_roll or None, "es": f_enroll_status, "id": enrollment_id})
                        
                        st.success("✅ Student updated successfully")
                    else:
                        existing = conn.execute(sa_text("SELECT 1 FROM student_profiles WHERE student_id = :s"), {"s": f_sid}).fetchone()
                        if existing:
                            st.error(f"Student ID '{f_sid}' already exists")
                            return
                        
                        res = conn.execute(sa_text("""
                            INSERT INTO student_profiles (student_id, name, email, phone, status, dob, gender)
                            VALUES (:sid, :n, :e, :p, :s, :dob, :g)
                        """), {"sid": f_sid, "n": f_name, "e": f_email, "p": f_phone or None,
                               "s": f_status, "dob": f_dob or None, "g": f_gender or None})
                        new_pid = res.lastrowid
                        
                        conn.execute(sa_text("""
                            INSERT INTO student_enrollments (student_profile_id, degree_code, batch, current_year, division_code, roll_number, enrollment_status, is_primary)
                            VALUES (:pid, :d, :b, :y, :div, :roll, :es, 1)
                        """), {"pid": new_pid, "d": f_degree, "b": f_batch, "y": f_year,
                               "div": f_div or None, "roll": f_roll or None, "es": f_enroll_status})
                        
                        st.success(f"✅ Student created: {f_sid}")
                    
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Error: {e}")
    
    with col2:
        if mode == "Edit Existing" and profile_id:
            if st.button("🔄 Reset Form", key=_k("se_reset")):
                st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
# STUDENTS PREVIEW TAB
# ════════════════════════════════════════════════════════════════════════════════

def _render_students_preview(engine: Engine):
    """Preview students per batch with filtering by degree cohorts."""
    st.markdown("### 👥 Students Preview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with engine.connect() as conn:
        degrees = [d[0] for d in conn.execute(sa_text(
            "SELECT code FROM degrees WHERE active = 1 ORDER BY code"
        )).fetchall()]
    
    with col1:
        sel_degree = st.selectbox("Degree", ["All"] + degrees, key=_k("sp_deg"))
    
    with engine.connect() as conn:
        if sel_degree != "All":
            programs = [p[0] for p in conn.execute(sa_text(
                "SELECT DISTINCT program_code FROM student_enrollments WHERE degree_code = :d AND program_code IS NOT NULL ORDER BY program_code"
            ), {"d": sel_degree}).fetchall()]
        else:
            programs = [p[0] for p in conn.execute(sa_text(
                "SELECT DISTINCT program_code FROM student_enrollments WHERE program_code IS NOT NULL ORDER BY program_code"
            )).fetchall()]
    
    with col2:
        sel_program = st.selectbox("Program", ["All"] + programs, key=_k("sp_prog"))
    
    with engine.connect() as conn:
        branch_q = "SELECT DISTINCT branch_code FROM student_enrollments WHERE branch_code IS NOT NULL"
        params = {}
        if sel_degree != "All":
            branch_q += " AND degree_code = :d"
            params["d"] = sel_degree
        if sel_program != "All":
            branch_q += " AND program_code = :p"
            params["p"] = sel_program
        branch_q += " ORDER BY branch_code"
        branches = [b[0] for b in conn.execute(sa_text(branch_q), params).fetchall()]
    
    with col3:
        sel_branch = st.selectbox("Branch", ["All"] + branches, key=_k("sp_branch"))
    
    with engine.connect() as conn:
        batch_q = "SELECT DISTINCT batch FROM student_enrollments WHERE batch IS NOT NULL"
        params = {}
        if sel_degree != "All":
            batch_q += " AND degree_code = :d"
            params["d"] = sel_degree
        batch_q += " ORDER BY batch DESC"
        batches = [b[0] for b in conn.execute(sa_text(batch_q), params).fetchall()]
    
    with col4:
        sel_batch = st.selectbox("Batch", ["All"] + batches, key=_k("sp_batch"))
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        sel_year = st.selectbox("Year", ["All", 1, 2, 3, 4, 5], key=_k("sp_year"))
    
    with col2:
        with engine.connect() as conn:
            div_q = "SELECT DISTINCT division_code FROM student_enrollments WHERE division_code IS NOT NULL"
            if sel_degree != "All":
                div_q += f" AND degree_code = '{sel_degree}'"
            div_q += " ORDER BY division_code"
            try:
                div_list = [d[0] for d in conn.execute(sa_text(div_q)).fetchall()]
            except:
                div_list = []
        sel_division = st.selectbox("Division", ["All", "Unassigned"] + div_list, key=_k("sp_div"))
    
    with col3:
        sel_status = st.selectbox("Status", ["All", "Good", "Hold", "Left", "Transferred", "Graduated", "YearDrop"], key=_k("sp_status"))
    
    with col4:
        search_text = st.text_input("Search", placeholder="ID, Name, Email", key=_k("sp_search"))
    
    st.divider()
    
    query = """
        SELECT p.student_id, p.name, p.email, p.phone, p.status,
               e.degree_code, e.batch, e.current_year, e.program_code, e.branch_code,
               e.division_code, e.roll_number, e.enrollment_status, p.id as pid, e.id as eid
        FROM student_profiles p
        JOIN student_enrollments e ON p.id = e.student_profile_id AND e.is_primary = 1
        WHERE 1=1
    """
    params = {}
    
    if sel_degree != "All":
        query += " AND e.degree_code = :degree"
        params["degree"] = sel_degree
    if sel_program != "All":
        query += " AND e.program_code = :program"
        params["program"] = sel_program
    if sel_branch != "All":
        query += " AND e.branch_code = :branch"
        params["branch"] = sel_branch
    if sel_batch != "All":
        query += " AND e.batch = :batch"
        params["batch"] = sel_batch
    if sel_year != "All":
        query += " AND e.current_year = :year"
        params["year"] = sel_year
    if sel_division == "Unassigned":
        query += " AND (e.division_code IS NULL OR e.division_code = '')"
    elif sel_division != "All":
        query += " AND e.division_code = :division"
        params["division"] = sel_division
    if sel_status != "All":
        query += " AND p.status = :status"
        params["status"] = sel_status
    if search_text:
        query += " AND (p.student_id LIKE :search OR p.name LIKE :search OR p.email LIKE :search)"
        params["search"] = f"%{search_text}%"
    
    query += " ORDER BY e.degree_code, e.batch, e.current_year, p.student_id LIMIT 500"
    
    with engine.connect() as conn:
        rows = conn.execute(sa_text(query), params).fetchall()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Students", len(rows))
    unassigned = sum(1 for r in rows if not r[10])
    col2.metric("Unassigned Division", unassigned)
    status_counts = {}
    for r in rows:
        status_counts[r[4]] = status_counts.get(r[4], 0) + 1
    col3.metric("Good Standing", status_counts.get("Good", 0))
    col4.metric("On Hold", status_counts.get("Hold", 0))
    
    st.divider()
    
    if not rows:
        st.info("No students found with selected filters")
        return
    
    df = pd.DataFrame(rows, columns=[
        "Student ID", "Name", "Email", "Phone", "Status", "Degree", "Batch", "Year",
        "Program", "Branch", "Division", "Roll No", "Enroll Status", "PID", "EID"
    ])
    
    # Replace None/NaN with readable placeholders
    display_df = df.drop(columns=["PID", "EID"])
    display_df = display_df.fillna({
        "Program": "-",
        "Branch": "-",
        "Division": "-",
        "Roll No": "-",
        "Phone": "-"
    })
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    csv = display_df.to_csv(index=False)
    st.download_button("📥 Export to CSV", csv, "students_export.csv", "text/csv", key=_k("sp_dl"))
    
    st.divider()
    st.markdown("#### Quick Edit")
    
    student_options = [f"{r[0]} - {r[1]}" for r in rows[:100]]
    if student_options:
        selected = st.selectbox("Select student to edit", [""] + student_options, key=_k("sp_qe_sel"))
        
        if selected:
            idx = student_options.index(selected)
            row = rows[idx]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                qe_statuses = ["Good", "Hold", "Left", "Transferred", "Graduated", "YearDrop"]
                qe_curr_idx = qe_statuses.index(row[4]) if row[4] in qe_statuses else 0
                new_status = st.selectbox("Status", qe_statuses, index=qe_curr_idx, key=_k("sp_qe_status"))
            
            with col2:
                with engine.connect() as conn:
                    divs = [""] + [d[0] for d in conn.execute(sa_text("""
                        SELECT division_code FROM division_master
                        WHERE degree_code = :d AND batch = :b AND current_year = :y AND active = 1 ORDER BY division_code
                    """), {"d": row[5], "b": row[6], "y": row[7]}).fetchall()]
                
                curr_div_idx = divs.index(row[10]) if row[10] in divs else 0
                new_div = st.selectbox("Division", divs, index=curr_div_idx, key=_k("sp_qe_div"))
            
            with col3:
                if st.button("💾 Update", key=_k("sp_qe_save")):
                    with engine.begin() as conn:
                        # Get old status for audit
                        old_status = conn.execute(sa_text("SELECT status FROM student_profiles WHERE id = :id"), 
                                                 {"id": row[13]}).fetchone()
                        old_status_val = old_status[0] if old_status else None
                        
                        # Update status
                        conn.execute(sa_text("UPDATE student_profiles SET status = :s, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                                     {"s": new_status, "id": row[13]})
                        
                        # Log status change if different
                        if old_status_val and old_status_val != new_status:
                            conn.execute(sa_text("""
                                INSERT INTO student_status_audit (student_profile_id, from_status, to_status, reason, changed_by)
                                VALUES (:pid, :from, :to, :reason, :by)
                            """), {"pid": row[13], "from": old_status_val, "to": new_status, 
                                   "reason": "Quick edit from Students Preview", "by": None})
                        
                        # Update division
                        conn.execute(sa_text("UPDATE student_enrollments SET division_code = :d, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                                     {"d": new_div or None, "id": row[14]})
                    st.success("Updated")
                    st.cache_data.clear()
                    st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
# SETTINGS TAB HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _render_custom_fields_settings(engine: Engine):
    """Manage custom profile fields for students."""
    st.markdown("### 📝 Custom Profile Fields")
    st.caption("Define additional fields to capture student information.")
    
    try:
        with engine.connect() as conn:
            fields = conn.execute(sa_text("""
                SELECT id, code, label, dtype, required, active, sort_order
                FROM student_custom_profile_fields ORDER BY sort_order, code
            """)).fetchall()
            
            if fields:
                st.markdown("#### Existing Custom Fields")
                for field in fields:
                    with st.expander(f"**{field[2]}** (`{field[1]}`) - {'Active' if field[5] else 'Inactive'}"):
                        col1, col2, col3 = st.columns([2, 1, 1])
                        col1.text_input("Label", value=field[2], key=f"field_label_{field[0]}", disabled=True)
                        col2.text_input("Type", value=field[3], key=f"field_type_{field[0]}", disabled=True)
                        col3.checkbox("Required", value=bool(field[4]), key=f"field_req_{field[0]}", disabled=True)
                        
                        if st.button("🗑️ Delete Field", key=f"del_field_{field[0]}"):
                            with engine.begin() as conn_b:
                                conn_b.execute(sa_text("DELETE FROM student_custom_profile_data WHERE field_code = :code"), {"code": field[1]})
                                conn_b.execute(sa_text("DELETE FROM student_custom_profile_fields WHERE code = :code"), {"code": field[1]})
                            st.success(f"Deleted field: {field[2]}")
                            st.rerun()
            else:
                st.info("No custom fields defined yet.")
        
        with st.expander("➕ Add New Custom Field", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                new_code = st.text_input("Field Code*", placeholder="e.g., blood_group", key=_k("new_field_code"))
                new_label = st.text_input("Field Label*", placeholder="e.g., Blood Group", key=_k("new_field_label"))
            with col2:
                new_dtype = st.selectbox("Data Type*", ["text", "number", "date", "choice", "boolean"], key=_k("new_field_dtype"))
                new_required = st.checkbox("Required Field", key=_k("new_field_required"))
                new_active = st.checkbox("Active", value=True, key=_k("new_field_active"))

            if st.button("Add Custom Field", type="primary", key=_k("add_field_btn")):
                if not new_code or not new_label:
                    st.error("Field code and label are required")
                else:
                    try:
                        with engine.begin() as conn_b:
                            conn_b.execute(sa_text("""
                                INSERT INTO student_custom_profile_fields (code, label, dtype, required, active, sort_order)
                                VALUES (:code, :label, :dtype, :req, :active, 100)
                            """), {"code": new_code.strip().lower().replace(" ", "_"), "label": new_label.strip(),
                                   "dtype": new_dtype, "req": 1 if new_required else 0, "active": 1 if new_active else 0})
                        st.success(f"✅ Added custom field: {new_label}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add field: {e}")
    except Exception as e:
        st.error(f"Failed to load custom fields: {e}")


def _render_roll_number_policy(engine: Engine):
    """Configure roll number policies."""
    st.markdown("### 🔢 Roll Number Policy")
    
    with engine.connect() as conn:
        derivation_mode = st.radio(
            "Roll Number Generation",
            ["hybrid", "manual", "auto"],
            index=["hybrid", "manual", "auto"].index(_get_setting(conn, "roll_derivation_mode", "hybrid")),
            help="Hybrid: Auto with override. Manual: Always enter. Auto: Fully automated.",
            key=_k("roll_derivation_mode")
        )
        
        year_from_first4 = st.checkbox(
            "Extract year from first 4 digits",
            value=_get_setting(conn, "roll_year_from_first4", "True") == "True",
            key=_k("year_from_first4")
        )
        
        per_degree_regex = st.checkbox(
            "Allow per-degree regex patterns",
            value=_get_setting(conn, "roll_per_degree_regex", "True") == "True",
            key=_k("per_degree_regex")
        )
    
    if st.button("💾 Save Roll Number Policy", type="primary", key=_k("save_roll_policy")):
        with engine.begin() as conn_b:
            _set_setting(conn_b, "roll_derivation_mode", derivation_mode)
            _set_setting(conn_b, "roll_year_from_first4", str(year_from_first4))
            _set_setting(conn_b, "roll_per_degree_regex", str(per_degree_regex))
        st.success("✅ Roll number policy saved")
        st.rerun()


def _render_email_lifecycle_policy(engine: Engine):
    """Configure email lifecycle requirements."""
    st.markdown("### 📧 Email Lifecycle Policy")
    
    with engine.connect() as conn:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### .edu Email Requirement")
            edu_email_enabled = st.checkbox(
                "Require .edu email",
                value=_get_setting(conn, "email_edu_enabled", "True") == "True",
                key=_k("edu_email_enabled")
            )
            edu_enforcement_months = st.number_input(
                "Enforcement period (months)", min_value=1, max_value=24,
                value=int(_get_setting(conn, "email_edu_months", "6")),
                key=_k("edu_enforcement_months")
            )
            edu_domain = st.text_input(
                "Allowed domain(s)", value=_get_setting(conn, "email_edu_domain", "college.edu"),
                key=_k("edu_domain")
            )
        
        with col2:
            st.markdown("#### Post-Graduation Email")
            personal_email_enabled = st.checkbox(
                "Require personal email after graduation",
                value=_get_setting(conn, "email_personal_enabled", "True") == "True",
                key=_k("personal_email_enabled")
            )
            personal_enforcement_months = st.number_input(
                "Enforcement period (months)", min_value=1, max_value=24,
                value=int(_get_setting(conn, "email_personal_months", "6")),
                key=_k("personal_enforcement_months")
            )
    
    if st.button("💾 Save Email Policy", type="primary", key=_k("save_email_policy")):
        with engine.begin() as conn:
            _set_setting(conn, "email_edu_enabled", str(edu_email_enabled))
            _set_setting(conn, "email_edu_months", str(edu_enforcement_months))
            _set_setting(conn, "email_edu_domain", edu_domain)
            _set_setting(conn, "email_personal_enabled", str(personal_email_enabled))
            _set_setting(conn, "email_personal_months", str(personal_enforcement_months))
        st.success("✅ Email lifecycle policy saved")
        st.rerun()


def _render_student_status_settings(engine: Engine):
    """Configure student statuses and manage advanced status rules."""
    st.markdown("### 🎓 Student Status Configuration")
    
    tabs = st.tabs(["📋 Status Definitions", "📜 Status History", "⚙️ Advanced Rules Engine"])
    
    # TAB 1: Status Definitions
    with tabs[0]:
        default_statuses = {
            "Good": {"effects": {"include_in_current_ay": True}, "note": "Active student in good standing"},
            "Hold": {"effects": {"include_in_current_ay": False}, "note": "Hidden from current AY calculations"},
            "Left": {"effects": {"include_in_current_ay": False, "future_allocations": False}, "note": "Student has left"},
            "Transferred": {"effects": {"include_in_current_ay": False, "future_allocations": False}, "note": "Transferred out"},
            "Graduated": {"effects": {"include_in_current_ay": False, "eligible_for_transcript": True}, "note": "Completed program"},
            "Deceased": {"effects": {"include_in_current_ay": False, "record_frozen": True}, "note": "Record frozen"},
            "YearDrop": {"effects": {"include_in_current_ay": True}, "note": "Dropped a year but enrolled"}
        }
        
        for status_name, config in default_statuses.items():
            with st.expander(f"**{status_name}**"):
                st.caption(config['note'])
                for effect, value in config['effects'].items():
                    st.markdown(f"{'✅' if value else '❌'} `{effect}`")
        
        st.info("💡 Status definitions shown above. Use Advanced Rules Engine tab for automatic status computation.")
    
    # TAB 2: Status History
    with tabs[1]:
        st.markdown("#### 📜 Recent Status Changes")
        
        with engine.connect() as conn:
            try:
                logs = conn.execute(sa_text("""
                    SELECT 
                        p.student_id,
                        p.name,
                        a.from_status,
                        a.to_status,
                        a.reason,
                        a.changed_by,
                        a.changed_at
                    FROM student_status_audit a
                    JOIN student_profiles p ON p.id = a.student_profile_id
                    ORDER BY a.changed_at DESC
                    LIMIT 100
                """)).fetchall()
                
                if logs:
                    df = pd.DataFrame(logs, columns=[
                        "Student ID", "Name", "From", "To", "Reason", "Changed By", "Changed At"
                    ])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("No status change history yet")
            except Exception as e:
                st.warning(f"Status audit table not available: {e}")
    
    # TAB 3: Advanced Rules Engine
    with tabs[2]:
        st.markdown("#### 🎯 Rule-Based Status Management")
        st.info("""
**Advanced Status System** automatically computes student status based on:
- 📊 Fee payment status (Active/Inactive)
- 📈 Academic performance (Good/Hold/Detained)
- 📚 Attendance percentage
- 🎓 Internal/External marks
- 🔄 Previous semester performance
- 📝 Backlog count

This requires additional schema tables. Check if installed below.
        """)
        
        # Check if advanced tables exist
        with engine.connect() as conn:
            try:
                tables_exist = all([
                    _table_exists(conn, "student_fee_payments"),
                    _table_exists(conn, "student_semester_performance"),
                    _table_exists(conn, "student_status_rules"),
                    _table_exists(conn, "student_exam_eligibility")
                ])
            except:
                tables_exist = False
        
        if not tables_exist:
            st.warning("⚠️ Advanced status tables not installed")
            
            with st.expander("📋 Installation Instructions", expanded=True):
                st.markdown("""
### Installation Steps:

1. **Add schema file**: Create `schemas/student_status_enhanced_schema.py`
2. **Add rules engine**: Create `core/student_status_engine.py`
3. **Add UI module**: Create `screens/students/status_management.py`
4. **Run schema installer** to create new tables
5. **Refresh this page**

**Tables to be created:**
- `student_fee_payments` - Fee payment tracking
- `student_semester_performance` - Academic performance per semester
- `student_status_rules` - Configurable rules
- `student_status_computation_log` - Audit trail
- `student_exam_eligibility` - Exam eligibility tracking
- `student_status_overrides` - Manual overrides

**Files needed:**
```
schemas/student_status_enhanced_schema.py  ← Schema definitions
core/student_status_engine.py             ← Rules engine
screens/students/status_management.py     ← UI component
```

Contact your system administrator to install these components.
                """)
        else:
            st.success("✅ Advanced status system is installed")
            
            # Try to import and render the advanced UI
            try:
                from screens.students.status_management import render_status_management
                
                st.divider()
                render_status_management(engine)
                
            except ImportError as e:
                st.warning(f"⚠️ Status management UI not available: {e}")
                st.info("The database tables exist, but the UI module is not installed. Create `screens/students/status_management.py`")
            except Exception as e:
                st.error(f"Failed to load status management: {e}")
                import traceback
                with st.expander("Error Details"):
                    st.code(traceback.format_exc())


def _render_division_settings(engine: Engine):
    """Configure division management rules."""
    st.markdown("### 🏫 Division/Section Settings")
    
    with engine.connect() as conn:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Division Configuration")
            divisions_enabled = st.checkbox(
                "Enable divisions per term",
                value=_get_setting(conn, "div_enabled", "True") == "True",
                key=_k("divisions_enabled")
            )
            free_form_names = st.checkbox(
                "Allow free-form division names",
                value=_get_setting(conn, "div_free_form", "True") == "True",
                key=_k("free_form_names")
            )
            
            scope_options = ["degree_cohort_term", "degree_cohort_global", "degree_global_term", "degree_global", "global"]
            scope_labels = {
                "degree_cohort_term": "Per Degree Cohort Per Term",
                "degree_cohort_global": "Per Degree Cohort (Global)",
                "degree_global_term": "Per Degree Per Term",
                "degree_global": "Per Degree (Global)",
                "global": "Globally Unique"
            }
            current_scope = _get_setting(conn, "div_unique_scope", "degree_cohort_term")
            if current_scope not in scope_options:
                current_scope = "degree_cohort_term"
            
            unique_scope = st.selectbox(
                "Uniqueness scope", scope_options, index=scope_options.index(current_scope),
                format_func=lambda x: scope_labels.get(x, x), key=_k("unique_scope")
            )
        
        with col2:
            st.markdown("#### Import & Copy Settings")
            import_optional = st.checkbox(
                "Division column optional in imports",
                value=_get_setting(conn, "div_import_optional", "True") == "True",
                key=_k("import_optional")
            )
            copy_from_previous = st.checkbox(
                "Enable copy from previous term",
                value=_get_setting(conn, "div_copy_prev", "True") == "True",
                key=_k("copy_from_previous")
            )
            block_publish_unassigned = st.checkbox(
                "Block publish when students unassigned",
                value=_get_setting(conn, "div_block_publish", "True") == "True",
                key=_k("block_publish")
            )
        
        with st.expander("🔢 Division Capacity"):
            capacity_mode = st.radio(
                "Capacity tracking", ["off", "soft_limit", "hard_limit"],
                index=["off", "soft_limit", "hard_limit"].index(_get_setting(conn, "div_capacity_mode", "off")),
                key=_k("capacity_mode")
            )
            default_capacity = 60
            if capacity_mode != "off":
                default_capacity = st.number_input("Default capacity", min_value=1,
                    value=int(_get_setting(conn, "div_default_capacity", "60")), key=_k("default_capacity"))
    
    if st.button("💾 Save Division Settings", type="primary", key=_k("save_div_settings")):
        with engine.begin() as conn:
            _set_setting(conn, "div_enabled", str(divisions_enabled))
            _set_setting(conn, "div_free_form", str(free_form_names))
            _set_setting(conn, "div_unique_scope", unique_scope)
            _set_setting(conn, "div_import_optional", str(import_optional))
            _set_setting(conn, "div_copy_prev", str(copy_from_previous))
            _set_setting(conn, "div_block_publish", str(block_publish_unassigned))
            _set_setting(conn, "div_capacity_mode", capacity_mode)
            if capacity_mode != "off":
                _set_setting(conn, "div_default_capacity", str(default_capacity))
        st.success("✅ Division settings saved")
        st.rerun()


def _render_publish_guardrails(engine: Engine):
    """Configure publish guardrails."""
    st.markdown("### 🛡️ Publish Guardrails")
    
    with engine.connect() as conn:
        guard_unassigned = st.checkbox("Block if program/branch/division unassigned",
            value=_get_setting(conn, "guard_unassigned", "True") == "True", key=_k("guard_unassigned"))
        guard_duplicates = st.checkbox("Block if duplicates unresolved",
            value=_get_setting(conn, "guard_duplicates", "True") == "True", key=_k("guard_duplicates"))
        guard_invalid = st.checkbox("Block if invalid roll or email",
            value=_get_setting(conn, "guard_invalid", "True") == "True", key=_k("guard_invalid"))
        guard_batch_mismatch = st.checkbox("Block if batch mismatch",
            value=_get_setting(conn, "guard_batch_mismatch", "True") == "True", key=_k("guard_batch_mismatch"))
        guard_capacity = st.checkbox("Block on hard capacity breach",
            value=_get_setting(conn, "guard_capacity", "False") == "True", key=_k("guard_capacity"))
    
    if st.button("💾 Save Guardrails", type="primary", key=_k("save_guardrails")):
        with engine.begin() as conn:
            _set_setting(conn, "guard_unassigned", str(guard_unassigned))
            _set_setting(conn, "guard_duplicates", str(guard_duplicates))
            _set_setting(conn, "guard_invalid", str(guard_invalid))
            _set_setting(conn, "guard_batch_mismatch", str(guard_batch_mismatch))
            _set_setting(conn, "guard_capacity", str(guard_capacity))
        st.success("✅ Publish guardrails saved")
        st.rerun()


def _render_mover_settings(engine: Engine):
    """Configure student mover policies."""
    st.markdown("### 🚚 Student Mover Settings")
    
    with engine.connect() as conn:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Within-Term Division Moves")
            within_term_enabled = st.checkbox("Enable within-term division moves",
                value=_get_setting(conn, "mover_within_term", "True") == "True", key=_k("mover_within_term"))
            require_reason_within = st.checkbox("Require reason for move",
                value=_get_setting(conn, "mover_within_reason", "True") == "True", key=_k("mover_within_reason"))
        
        with col2:
            st.markdown("#### Cross-Batch Moves")
            cross_batch_enabled = st.checkbox("Enable cross-batch moves",
                value=_get_setting(conn, "mover_cross_batch", "True") == "True", key=_k("mover_cross_batch"))
            next_batch_only = st.checkbox("Restrict to next batch only",
                value=_get_setting(conn, "mover_next_only", "True") == "True", key=_k("mover_next_only"))
            require_reason_cross = st.checkbox("Require reason for cross-batch move",
                value=_get_setting(conn, "mover_cross_reason", "True") == "True", key=_k("mover_cross_reason"))
    
    if st.button("💾 Save Mover Settings", type="primary", key=_k("save_mover_settings")):
        with engine.begin() as conn:
            _set_setting(conn, "mover_within_term", str(within_term_enabled))
            _set_setting(conn, "mover_within_reason", str(require_reason_within))
            _set_setting(conn, "mover_cross_batch", str(cross_batch_enabled))
            _set_setting(conn, "mover_next_only", str(next_batch_only))
            _set_setting(conn, "mover_cross_reason", str(require_reason_cross))
        st.success("✅ Student mover settings saved")
        st.rerun()


def _render_settings_tab(engine: Engine):
    """Main settings tab."""
    st.subheader("⚙️ Student Settings")
    
    settings_sections = st.tabs([
        "📝 Custom Fields", "🔢 Roll Numbers", "📧 Email Policy", "🎓 Student Status",
        "🏫 Division Editor", "📋 Division Assignment", "⚙️ Division Settings",
        "🛡️ Guardrails", "🚚 Movers"
    ])
    
    with settings_sections[0]:
        _render_custom_fields_settings(engine)
    with settings_sections[1]:
        _render_roll_number_policy(engine)
    with settings_sections[2]:
        _render_email_lifecycle_policy(engine)
    with settings_sections[3]:
        _render_student_status_settings(engine)
    with settings_sections[4]:
        _render_division_editor(engine)
    with settings_sections[5]:
        _render_division_assignment(engine)
    with settings_sections[6]:
        _render_division_settings(engine)
    with settings_sections[7]:
        _render_publish_guardrails(engine)
    with settings_sections[8]:
        _render_mover_settings(engine)


# ════════════════════════════════════════════════════════════════════════════════
# MAIN RENDER FUNCTION
# ════════════════════════════════════════════════════════════════════════════════

def render(engine: Optional[Engine] = None, **kwargs) -> None:
    """Main render function for Students page."""
    engine = _ensure_engine(engine)

    st.title("👨‍🎓 Students")
    st.caption(f"Module: `{__file__}`")

    if not _students_tables_exist(engine):
        st.warning("⚠️ Student tables not found. Run schema setup.")
        st.info("""
### 🚀 Getting Started
1. Run database schema initialization
2. Create **Degrees** (in 🎓 Degrees)
3. Create **Academic Years** (in 🗓️ Academic Years)
4. Return here to manage students
        """)
        return

    with engine.connect() as conn:
        try:
            degree_count = conn.execute(sa_text("SELECT COUNT(*) FROM degrees WHERE active = 1")).scalar() or 0
        except:
            degree_count = 0

    if not degree_count:
        st.warning("⚠️ No active degrees found")
        st.info("""
### 🚀 Getting Started
1. **Create Degrees** - Go to 🎓 Degrees page
2. **Set degree duration** (number of years)
3. **Activate the degree**
4. Return here to manage students
        """)
        return

    _ensure_division_tables(engine)
    _students_tables_snapshot(engine)

    tab_preview, tab_editor, tab_list, tab_bulk, tab_settings = st.tabs([
        "👥 Students Preview", "👤 Student Editor", "📋 Student List",
        "📦 Bulk Operations", "⚙️ Settings"
    ])

    with tab_preview:
        try:
            _render_students_preview(engine)
        except Exception as e:
            st.error(f"Preview failed: {e}")
            st.code(traceback.format_exc())

    with tab_editor:
        try:
            _render_student_editor(engine)
        except Exception as e:
            st.error(f"Editor failed: {e}")
            st.code(traceback.format_exc())

    with tab_list:
        try:
            st.subheader("📋 All Students (Recent 50)")
            with engine.connect() as conn:
                rows = conn.execute(sa_text("""
                    SELECT p.id, p.student_id, p.name, p.email, p.status, e.degree_code, e.batch, e.current_year
                    FROM student_profiles p
                    LEFT JOIN student_enrollments e ON p.id = e.student_profile_id AND e.is_primary = 1
                    ORDER BY p.updated_at DESC LIMIT 50
                """)).fetchall()
                
                if rows:
                    st.dataframe([{
                        "ID": r[1], "Name": r[2], "Email": r[3], "Status": r[4],
                        "Degree": r[5], "Batch": r[6], "Year": r[7]
                    } for r in rows], use_container_width=True, hide_index=True)
                else:
                    st.info("No students. Use **Bulk Operations** to import or **Student Editor** to create.")
        except Exception as e:
            st.error(f"List failed: {e}")

    with tab_bulk:
        if _bulk_err:
            st.error(f"Bulk Operations import failed: {_bulk_err}")
        elif _render_bulk_ops:
            try:
                _render_bulk_ops(engine)
            except Exception as e:
                st.error(f"Bulk ops failed: {e}")
                st.code(traceback.format_exc())
        else:
            st.info("Bulk operations not available")

    with tab_settings:
        try:
            _render_settings_tab(engine)
        except Exception as e:
            st.error(f"Settings failed: {e}")
            st.code(traceback.format_exc())


if __name__ == "__main__":
    render()
