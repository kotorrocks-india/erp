# ============================================================================
# TIMETABLE GRID FIX - Interactive Dropdowns
# ============================================================================
# This module provides a fix for the timetable grid to use actual dropdowns
# instead of static HTML + signs
#
# To use: Replace the render_complete_excel_timetable function import in 
# app_weekly_planner.py with this module
# ============================================================================

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.engine import Engine
from sqlalchemy import text
import json
import uuid
from datetime import datetime

# ============================================================================
# COLOR SCHEMES (Matching existing design)
# ============================================================================

YEAR_COLORS = {
    1: '#F4CCCC',  # Light red/pink
    2: '#FCE5CD',  # Light orange/tan
    3: '#FFF2CC',  # Light yellow
    4: '#D9EAD3',  # Light green
    5: '#D0E0E3',  # Light blue
}

HEADER_COLORS = {
    'day': '#93C47D',
    'period': '#B7B7B7',
    'time': '#D9D9D9',
    'year_label': '#E6B8AF',
}

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def ensure_tables(engine: Engine):
    """Ensure required tables exist - handles existing tables gracefully"""
    with engine.begin() as conn:
        # Check if table exists
        table_exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='timetable_slots'"
        )).fetchone()
        
        if not table_exists:
            # Create fresh table with all columns
            conn.execute(text("""
                CREATE TABLE timetable_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ay_label TEXT NOT NULL,
                    degree_code TEXT NOT NULL,
                    program_code TEXT,
                    branch_code TEXT,
                    year INTEGER NOT NULL,
                    term INTEGER NOT NULL,
                    division_code TEXT,
                    offering_id INTEGER,
                    subject_code TEXT,
                    subject_type TEXT,
                    day_of_week INTEGER NOT NULL,
                    period_id INTEGER NOT NULL,
                    bridge_group_id TEXT,
                    bridge_position INTEGER DEFAULT 1,
                    bridge_length INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    faculty_in_charge TEXT,
                    faculty_list TEXT,
                    room_code TEXT,
                    version_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            # Table exists - check if we need to add any missing columns
            schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
            existing_cols = {col[1] for col in schema}
            
            # Add missing columns if needed (safely)
            optional_columns = [
                ('version_id', 'INTEGER'),
                ('bridge_group_id', 'TEXT'),
                ('bridge_position', 'INTEGER DEFAULT 1'),
                ('bridge_length', 'INTEGER DEFAULT 1'),
                ('room_code', 'TEXT'),
            ]
            
            for col_name, col_type in optional_columns:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE timetable_slots ADD COLUMN {col_name} {col_type}"))
                    except:
                        pass  # Column might already exist or other issue


def get_template_periods(engine: Engine, ay: str, degree: str, term: int) -> List[Dict]:
    """Get periods from published template"""
    with engine.connect() as conn:
        template = conn.execute(text("""
            SELECT id FROM day_templates
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
            AND status = 'published'
            ORDER BY (year IS NOT NULL) + (division_code IS NOT NULL) DESC
            LIMIT 1
        """), {'ay': ay, 'deg': degree, 'term': term}).fetchone()
        
        if not template:
            return []
        
        slots = conn.execute(text("""
            SELECT slot_index as id, slot_label as label,
                   fixed_start_time as start_time, fixed_end_time as end_time,
                   is_teaching_slot, duration_min
            FROM day_template_slots
            WHERE template_id = :tid AND is_teaching_slot = 1
            ORDER BY slot_index
        """), {'tid': template[0]}).fetchall()
        
        return [dict(s._mapping) for s in slots]


def get_distribution_subjects(engine: Engine, ay: str, degree: str, year: int, term: int, div: str = None) -> List[Dict]:
    """Get subjects from weekly distribution"""
    with engine.connect() as conn:
        query = """
            SELECT DISTINCT
                wsd.subject_code,
                COALESCE(sc.subject_name, wsd.subject_code) as subject_name,
                wsd.subject_type,
                wsd.division_code,
                wsd.offering_id,
                wsd.subject_code || ' - ' || COALESCE(sc.subject_name, wsd.subject_code) as display_name
            FROM weekly_subject_distribution wsd
            LEFT JOIN subjects_catalog sc ON wsd.subject_code = sc.subject_code
            WHERE wsd.ay_label = :ay
              AND wsd.degree_code = :deg
              AND wsd.year = :year
              AND wsd.term = :term
        """
        params = {'ay': ay, 'deg': degree, 'year': year, 'term': term}
        
        if div:
            query += " AND (wsd.division_code = :div OR wsd.division_code IS NULL)"
            params['div'] = div
        
        query += " ORDER BY wsd.subject_code"
        
        result = conn.execute(text(query), params)
        return [dict(r._mapping) for r in result]


def get_faculty_list(engine: Engine, degree: str) -> List[Dict]:
    """Get faculty for a degree"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT
                fp.id as faculty_id,
                fp.email,
                fp.name as faculty_name,
                fa.designation
            FROM faculty_profiles fp
            JOIN faculty_affiliations fa ON fp.email = fa.email
            WHERE fa.degree_code = :deg AND fa.active = 1
            ORDER BY fp.name
        """), {'deg': degree})
        return [dict(r._mapping) for r in result]


def get_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int, ver: int = None) -> Optional[Dict]:
    """Get existing slot assignment"""
    with engine.connect() as conn:
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        # Check if version_id column exists
        has_version_id = False
        try:
            schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
            has_version_id = any(col[1] == 'version_id' for col in schema)
        except:
            pass
        
        query = """
            SELECT ts.*, sc.subject_name, fp.name as faculty_name
            FROM timetable_slots ts
            LEFT JOIN subjects_catalog sc ON ts.subject_code = sc.subject_code
            LEFT JOIN faculty_profiles fp ON ts.faculty_in_charge = fp.email
            WHERE ts.ay_label = :ay AND ts.degree_code = :deg
              AND ts.year = :year AND ts.term = :term
              AND COALESCE(ts.division_code, '') = COALESCE(:div, '')
              AND ts.day_of_week = :day AND ts.period_id = :per
              AND ts.status = 'active'
        """
        
        if ver and has_version_id:
            query += " AND ts.version_id = :ver"
            params['ver'] = ver
        
        result = conn.execute(text(query), params).fetchone()
        return dict(result._mapping) if result else None


def save_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int,
              subj: str, stype: str, faculty_email: str = None, ver: int = None):
    """Save a slot assignment"""
    ensure_tables(engine)
    
    with engine.begin() as conn:
        # Check if version_id column exists
        has_version_id = False
        try:
            schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
            has_version_id = any(col[1] == 'version_id' for col in schema)
        except:
            pass
        
        # Delete existing
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        delete_query = """
            DELETE FROM timetable_slots
            WHERE ay_label = :ay AND degree_code = :deg
              AND year = :year AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND day_of_week = :day AND period_id = :per
        """
        
        if ver and has_version_id:
            delete_query += " AND COALESCE(version_id, 0) = COALESCE(:ver, 0)"
            params['ver'] = ver
        
        conn.execute(text(delete_query), params)
        
        # Insert new - build query based on available columns
        if has_version_id:
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, year, term, division_code,
                    day_of_week, period_id, subject_code, subject_type,
                    faculty_in_charge, faculty_list, version_id, status
                ) VALUES (
                    :ay, :deg, :year, :term, :div,
                    :day, :per, :subj, :stype,
                    :fac, :fac, :ver, 'active'
                )
            """), {
                'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                'year': year, 'term': ctx['term'], 'div': div,
                'day': day, 'per': period, 'subj': subj, 'stype': stype,
                'fac': faculty_email, 'ver': ver
            })
        else:
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, year, term, division_code,
                    day_of_week, period_id, subject_code, subject_type,
                    faculty_in_charge, faculty_list, status
                ) VALUES (
                    :ay, :deg, :year, :term, :div,
                    :day, :per, :subj, :stype,
                    :fac, :fac, 'active'
                )
            """), {
                'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                'year': year, 'term': ctx['term'], 'div': div,
                'day': day, 'per': period, 'subj': subj, 'stype': stype,
                'fac': faculty_email
            })


def delete_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int, ver: int = None):
    """Delete a slot assignment"""
    with engine.begin() as conn:
        # Check if version_id column exists
        has_version_id = False
        try:
            schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
            has_version_id = any(col[1] == 'version_id' for col in schema)
        except:
            pass
        
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        query = """
            DELETE FROM timetable_slots
            WHERE ay_label = :ay AND degree_code = :deg
              AND year = :year AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND day_of_week = :day AND period_id = :per
        """
        
        if ver and has_version_id:
            query += " AND COALESCE(version_id, 0) = COALESCE(:ver, 0)"
            params['ver'] = ver
        
        conn.execute(text(query), params)


# ============================================================================
# BRIDGING FUNCTIONS
# ============================================================================

def create_bridge(engine: Engine, ctx: Dict, year: int, div: str, day: int, 
                  start_period: int, bridge_length: int, subj: str, stype: str, 
                  faculty_email: str = None, ver: int = None):
    """Create a bridged (merged) slot spanning multiple periods"""
    ensure_tables(engine)
    
    bridge_id = str(uuid.uuid4())[:8]  # Short unique ID
    
    with engine.begin() as conn:
        # Check schema
        schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
        has_version_id = any(col[1] == 'version_id' for col in schema)
        
        # Delete any existing slots in the bridge range
        for i in range(bridge_length):
            period_id = start_period + i
            params = {
                'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                'year': year, 'term': ctx['term'], 'div': div,
                'day': day, 'per': period_id
            }
            conn.execute(text("""
                DELETE FROM timetable_slots
                WHERE ay_label = :ay AND degree_code = :deg
                  AND year = :year AND term = :term
                  AND COALESCE(division_code, '') = COALESCE(:div, '')
                  AND day_of_week = :day AND period_id = :per
            """), params)
        
        # Create bridge slots
        for i in range(bridge_length):
            period_id = start_period + i
            position = i + 1
            
            if has_version_id:
                conn.execute(text("""
                    INSERT INTO timetable_slots (
                        ay_label, degree_code, year, term, division_code,
                        day_of_week, period_id, subject_code, subject_type,
                        faculty_in_charge, faculty_list, 
                        bridge_group_id, bridge_position, bridge_length,
                        version_id, status
                    ) VALUES (
                        :ay, :deg, :year, :term, :div,
                        :day, :per, :subj, :stype,
                        :fac, :fac,
                        :bridge_id, :pos, :len,
                        :ver, 'active'
                    )
                """), {
                    'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                    'year': year, 'term': ctx['term'], 'div': div,
                    'day': day, 'per': period_id, 'subj': subj, 'stype': stype,
                    'fac': faculty_email, 'bridge_id': bridge_id, 
                    'pos': position, 'len': bridge_length, 'ver': ver
                })
            else:
                conn.execute(text("""
                    INSERT INTO timetable_slots (
                        ay_label, degree_code, year, term, division_code,
                        day_of_week, period_id, subject_code, subject_type,
                        faculty_in_charge, faculty_list,
                        bridge_group_id, bridge_position, bridge_length,
                        status
                    ) VALUES (
                        :ay, :deg, :year, :term, :div,
                        :day, :per, :subj, :stype,
                        :fac, :fac,
                        :bridge_id, :pos, :len,
                        'active'
                    )
                """), {
                    'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                    'year': year, 'term': ctx['term'], 'div': div,
                    'day': day, 'per': period_id, 'subj': subj, 'stype': stype,
                    'fac': faculty_email, 'bridge_id': bridge_id,
                    'pos': position, 'len': bridge_length
                })
    
    return bridge_id


def delete_bridge(engine: Engine, bridge_id: str):
    """Delete all slots in a bridge"""
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM timetable_slots WHERE bridge_group_id = :bid
        """), {'bid': bridge_id})


