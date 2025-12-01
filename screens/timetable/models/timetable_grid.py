"""
Timetable Grid Tab - FIXED VERSION with Dropdown Menus
Provides interactive grid-based timetable creation with dropdown subject/faculty selection
Compatible with app_weekly_planner Context architecture
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.engine import Engine
from sqlalchemy import text

# ============================================================================
# DATABASE HELPER FUNCTIONS
# ============================================================================

def get_semesters(engine: Engine) -> List[Dict]:
    """Get list of semesters"""
    with engine.connect() as conn:
        df = pd.read_sql_query("""
            SELECT semester_id, year_level, semester_number, 
                   year_level || ' Year Semester ' || semester_number as display_name
            FROM semesters
            ORDER BY year_level, semester_number
        """, conn)
        return df.to_dict('records')


def get_divisions_for_semester(semester_id: int, engine: Engine) -> List[str]:
    """Get divisions for a semester"""
    with engine.connect() as conn:
        df = pd.read_sql_query(text("""
            SELECT DISTINCT division_code
            FROM subject_offerings
            WHERE semester_id = :sem
            AND division_code IS NOT NULL
            AND TRIM(division_code) != ''
            ORDER BY division_code
        """), conn, params={'sem': semester_id})
        return df['division_code'].tolist() if not df.empty else []


def get_subjects_for_division(semester_id: int, division_code: str, engine: Engine) -> List[Dict]:
    """Get subjects available for a specific division"""
    with engine.connect() as conn:
        df = pd.read_sql_query(text("""
            SELECT DISTINCT 
                so.subject_code,
                cs.subject_name,
                so.subject_code || ' - ' || cs.subject_name as display_name,
                so.subject_type
            FROM subject_offerings so
            JOIN comprehensive_subjects cs ON so.subject_code = cs.subject_code
            WHERE so.semester_id = :sem
            AND (so.division_code = :div OR so.division_code IS NULL)
            ORDER BY so.subject_code
        """), conn, params={'sem': semester_id, 'div': division_code})
        return df.to_dict('records')


def get_faculty_for_subject(subject_code: str, semester_id: int, engine: Engine) -> List[Dict]:
    """Get faculty teaching a subject"""
    with engine.connect() as conn:
        df = pd.read_sql_query(text("""
            SELECT DISTINCT f.faculty_id, f.name
            FROM faculty f
            JOIN subject_offerings so ON f.faculty_id = so.faculty_id
            WHERE so.subject_code = :subj AND so.semester_id = :sem
            ORDER BY f.name
        """), conn, params={'subj': subject_code, 'sem': semester_id})
        return df.to_dict('records')


def get_period_configuration(engine: Engine) -> List[Dict]:
    """Get period configuration"""
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query("""
                SELECT period_number, period_name, start_time, end_time, period_type
                FROM periods
                ORDER BY period_number
            """, conn)
            return df.to_dict('records')
    except:
        # Fallback default configuration
        return [
            {'period_number': 1, 'period_name': 'Period 1', 'start_time': '09:00', 'end_time': '09:50', 'period_type': 'lecture'},
            {'period_number': 2, 'period_name': 'Period 2', 'start_time': '09:50', 'end_time': '10:40', 'period_type': 'lecture'},
            {'period_number': 3, 'period_name': 'Period 3', 'start_time': '10:40', 'end_time': '11:30', 'period_type': 'lecture'},
            {'period_number': 4, 'period_name': 'Period 4', 'start_time': '11:30', 'end_time': '12:20', 'period_type': 'lecture'},
            {'period_number': 5, 'period_name': 'Break', 'start_time': '12:20', 'end_time': '01:00', 'period_type': 'break'},
            {'period_number': 6, 'period_name': 'Period 5', 'start_time': '01:00', 'end_time': '01:50', 'period_type': 'lecture'},
            {'period_number': 7, 'period_name': 'Period 6', 'start_time': '01:50', 'end_time': '02:40', 'period_type': 'lecture'},
            {'period_number': 8, 'period_name': 'Period 7', 'start_time': '02:40', 'end_time': '03:30', 'period_type': 'lecture'},
        ]


def get_timetable_entry(semester_id: int, division_code: str, day: str, period_number: int, engine: Engine) -> Optional[Dict]:
    """Get existing timetable entry"""
    with engine.connect() as conn:
        df = pd.read_sql_query(text("""
            SELECT tt.*, cs.subject_name, f.name as faculty_name
            FROM timetable_grid tt
            LEFT JOIN comprehensive_subjects cs ON tt.subject_code = cs.subject_code
            LEFT JOIN faculty f ON tt.faculty_id = f.faculty_id
            WHERE tt.semester_id = :sem 
            AND tt.division_code = :div
            AND tt.day_of_week = :day
            AND tt.period_number = :per
        """), conn, params={'sem': semester_id, 'div': division_code, 'day': day, 'per': period_number})
        
        if not df.empty:
            return df.iloc[0].to_dict()
        return None


def save_timetable_entry(semester_id: int, division_code: str, day: str, period_number: int,
                        subject_code: Optional[str], faculty_id: Optional[int],
                        room_number: Optional[str], engine: Engine):
    """Save or update timetable entry"""
    with engine.begin() as conn:
        # Check if entry exists
        existing = get_timetable_entry(semester_id, division_code, day, period_number, engine)
        
        if subject_code is None or subject_code == "":
            # Delete entry if subject is cleared
            if existing:
                conn.execute(text("""
                    DELETE FROM timetable_grid
                    WHERE semester_id = :sem AND division_code = :div 
                    AND day_of_week = :day AND period_number = :per
                """), {'sem': semester_id, 'div': division_code, 'day': day, 'per': period_number})
        else:
            if existing:
                # Update existing entry
                conn.execute(text("""
                    UPDATE timetable_grid
                    SET subject_code = :subj, faculty_id = :fac, room_number = :room
                    WHERE semester_id = :sem AND division_code = :div
                    AND day_of_week = :day AND period_number = :per
                """), {'subj': subject_code, 'fac': faculty_id, 'room': room_number, 
                       'sem': semester_id, 'div': division_code, 'day': day, 'per': period_number})
            else:
                # Insert new entry
                conn.execute(text("""
                    INSERT INTO timetable_grid 
                    (semester_id, division_code, day_of_week, period_number, 
                     subject_code, faculty_id, room_number)
                    VALUES (:sem, :div, :day, :per, :subj, :fac, :room)
                """), {'sem': semester_id, 'div': division_code, 'day': day, 'per': period_number,
                       'subj': subject_code, 'fac': faculty_id, 'room': room_number})


def check_conflicts(semester_id: int, division_code: str, day: str, period_number: int,
                   faculty_id: Optional[int], engine: Engine) -> List[str]:
    """Check for scheduling conflicts"""
    conflicts = []
    
    if faculty_id is None:
        return conflicts
    
    with engine.connect() as conn:
        # Check faculty conflict
        df = pd.read_sql_query(text("""
            SELECT division_code, cs.subject_name
            FROM timetable_grid tt
            JOIN comprehensive_subjects cs ON tt.subject_code = cs.subject_code
            WHERE tt.semester_id = :sem 
            AND tt.day_of_week = :day
            AND tt.period_number = :per
            AND tt.faculty_id = :fac
            AND tt.division_code != :div
        """), conn, params={'sem': semester_id, 'day': day, 'per': period_number, 
                            'fac': faculty_id, 'div': division_code})
        
        for _, row in df.iterrows():
            conflicts.append(f"Faculty is teaching {row['subject_name']} to {row['division_code']}")
    
    return conflicts


# ============================================================================
# UI RENDERING FUNCTIONS
# ============================================================================

def render_timetable_cell(semester_id: int, division_code: str, day: str, period: Dict,
                         subjects: List[Dict], col_idx: int, engine: Engine):
    """Render a single timetable cell with dropdown"""
    
    period_number = period['period_number']
    period_type = period.get('period_type', 'lecture')
    
    # Get existing entry
    existing = get_timetable_entry(semester_id, division_code, day, period_number, engine)
    
    # Create unique key for this cell
    cell_key = f"cell_{semester_id}_{division_code}_{day}_{period_number}_{col_idx}"
    
    # Skip if it's a break period
    if period_type.lower() == 'break':
        st.markdown("**Break**")
        return
    
    # Prepare subject options
    subject_options = ["-- Select Subject --"] + [s['display_name'] for s in subjects]
    
    # Find current selection index
    current_idx = 0
    if existing and existing.get('subject_code'):
        for idx, subj in enumerate(subjects):
            if subj['subject_code'] == existing['subject_code']:
                current_idx = idx + 1
                break
    
    # Subject dropdown
    selected_subject = st.selectbox(
        "Subject",
        options=subject_options,
        index=current_idx,
        key=f"subject_{cell_key}",
        label_visibility="collapsed"
    )
    
    # If a subject is selected
    if selected_subject != "-- Select Subject --":
        # Find the selected subject details
        selected_subj = next((s for s in subjects if s['display_name'] == selected_subject), None)
        
        if selected_subj:
            subject_code = selected_subj['subject_code']
            
            # Get faculty for this subject
            faculty_list = get_faculty_for_subject(subject_code, semester_id, engine)
            
            if faculty_list:
                faculty_options = ["-- Select Faculty --"] + [f['name'] for f in faculty_list]
                
                # Find current faculty index
                faculty_idx = 0
                if existing and existing.get('faculty_id'):
                    for idx, fac in enumerate(faculty_list):
                        if fac['faculty_id'] == existing['faculty_id']:
                            faculty_idx = idx + 1
                            break
                
                # Faculty dropdown
                selected_faculty = st.selectbox(
                    "Faculty",
                    options=faculty_options,
                    index=faculty_idx,
                    key=f"faculty_{cell_key}",
                    label_visibility="collapsed"
                )
                
                # If faculty is selected, show save button
                if selected_faculty != "-- Select Faculty --":
                    selected_fac = next((f for f in faculty_list if f['name'] == selected_faculty), None)
                    
                    if selected_fac:
                        faculty_id = selected_fac['faculty_id']
                        
                        # Check for conflicts
                        conflicts = check_conflicts(semester_id, division_code, day, period_number, faculty_id, engine)
                        
                        if conflicts:
                            st.warning("⚠️ " + "; ".join(conflicts))
                        
                        # Save button
                        if st.button("💾 Save", key=f"save_{cell_key}", use_container_width=True):
                            save_timetable_entry(
                                semester_id, division_code, day, period_number,
                                subject_code, faculty_id, None, engine
                            )
                            st.success("Saved!")
                            st.rerun()
                        
                        # Show current assignment if exists
                        if existing:
                            st.caption(f"✓ {existing.get('subject_name', '')} - {existing.get('faculty_name', '')}")
            else:
                st.info("No faculty assigned to this subject")
    
    # Clear button if entry exists
    if existing:
        if st.button("🗑️ Clear", key=f"clear_{cell_key}", use_container_width=True):
            save_timetable_entry(semester_id, division_code, day, period_number, None, None, None, engine)
            st.success("Cleared!")
            st.rerun()


def render_day_timetable(semester_id: int, division_code: str, day: str, periods: List[Dict], subjects: List[Dict], engine: Engine):
    """Render timetable for one day"""
    
    st.markdown(f"### {day.upper()}")
    
    # Create columns for periods
    cols = st.columns(len(periods))
    
    for idx, (col, period) in enumerate(zip(cols, periods)):
        with col:
            st.markdown(f"**{period['period_name']}**")
            st.caption(f"{period.get('start_time', '')} - {period.get('end_time', '')}")
            
            render_timetable_cell(semester_id, division_code, day, period, subjects, idx, engine)


def render_timetable_grid_tab(ctx: Any, engine: Engine):
    """
    Main rendering function for timetable grid tab
    
    Args:
        ctx: Context object from app_weekly_planner (has .ay, .degree, .term, .year attributes)
        engine: SQLAlchemy database engine
    """
    
    st.markdown("### 📅 Weekly Timetable Grid")
    st.caption("Select subjects and faculty using dropdown menus")
    
    # Extract context information
    if hasattr(ctx, 'ay'):
        # Context object from app_weekly_planner
        ay_label = ctx.ay
        degree_code = ctx.degree
        term = ctx.term
        default_year = ctx.year if hasattr(ctx, 'year') else 1
    else:
        # Fallback for dict-based context
        ay_label = ctx.get('ay_label', '')
        degree_code = ctx.get('degree_code', '')
        term = ctx.get('term', 1)
        default_year = ctx.get('year', 1)
    
    # Get semesters
    semesters = get_semesters(engine)
    if not semesters:
        st.error("No semesters found. Please configure semesters first.")
        return
    
    # Selection controls
    col1, col2 = st.columns(2)
    
    with col1:
        # Semester selection (filter by year level from context)
        semester_options = [s['display_name'] for s in semesters]
        
        # Try to find semester matching the context year
        default_sem_idx = 0
        for idx, sem in enumerate(semesters):
            if sem['year_level'] == default_year:
                default_sem_idx = idx
                break
        
        selected_semester_name = st.selectbox("Select Semester", semester_options, index=default_sem_idx)
        
        selected_semester = next((s for s in semesters if s['display_name'] == selected_semester_name), None)
        
        if not selected_semester:
            st.error("Please select a semester")
            return
        
        semester_id = selected_semester['semester_id']
    
    with col2:
        # Division selection
        divisions = get_divisions_for_semester(semester_id, engine)
        
        if not divisions:
            st.warning("No divisions found for this semester. Please configure subject offerings.")
            return
        
        selected_division = st.selectbox("Select Division", divisions)
    
    # Get subjects for selected division
    subjects = get_subjects_for_division(semester_id, selected_division, engine)
    
    if not subjects:
        st.warning("No subjects found for this division.")
        return
    
    # Get period configuration
    periods = get_period_configuration(engine)
    
    if not periods:
        st.error("No periods configured. Please configure periods first.")
        return
    
    st.markdown("---")
    
    # Days of week
    days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
    
    # Render each day
    for day in days:
        with st.expander(f"📅 {day}", expanded=(day == "MONDAY")):
            render_day_timetable(semester_id, selected_division, day, periods, subjects, engine)
        st.markdown("---")
    
    # Summary statistics
    with st.expander("📊 Timetable Summary"):
        with engine.connect() as conn:
            df = pd.read_sql_query(text("""
                SELECT 
                    COUNT(*) as total_slots,
                    COUNT(DISTINCT subject_code) as subjects_scheduled,
                    COUNT(DISTINCT faculty_id) as faculty_involved
                FROM timetable_grid
                WHERE semester_id = :sem AND division_code = :div
            """), conn, params={'sem': semester_id, 'div': selected_division})
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Scheduled Slots", df['total_slots'].iloc[0])
            with col2:
                st.metric("Subjects Scheduled", df['subjects_scheduled'].iloc[0])
            with col3:
                st.metric("Faculty Involved", df['faculty_involved'].iloc[0])


if __name__ == "__main__":
    st.error("This module should be imported by app_weekly_planner.py")