def extend_bridge(engine: Engine, ctx: Dict, bridge_id: str, additional_periods: int = 1):
    """Extend a bridge by adding more periods"""
    with engine.connect() as conn:
        # Get bridge info
        bridge = conn.execute(text("""
            SELECT * FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position = 1
        """), {'bid': bridge_id}).fetchone()
        
        if not bridge:
            return False
        
        bridge = dict(bridge._mapping)
        current_length = bridge['bridge_length']
        new_length = current_length + additional_periods
        last_period = bridge['period_id'] + current_length - 1
        
    with engine.begin() as conn:
        # Update existing bridge length
        conn.execute(text("""
            UPDATE timetable_slots SET bridge_length = :len WHERE bridge_group_id = :bid
        """), {'len': new_length, 'bid': bridge_id})
        
        # Add new periods
        for i in range(additional_periods):
            period_id = last_period + i + 1
            position = current_length + i + 1
            
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, year, term, division_code,
                    day_of_week, period_id, subject_code, subject_type,
                    faculty_in_charge, faculty_list,
                    bridge_group_id, bridge_position, bridge_length, status
                ) VALUES (
                    :ay, :deg, :year, :term, :div,
                    :day, :per, :subj, :stype,
                    :fac, :fac,
                    :bid, :pos, :len, 'active'
                )
            """), {
                'ay': bridge['ay_label'], 'deg': bridge['degree_code'],
                'year': bridge['year'], 'term': bridge['term'], 
                'div': bridge.get('division_code'),
                'day': bridge['day_of_week'], 'per': period_id,
                'subj': bridge['subject_code'], 'stype': bridge.get('subject_type'),
                'fac': bridge.get('faculty_in_charge'), 'bid': bridge_id,
                'pos': position, 'len': new_length
            })
    
    return True


def shrink_bridge(engine: Engine, bridge_id: str, remove_periods: int = 1):
    """Shrink a bridge by removing periods from the end"""
    with engine.connect() as conn:
        bridge = conn.execute(text("""
            SELECT bridge_length FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position = 1
        """), {'bid': bridge_id}).fetchone()
        
        if not bridge or bridge[0] <= 1:
            return False
        
        current_length = bridge[0]
        new_length = max(1, current_length - remove_periods)
    
    with engine.begin() as conn:
        # Remove extra periods
        conn.execute(text("""
            DELETE FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position > :len
        """), {'bid': bridge_id, 'len': new_length})
        
        # Update remaining
        if new_length == 1:
            # Unmerge to single
            conn.execute(text("""
                UPDATE timetable_slots 
                SET bridge_group_id = NULL, bridge_position = 1, bridge_length = 1
                WHERE bridge_group_id = :bid
            """), {'bid': bridge_id})
        else:
            conn.execute(text("""
                UPDATE timetable_slots SET bridge_length = :len WHERE bridge_group_id = :bid
            """), {'len': new_length, 'bid': bridge_id})
    
    return True


def unmerge_bridge(engine: Engine, bridge_id: str):
    """Convert bridge back to individual single-period slots"""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE timetable_slots 
            SET bridge_group_id = NULL, bridge_position = 1, bridge_length = 1
            WHERE bridge_group_id = :bid
        """), {'bid': bridge_id})


def get_day_slots_with_bridges(engine: Engine, ctx: Dict, year: int, div: str, day: int, ver: int = None) -> Dict:
    """Get all slots for a day, organized for bridge rendering"""
    with engine.connect() as conn:
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div, 'day': day
        }
        
        # Check schema
        schema = conn.execute(text("PRAGMA table_info(timetable_slots)")).fetchall()
        has_version_id = any(col[1] == 'version_id' for col in schema)
        
        query = """
            SELECT ts.*, sc.subject_name, fp.name as faculty_name
            FROM timetable_slots ts
            LEFT JOIN subjects_catalog sc ON ts.subject_code = sc.subject_code
            LEFT JOIN faculty_profiles fp ON ts.faculty_in_charge = fp.email
            WHERE ts.ay_label = :ay AND ts.degree_code = :deg
              AND ts.year = :year AND ts.term = :term
              AND COALESCE(ts.division_code, '') = COALESCE(:div, '')
              AND ts.day_of_week = :day
              AND ts.status = 'active'
            ORDER BY ts.period_id
        """
        
        if ver and has_version_id:
            query = query.replace("AND ts.status", "AND ts.version_id = :ver AND ts.status")
            params['ver'] = ver
        
        rows = conn.execute(text(query), params).fetchall()
        
        # Organize by period
        slots_map = {}
        for row in rows:
            slot = dict(row._mapping)
            pid = slot['period_id']
            slots_map[pid] = slot
        
        return slots_map


def get_divisions(engine: Engine, ctx: Dict) -> List[str]:
    """Get divisions for context"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT division_code
            FROM weekly_subject_distribution
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
              AND division_code IS NOT NULL AND division_code != ''
            ORDER BY division_code
        """), {'ay': ctx['ay_label'], 'deg': ctx['degree_code'], 'term': ctx['term']})
        return [r[0] for r in result]


def get_years_in_distribution(engine: Engine, ctx: Dict) -> List[int]:
    """Get years that have subjects in distribution"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT year
            FROM weekly_subject_distribution
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
            ORDER BY year
        """), {'ay': ctx['ay_label'], 'deg': ctx['degree_code'], 'term': ctx['term']})
        return [r[0] for r in result]


# ============================================================================
# INTERACTIVE CELL RENDERER
# ============================================================================

def render_cell(engine: Engine, ctx: Dict, year: int, div: str, day: int, day_name: str,
                period: Dict, periods_list: List[Dict], edit_mode: bool, show_fac: bool, 
                bridge_mode: bool, ver: int = None):
    """Render a single timetable cell with interactive dropdowns and bridge support"""
    
    pid = period['id']
    key = f"c_{day}_{pid}_{year}_{div or 'X'}"
    year_bg = YEAR_COLORS.get(year, '#FFF')
    
    # Get existing slot
    existing = get_slot(engine, ctx, year, div, day, pid, ver)
    
    # Check if this is part of a bridge
    is_bridge_start = existing and existing.get('bridge_group_id') and existing.get('bridge_position') == 1
    is_bridge_continuation = existing and existing.get('bridge_group_id') and existing.get('bridge_position', 1) > 1
    bridge_length = existing.get('bridge_length', 1) if existing else 1
    bridge_id = existing.get('bridge_group_id') if existing else None
    
    # Skip rendering if this is a continuation of a bridge (it's merged into the first cell visually)
    if is_bridge_continuation:
        # Show a small indicator that this cell is merged
        st.markdown(
            f"""<div style="background: linear-gradient(135deg, {year_bg} 0%, #ddd 100%); 
                padding: 6px; border-radius: 4px; min-height: 50px; 
                border: 1px dashed #999; text-align: center; opacity: 0.6;">
                <span style="font-size: 10px; color: #666;">⬅️ merged</span>
            </div>""",
            unsafe_allow_html=True
        )
        return
    
    if existing and not is_bridge_continuation:
        # Display existing assignment
        subj = existing.get('subject_name') or existing.get('subject_code', 'Unknown')
        fac = existing.get('faculty_name', '')
        
        # Different styling for bridged vs single slots
        if is_bridge_start:
            border_style = "2px solid #1976D2"
            merge_indicator = f'<div style="font-size:9px; color:#1976D2; margin-top:4px;">🔗 {bridge_length} periods</div>'
        else:
            border_style = "1px solid #ccc"
            merge_indicator = ""
        
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 6px; border-radius: 4px; 
                min-height: 50px; font-size: 11px; border: {border_style};">
                <strong>{subj}</strong>
                {'<br><span style="color:#666">' + fac + '</span>' if show_fac and fac else ''}
                {merge_indicator}
            </div>""",
            unsafe_allow_html=True
        )
        
        if edit_mode:
            if is_bridge_start:
                # Bridge controls
                c1, c2, c3 = st.columns(3)
                if c1.button("➕", key=f"ext_{key}", help="Extend bridge"):
                    extend_bridge(engine, bridge_id)
                    st.rerun()
                if c2.button("➖", key=f"shr_{key}", help="Shrink bridge"):
                    shrink_bridge(engine, bridge_id)
                    st.rerun()
                if c3.button("🔓", key=f"unm_{key}", help="Unmerge"):
                    unmerge_bridge(engine, bridge_id)
                    st.rerun()
                
                c4, c5 = st.columns(2)
                if c4.button("✏️", key=f"e_{key}", help="Edit"):
                    st.session_state[f"edit_{key}"] = True
                    st.rerun()
                if c5.button("🗑️", key=f"d_{key}", help="Delete"):
                    delete_bridge(engine, bridge_id)
                    st.rerun()
            else:
                # Single slot controls
                c1, c2 = st.columns(2)
                if c1.button("✏️", key=f"e_{key}", help="Edit", use_container_width=True):
                    st.session_state[f"edit_{key}"] = True
                    st.rerun()
                if c2.button("🗑️", key=f"d_{key}", help="Delete", use_container_width=True):
                    delete_slot(engine, ctx, year, div, day, pid, ver)
                    st.rerun()
    else:
        # Empty cell
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 6px; border-radius: 4px; 
                min-height: 50px; border: 1px solid #ccc; text-align: center;">
            </div>""",
            unsafe_allow_html=True
        )
        
        if edit_mode:
            if st.button("➕", key=f"a_{key}", help="Add Subject", use_container_width=True):
                st.session_state[f"edit_{key}"] = True
                st.session_state[f"bridge_mode_{key}"] = bridge_mode
                st.rerun()
    
    # Edit form in expander
    if edit_mode and st.session_state.get(f"edit_{key}"):
        with st.expander(f"📝 {day_name} P{pid} Y{year}", expanded=True):
            render_editor(engine, ctx, year, div, day, pid, periods_list, key, existing, 
                         st.session_state.get(f"bridge_mode_{key}", bridge_mode), ver)


def render_editor(engine: Engine, ctx: Dict, year: int, div: str, day: int, 
                  period: int, periods_list: List[Dict], key: str, existing: Optional[Dict], 
                  bridge_mode: bool, ver: int = None):
    """Render the editor form with dropdowns and bridge options"""
    
    # Get subjects for this year
    subjects = get_distribution_subjects(engine, ctx['ay_label'], ctx['degree_code'], year, ctx['term'], div)
    
    if not subjects:
        st.warning(f"No subjects in distribution for Year {year}")
        if st.button("Cancel", key=f"x1_{key}"):
            st.session_state[f"edit_{key}"] = False
            st.rerun()
        return
    
    # Subject dropdown
    subj_opts = ["-- Select Subject --"] + [s['display_name'] for s in subjects]
    
    curr_idx = 0
    if existing and existing.get('subject_code'):
        for i, s in enumerate(subjects):
            if s['subject_code'] == existing['subject_code']:
                curr_idx = i + 1
                break
    
    sel_subj = st.selectbox("Subject", subj_opts, index=curr_idx, key=f"subj_{key}")
    
    if sel_subj != "-- Select Subject --":
        # Get selected subject details
        subj_data = next((s for s in subjects if s['display_name'] == sel_subj), None)
        
        if subj_data:
            st.caption(f"Type: {subj_data.get('subject_type', 'N/A')}")
            
            # Faculty dropdown
            faculty = get_faculty_list(engine, ctx['degree_code'])
            
            if faculty:
                fac_opts = ["-- Select Faculty --"] + [f"{f['faculty_name']} ({f.get('designation', '')})" for f in faculty]
                
                fac_idx = 0
                if existing and existing.get('faculty_in_charge'):
                    for i, f in enumerate(faculty):
                        if f['email'] == existing['faculty_in_charge']:
                            fac_idx = i + 1
                            break
                
                sel_fac = st.selectbox("Faculty", fac_opts, index=fac_idx, key=f"fac_{key}")
                
                # Bridge options (when bridge mode is enabled)
                bridge_length = 1
                if bridge_mode:
                    st.markdown("---")
                    st.markdown("**🔗 Bridge (Merge Periods)**")
                    
                    # Calculate max possible bridge length
                    current_period_idx = next((i for i, p in enumerate(periods_list) if p['id'] == period), 0)
                    max_bridge = len(periods_list) - current_period_idx
                    
                    if max_bridge > 1:
                        bridge_length = st.slider(
                            "Number of periods to merge",
                            min_value=1,
                            max_value=min(max_bridge, 6),  # Cap at 6
                            value=existing.get('bridge_length', 1) if existing else 1,
                            key=f"bridge_{key}"
                        )
                        
                        if bridge_length > 1:
                            # Show which periods will be merged
                            merged_periods = [periods_list[current_period_idx + i]['label'] 
                                            for i in range(bridge_length) 
                                            if current_period_idx + i < len(periods_list)]
                            st.info(f"Will merge: {' + '.join(merged_periods)}")
                    else:
                        st.caption("This is the last period - cannot create bridge")
                
                # Buttons
                c1, c2 = st.columns(2)
                
                if c1.button("💾 Save", key=f"sv_{key}", type="primary", use_container_width=True):
                    fac_email = None
                    if sel_fac != "-- Select Faculty --":
                        fac_data = faculty[fac_opts.index(sel_fac) - 1]
                        fac_email = fac_data['email']
                    
                    if bridge_length > 1:
                        # Create bridge
                        create_bridge(
                            engine, ctx, year, div, day, period, bridge_length,
                            subj_data['subject_code'], subj_data.get('subject_type'),
                            fac_email, ver
                        )
                    else:
                        # Single slot
                        save_slot(engine, ctx, year, div, day, period,
                                 subj_data['subject_code'], subj_data.get('subject_type'),
                                 fac_email, ver)
                    
                    st.session_state[f"edit_{key}"] = False
                    st.success("✅ Saved!")
                    st.rerun()
                
                if c2.button("Cancel", key=f"x2_{key}", use_container_width=True):
                    st.session_state[f"edit_{key}"] = False
                    st.rerun()
            else:
                st.info("No faculty found for this degree")
                if st.button("Cancel", key=f"x3_{key}"):
                    st.session_state[f"edit_{key}"] = False
                    st.rerun()
    else:
        if st.button("Cancel", key=f"x4_{key}"):
            st.session_state[f"edit_{key}"] = False
            st.rerun()


# ============================================================================
# MAIN GRID RENDERER
# ============================================================================

def render_complete_excel_timetable(context: Dict, engine: Engine):
    """
    Main entry point - renders the interactive timetable grid
    
    This replaces the static HTML version with working dropdown menus
    """
    
    ensure_tables(engine)
    
    # Initialize state
    if 'tt_edit_mode' not in st.session_state:
        st.session_state.tt_edit_mode = False
    if 'tt_show_faculty' not in st.session_state:
        st.session_state.tt_show_faculty = True
    
    # Get current version
    ver = None
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, version_code, version_name, status
            FROM timetable_versions
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
            ORDER BY created_at DESC LIMIT 1
        """), {
            'ay': context.get('ay_label'),
            'deg': context.get('degree_code'),
            'term': context.get('term')
        }).fetchone()
        
        if result:
            ver = result[0]
            st.caption(f"📋 Version: {result[1]} | Status: {result[3]}")
    
    # Controls
    st.markdown("### 📅 Weekly Timetable")
    
    col1, col2, col3, col4 = st.columns([1.5, 1.5, 1.5, 1])
    
    with col1:
        mode = st.radio("Mode", ["👁️ View Only", "✏️ Edit Mode"], 
                       index=1 if st.session_state.tt_edit_mode else 0,
                       horizontal=True, key="tt_mode_radio")
        st.session_state.tt_edit_mode = (mode == "✏️ Edit Mode")
    
    with col2:
        st.session_state.tt_show_faculty = st.checkbox(
            "Show Faculty Names", 
            value=st.session_state.tt_show_faculty,
            key="tt_show_fac_check"
        )
    
    with col3:
        bridge_mode = st.checkbox("🔗 Bridge Mode (Merge Cells)", key="tt_bridge_check",
                                 help="Enable to merge periods")
    
    with col4:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    if st.session_state.tt_edit_mode:
        st.info("✏️ **Edit Mode Active:** Click ➕ to add subjects. Use dropdowns to select subject and faculty.")
    
    # Get periods
    periods = get_template_periods(engine, context['ay_label'], context['degree_code'], context['term'])
    
    if not periods:
        st.error("❌ No published template found. Please publish a timegrid template first.")
        st.stop()
    
    # Get years and divisions
    years = get_years_in_distribution(engine, context) or [1, 2, 3, 4]
    divisions = get_divisions(engine, context) or [None]
    
    # Days
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    day_map = {d: i + 1 for i, d in enumerate(days)}
    
    # Render each day
    for day_name in days:
        day_num = day_map[day_name]
        
        # Day header
        st.markdown(
            f'<div style="background: {HEADER_COLORS["day"]}; padding: 10px; '
            f'text-align: center; font-weight: bold; font-size: 16px; '
            f'color: white; margin-top: 15px; border-radius: 4px;">'
            f'{day_name.upper()}</div>',
            unsafe_allow_html=True
        )
        
        # Period headers
        cols = st.columns([1.5] + [1] * len(periods))
        cols[0].markdown("**PERIODS**")
        for i, p in enumerate(periods):
            cols[i + 1].markdown(f"**{p['label']}**")
        
        # Time row
        time_cols = st.columns([1.5] + [1] * len(periods))
        time_cols[0].markdown("*TIME*")
        for i, p in enumerate(periods):
            t = f"{p.get('start_time', '')} - {p.get('end_time', '')}"
            time_cols[i + 1].caption(t)
        
        # Year rows
        for yr in years:
            for div in divisions:
                sem = ['I', 'III', 'V', 'VII', 'IX'][yr - 1] if yr <= 5 else str(yr * 2 - 1)
                ord_name = ['1st', '2nd', '3rd', '4th', '5th'][yr - 1] if yr <= 5 else f'{yr}th'
                div_lbl = f" ({div})" if div else ""
                
                row_cols = st.columns([1.5] + [1] * len(periods))
                
                # Year label
                row_cols[0].markdown(
                    f'<div style="background: {YEAR_COLORS.get(yr, "#FFF")}; '
                    f'padding: 8px; font-weight: bold; border-radius: 4px; '
                    f'border: 1px solid #ccc; font-size: 12px;">'
                    f'{ord_name} Year Semester {sem}{div_lbl}</div>',
                    unsafe_allow_html=True
                )
                
                # Period cells
                for i, period in enumerate(periods):
                    with row_cols[i + 1]:
                        render_cell(
                            engine, context, yr, div, day_num, day_name,
                            period, periods, st.session_state.tt_edit_mode,
                            st.session_state.tt_show_faculty, bridge_mode, ver
                        )
        
        st.markdown("---")
    
    # Stats
    with st.expander("📊 Timetable Statistics"):
        with engine.connect() as conn:
            stats = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_slots,
                    COUNT(DISTINCT subject_code) as subjects,
                    COUNT(DISTINCT faculty_in_charge) as faculty
                FROM timetable_slots
                WHERE ay_label = :ay AND degree_code = :deg AND term = :term
                  AND status = 'active'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term']
            }).fetchone()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Slots", stats[0] if stats else 0)
            c2.metric("Subjects", stats[1] if stats else 0)
            c3.metric("Faculty", stats[2] if stats else 0)


if __name__ == "__main__":
    st.error("Import this module from app_weekly_planner.py")
