# screens/academic_years/enhanced_term_dates.py
"""
Enhanced Term Dates Editor - Hierarchy-Aware (Degree/Program/Branch)
Respects binding modes and curriculum governance flags.
NO SCHEMA CHANGES - uses existing batch_term_dates table smartly.
"""

from __future__ import annotations

import datetime
import streamlit as st
import pandas as pd
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import Optional, List, Dict, Tuple
import traceback

__all__ = ["render_enhanced_term_dates"]


# ============================================================
# DATABASE HELPERS
# ============================================================

def _safe_conn(engine: Engine):
    """Get a database connection."""
    try:
        return engine.connect()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.stop()


def get_degree_info(conn, degree_code: str) -> Optional[Dict]:
    """Get degree info including binding mode and curriculum flags."""
    result = conn.execute(
        sa_text("""
            SELECT 
                d.code,
                d.title,
                COALESCE(d.cg_degree, 0) as cg_degree,
                COALESCE(d.cg_program, 0) as cg_program,
                COALESCE(d.cg_branch, 0) as cg_branch,
                COALESCE(sb.binding_mode, 'degree') as binding_mode,
                COALESCE(dss.years, 4) as years,
                COALESCE(dss.terms_per_year, 2) as terms_per_year
            FROM degrees d
            LEFT JOIN semester_binding sb ON sb.degree_code = d.code
            LEFT JOIN degree_semester_struct dss ON dss.degree_code = d.code AND dss.active = 1
            WHERE d.code = :d AND d.active = 1
        """),
        {"d": degree_code}
    ).fetchone()
    
    if not result:
        return None
    
    return {
        "code": result[0],
        "title": result[1],
        "cg_degree": bool(result[2]),
        "cg_program": bool(result[3]),
        "cg_branch": bool(result[4]),
        "binding_mode": result[5],
        "years": int(result[6]),
        "terms_per_year": int(result[7])
    }


def get_programs_for_degree(conn, degree_code: str) -> List[Dict]:
    """Get programs for a degree."""
    rows = conn.execute(
        sa_text("""
            SELECT 
                p.id,
                p.program_code,
                p.program_name,
                COALESCE(pss.years, dss.years, 4) as years,
                COALESCE(pss.terms_per_year, dss.terms_per_year, 2) as terms_per_year
            FROM programs p
            LEFT JOIN program_semester_struct pss ON pss.program_id = p.id AND pss.active = 1
            LEFT JOIN degree_semester_struct dss ON dss.degree_code = p.degree_code AND dss.active = 1
            WHERE LOWER(p.degree_code) = LOWER(:d) AND p.active = 1
            ORDER BY p.sort_order, p.program_code
        """),
        {"d": degree_code}
    ).fetchall()
    
    return [
        {
            "id": r[0],
            "code": r[1],
            "name": r[2],
            "years": int(r[3]),
            "terms_per_year": int(r[4])
        }
        for r in rows
    ]


def get_branches_for_program(conn, program_id: int) -> List[Dict]:
    """Get branches for a program."""
    rows = conn.execute(
        sa_text("""
            SELECT 
                b.id,
                b.branch_code,
                b.branch_name,
                COALESCE(bss.years, pss.years, dss.years, 4) as years,
                COALESCE(bss.terms_per_year, pss.terms_per_year, dss.terms_per_year, 2) as terms_per_year
            FROM branches b
            LEFT JOIN branch_semester_struct bss ON bss.branch_id = b.id AND bss.active = 1
            LEFT JOIN programs p ON p.id = b.program_id
            LEFT JOIN program_semester_struct pss ON pss.program_id = p.id AND pss.active = 1
            LEFT JOIN degree_semester_struct dss ON dss.degree_code = p.degree_code AND dss.active = 1
            WHERE b.program_id = :pid AND b.active = 1
            ORDER BY b.sort_order, b.branch_code
        """),
        {"pid": program_id}
    ).fetchall()
    
    return [
        {
            "id": r[0],
            "code": r[1],
            "name": r[2],
            "years": int(r[3]),
            "terms_per_year": int(r[4])
        }
        for r in rows
    ]


def get_batch_for_year(ay_code: str, year_of_study: int) -> str:
    """Calculate which batch corresponds to a year of study."""
    from screens.academic_years.utils import parse_ay_code
    
    parsed = parse_ay_code(ay_code)
    if not parsed:
        return "UNKNOWN"
    
    start_year = parsed["start_year"]
    batch_year = start_year - (year_of_study - 1)
    return str(batch_year)


def check_batch_exists(conn, degree_code: str, batch_code: str) -> bool:
    """Check if a batch exists."""
    result = conn.execute(
        sa_text("""
            SELECT 1 FROM degree_batches
            WHERE degree_code = :d AND batch_code = :b
            LIMIT 1
        """),
        {"d": degree_code, "b": batch_code}
    ).fetchone()
    return result is not None


def create_storage_key(degree_code: str, program_code: Optional[str] = None, 
                       branch_code: Optional[str] = None) -> str:
    """
    Create a composite key for storing hierarchical data.
    Examples:
    - Degree level: "BSC"
    - Program level: "BSC::COMP"
    - Branch level: "BSC::COMP::AI"
    """
    parts = [degree_code]
    if program_code:
        parts.append(program_code)
    if branch_code:
        parts.append(branch_code)
    return "::".join(parts)


def parse_storage_key(key: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Parse a storage key back into components."""
    parts = key.split("::")
    degree = parts[0]
    program = parts[1] if len(parts) > 1 else None
    branch = parts[2] if len(parts) > 2 else None
    return degree, program, branch


# ============================================================
# TERM DATES OPERATIONS
# ============================================================

def get_next_monday(date: datetime.date) -> datetime.date:
    """Return the next Monday from the given date."""
    days_ahead = 0 - date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    if date.weekday() == 0:
        return date
    return date + datetime.timedelta(days=days_ahead)


def get_previous_friday(date: datetime.date) -> datetime.date:
    """Return the previous Friday from the given date."""
    days_back = (date.weekday() - 4) % 7
    if date.weekday() == 4:
        return date
    return date - datetime.timedelta(days=days_back)


def initialize_term_dates(
    conn,
    storage_key: str,
    batch_code: str,
    ay_code: str,
    num_years: int,
    terms_per_year: int,
    ay_start: datetime.date,
    ay_end: datetime.date,
) -> None:
    """Initialize term dates for a hierarchy level."""
    # Check if already initialized
    existing = conn.execute(
        sa_text("""
            SELECT COUNT(*) FROM batch_term_dates
            WHERE degree_code = :d AND batch_code = :b AND ay_code = :ay
        """),
        {"d": storage_key, "b": batch_code, "ay": ay_code}
    ).scalar()
    
    if existing > 0:
        return  # Already initialized
    
    # Parse AY code for year calculation
    from screens.academic_years.utils import parse_ay_code
    parsed = parse_ay_code(ay_code)
    if not parsed:
        return
    
    ay_start_year = parsed["start_year"]
    
    # Determine year of study for this batch
    try:
        batch_year = int(batch_code)
        year_of_study = ay_start_year - batch_year + 1
    except:
        year_of_study = 1
    
    if year_of_study < 1 or year_of_study > num_years:
        return
    
    # Calculate term duration
    total_days = (ay_end - ay_start).days
    days_per_term = total_days // terms_per_year
    
    # Create initial term dates
    current_date = ay_start
    
    for term in range(1, terms_per_year + 1):
        start_date = get_next_monday(current_date)
        end_date = start_date + datetime.timedelta(days=days_per_term - 1)
        end_date = get_previous_friday(min(end_date, ay_end))
        
        sem_num = (year_of_study - 1) * terms_per_year + term
        
        conn.execute(
            sa_text("""
                INSERT INTO batch_term_dates 
                (degree_code, batch_code, ay_code, year_of_study, term_number, 
                 term_label, start_date, end_date)
                VALUES (:d, :b, :ay, :y, :t, :label, :start, :end)
            """),
            {
                "d": storage_key,
                "b": batch_code,
                "ay": ay_code,
                "y": year_of_study,
                "t": term,
                "label": f"Semester {sem_num}",
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        )
        
        current_date = end_date + datetime.timedelta(days=3)


def load_term_dates(conn, storage_key: str, batch_code: str, ay_code: str) -> Dict[int, List[Dict]]:
    """Load term dates organized by year of study."""
    # DEBUG: Always show what we're querying
    import streamlit as st
    st.write(f"🔍 LOAD: key={storage_key}, batch={batch_code}, ay={ay_code}")
    
    rows = conn.execute(
        sa_text("""
            SELECT year_of_study, term_number, term_label, start_date, end_date
            FROM batch_term_dates
            WHERE degree_code = :d AND batch_code = :b AND ay_code = :ay
            ORDER BY year_of_study, term_number
        """),
        {"d": storage_key, "b": batch_code, "ay": ay_code}
    ).fetchall()
    
    st.write(f"   → Found {len(rows)} rows")
    if rows:
        st.write(f"   → First row: Year {rows[0][0]}, Term {rows[0][1]}, {rows[0][3]} to {rows[0][4]}")
    
    data = {}
    for row in rows:
        year = row[0]
        if year not in data:
            data[year] = []
        data[year].append({
            "term_number": row[1],
            "label": row[2],
            "start_date": datetime.date.fromisoformat(row[3]),
            "end_date": datetime.date.fromisoformat(row[4])
        })
    
    return data


def copy_year_dates(
    conn,
    storage_key: str,
    from_batch: str,
    to_batch: str,
    ay_code: str,
    from_year: int,
    to_year: int,
    terms_per_year: int,
    ay_start: datetime.date,
    ay_end: datetime.date
) -> tuple[int, list]:
    """
    Copy term dates from one year/batch to another year/batch within the SAME AY.
    Returns (number of records copied, debug messages).
    """
    debug_msgs = []
    
    # STEP 1: Load source data (only from the specific source year)
    source_rows = conn.execute(
        sa_text("""
            SELECT term_number, term_label, start_date, end_date
            FROM batch_term_dates
            WHERE degree_code = :d AND batch_code = :b AND ay_code = :ay
              AND year_of_study = :y
            ORDER BY term_number
        """),
        {"d": storage_key, "b": from_batch, "ay": ay_code, "y": from_year}
    ).fetchall()

    if not source_rows:
        raise ValueError(f"No source data found for Year {from_year}, Batch {from_batch}")
    
    debug_msgs.append(f"Found {len(source_rows)} source records")

    # STEP 2: Delete existing target data to avoid conflicts
    result = conn.execute(
        sa_text("""
            DELETE FROM batch_term_dates
            WHERE degree_code = :d AND batch_code = :b AND ay_code = :ay
              AND year_of_study = :y
        """),
        {"d": storage_key, "b": to_batch, "ay": ay_code, "y": to_year}
    )
    
    debug_msgs.append(f"Deleted {result.rowcount} existing records")

    # STEP 3: Copy the dates EXACTLY as they are
    inserted_count = 0

    for row in source_rows:
        term_num = row[0]
        src_label = row[1]
        
        # Parse dates carefully - handle both string and date objects
        if isinstance(row[2], str):
            src_start = row[2]  # Keep as string for ISO format
        else:
            src_start = row[2].isoformat()
        
        if isinstance(row[3], str):
            src_end = row[3]  # Keep as string for ISO format
        else:
            src_end = row[3].isoformat()

        # Recalculate semester number based on TO year
        new_sem_num = (to_year - 1) * terms_per_year + term_num
        new_label = f"Semester {new_sem_num}"

        debug_msgs.append(f"Term {term_num}: {src_start} to {src_end}")

        # Insert new record with EXACT same dates
        conn.execute(
            sa_text("""
                INSERT INTO batch_term_dates 
                (degree_code, batch_code, ay_code, year_of_study, term_number, 
                 term_label, start_date, end_date, created_at, updated_at)
                VALUES (:d, :b, :ay, :y, :t, :label, :start, :end, 
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "d": storage_key,
                "b": to_batch,
                "ay": ay_code,
                "y": to_year,
                "t": term_num,
                "label": new_label,
                "start": src_start,
                "end": src_end,
            }
        )
        inserted_count += 1
    
    debug_msgs.append(f"Inserted {inserted_count} new records")
    
    return inserted_count, debug_msgs


def save_term_date(conn, storage_key: str, batch_code: str, ay_code: str,
                    year: int, term: int, label: str, start_date: str, end_date: str) -> None:
    """Save a single term's dates."""
    conn.execute(
        sa_text("""
            UPDATE batch_term_dates
            SET term_label = :label, start_date = :start, end_date = :end, 
                updated_at = CURRENT_TIMESTAMP
            WHERE degree_code = :d AND batch_code = :b AND ay_code = :ay
              AND year_of_study = :y AND term_number = :t
        """),
        {
            "d": storage_key,
            "b": batch_code,
            "ay": ay_code,
            "y": year,
            "t": term,
            "label": label,
            "start": start_date,
            "end": end_date
        }
    )


# ============================================================
# UI RENDERING
# ============================================================

def render_enhanced_term_dates(engine: Engine, roles: list, email: str) -> None:
    """Render the enhanced hierarchy-aware term dates editor."""
    st.subheader("📅 Enhanced Term Dates Editor (Hierarchy-Aware)")
    
    # Info box explaining the hierarchy
    with st.expander("ℹ️ How This Works", expanded=False):
        st.markdown("""
        This editor respects your degree's curriculum structure:
        
        - **Degree-level binding**: All programs/branches share the same term dates
        - **Program-level binding**: Each program has its own term dates
        - **Branch-level binding**: Each branch has its own term dates
        
        The system automatically determines what level to edit based on your degree's 
        **binding mode** and **curriculum governance** settings.
        """)
    
    if "admin" not in roles and "superadmin" not in roles:
        st.warning("You do not have permission to edit term dates.")
        return
    
    # ============================================================
    # STEP 1: DEGREE SELECTION
    # ============================================================
    
    with _safe_conn(engine) as conn:
        degrees = conn.execute(
            sa_text("""
                SELECT d.code, d.title
                FROM degrees d
                WHERE d.active = 1
                ORDER BY d.sort_order, d.code
            """)
        ).fetchall()
        
        ays = conn.execute(
            sa_text("""
                SELECT ay_code, start_date, end_date, status
                FROM academic_years
                ORDER BY start_date DESC
            """)
        ).fetchall()
    
    if not degrees:
        st.warning("No degrees found. Please configure degrees first.")
        return
    
    if not ays:
        st.warning("No academic years found. Please create academic years first.")
        return
    
    # Degree selection
    col1, col2 = st.columns(2)
    
    with col1:
        degree_options = {f"{d[1]} ({d[0]})": d for d in degrees}
        selected_degree_name = st.selectbox(
            "Select Degree",
            options=[""] + list(degree_options.keys()),
            key="enhanced_term_degree"
        )
    
    if not selected_degree_name:
        st.info("👈 Select a degree to get started")
        return
    
    degree_tuple = degree_options[selected_degree_name]
    degree_code = degree_tuple[0]
    
    # Load degree info
    with _safe_conn(engine) as conn:
        degree_info = get_degree_info(conn, degree_code)
    
    if not degree_info:
        st.error("Could not load degree information.")
        return
    
    # ============================================================
    # STEP 2: AY SELECTION
    # ============================================================
    
    with col2:
        ay_options = {f"{a[0]} ({a[3]})": a for a in ays}
        selected_ay_name = st.selectbox(
            "Select Academic Year",
            options=[""] + list(ay_options.keys()),
            key="enhanced_term_ay"
        )
    
    if not selected_ay_name:
        st.info("👈 Select an academic year")
        return
    
    ay = ay_options[selected_ay_name]
    ay_code = ay[0]
    ay_start = datetime.date.fromisoformat(ay[1])
    ay_end = datetime.date.fromisoformat(ay[2])
    
    st.info(f"📆 **AY Range:** {ay_start} to {ay_end}")
    
    st.divider()
    
    # ============================================================
    # STEP 3: HIERARCHY NAVIGATION (DYNAMIC BASED ON BINDING)
    # ============================================================
    
    binding_mode = degree_info["binding_mode"]
    cg_program = degree_info["cg_program"]
    cg_branch = degree_info["cg_branch"]
    
    # Display binding info
    st.markdown("### 🎯 Curriculum Structure")
    col_bind1, col_bind2, col_bind3 = st.columns(3)
    
    with col_bind1:
        st.metric("Binding Mode", binding_mode.upper())
    with col_bind2:
        st.metric("Programs", "Enabled" if cg_program else "Disabled")
    with col_bind3:
        st.metric("Branches", "Enabled" if cg_branch else "Disabled")
    
    # Determine what to show - BINDING MODE OVERRIDES cg flags
    # If binding is at program/branch level, we MUST show those selections
    if binding_mode == "degree":
        show_programs = False
        show_branches = False
    elif binding_mode == "program":
        show_programs = True
        show_branches = False
    elif binding_mode == "branch":
        show_programs = True  # Need program selection first
        show_branches = True  # Then branch selection
    else:
        # Fallback to cg flags if binding mode is unknown
        show_programs = cg_program
        show_branches = cg_branch
    
    # Storage key and structure info
    storage_key = degree_code
    selected_program = None
    selected_branch = None
    num_years = degree_info["years"]
    terms_per_year = degree_info["terms_per_year"]
    
    # ============================================================
    # PROGRAM SELECTION (if needed)
    # ============================================================
    
    if show_programs:
        st.markdown("### 📚 Program Selection")
        
        with _safe_conn(engine) as conn:
            programs = get_programs_for_degree(conn, degree_code)
        
        if not programs:
            st.warning(f"No programs found for {degree_code}. Please configure programs first.")
            return
        
        program_options = {f"{p['name']} ({p['code']})": p for p in programs}
        selected_program_name = st.selectbox(
            "Select Program",
            options=[""] + list(program_options.keys()),
            key="enhanced_term_program"
        )
        
        if not selected_program_name:
            st.info("👈 Select a program to continue")
            return
        
        selected_program = program_options[selected_program_name]
        storage_key = create_storage_key(degree_code, selected_program["code"])
        num_years = selected_program["years"]
        terms_per_year = selected_program["terms_per_year"]
        
        st.success(f"✅ Editing dates for: **{selected_program['name']}**")
    
    # ============================================================
    # BRANCH SELECTION (if needed)
    # ============================================================
    
    if show_branches and selected_program:
        st.markdown("### 🌿 Branch Selection")
        
        with _safe_conn(engine) as conn:
            branches = get_branches_for_program(conn, selected_program["id"])
        
        if not branches:
            st.warning(f"No branches found for {selected_program['name']}. Please configure branches first.")
            return
        
        branch_options = {f"{b['name']} ({b['code']})": b for b in branches}
        selected_branch_name = st.selectbox(
            "Select Branch",
            options=[""] + list(branch_options.keys()),
            key="enhanced_term_branch"
        )
        
        if not selected_branch_name:
            st.info("👈 Select a branch to continue")
            return
        
        selected_branch = branch_options[selected_branch_name]
        storage_key = create_storage_key(degree_code, selected_program["code"], selected_branch["code"])
        num_years = selected_branch["years"]
        terms_per_year = selected_branch["terms_per_year"]
        
        st.success(f"✅ Editing dates for: **{selected_branch['name']}**")
    
    st.divider()
    
    # ============================================================
    # STEP 4: DISPLAY STRUCTURE INFO
    # ============================================================
    
    st.markdown("### 📊 Structure Information")
    col_s1, col_s2, col_s3 = st.columns(3)
    
    with col_s1:
        st.metric("Years", num_years)
    with col_s2:
        st.metric("Terms/Year", terms_per_year)
    with col_s3:
        st.metric("Total Semesters", num_years * terms_per_year)
    
    st.info(f"🔑 **Storage Key:** `{storage_key}`")
    
    st.divider()
    
    # ============================================================
    # STEP 5: BATCH MAPPING
    # ============================================================
    
    st.markdown("### 📦 Year → Batch Mapping")
    
    batch_mapping = {}
    for year in range(1, num_years + 1):
        batch_code = get_batch_for_year(ay_code, year)
        batch_mapping[year] = batch_code
        
        with _safe_conn(engine) as conn:
            batch_exists = check_batch_exists(conn, degree_code, batch_code)
        
        col_year, col_batch, col_status = st.columns([1, 2, 2])
        with col_year:
            st.write(f"**Year {year}**")
        with col_batch:
            st.write(f"📦 Batch {batch_code}")
        with col_status:
            if batch_exists:
                st.success("✅ Batch exists", icon="✅")
            else:
                st.warning("⚠️ Batch not created", icon="⚠️")
    
    st.divider()
    
    # ============================================================
    # STEP 6: INITIALIZE IF NEEDED
    # ============================================================
    
    with engine.begin() as conn:
        existing_data = conn.execute(
            sa_text("""
                SELECT COUNT(*) FROM batch_term_dates
                WHERE degree_code = :d AND ay_code = :ay
            """),
            {"d": storage_key, "ay": ay_code}
        ).scalar()
        
        if existing_data == 0:
            st.info("📝 Initializing term dates for all years...")
            for year in range(1, num_years + 1):
                batch_code = batch_mapping[year]
                initialize_term_dates(
                    conn, storage_key, batch_code, ay_code,
                    num_years, terms_per_year, ay_start, ay_end
                )
            st.success("✅ Initialization complete!")
        else:
            st.info(f"📊 Found existing term data ({existing_data} records)")
    
    # ============================================================
    # STEP 7: LOAD AND DISPLAY TERM DATES
    # ============================================================
    
    all_term_data = {}
    table_data = []
    
    # DEBUG: Show what we're loading
    with st.expander("🔍 Debug Info", expanded=False):
        st.code(f"Storage Key: {storage_key}\nAY Code: {ay_code}\nBatch Mapping: {batch_mapping}")
    
    for year in range(1, num_years + 1):
        batch_code = batch_mapping[year]
        with _safe_conn(engine) as conn:
            term_data = load_term_dates(conn, storage_key, batch_code, ay_code)
            batch_exists = check_batch_exists(conn, degree_code, batch_code)
            batch_status = "✅ Created" if batch_exists else "⚠️ Not Created"
            
            # DEBUG: Show what we're querying for
            st.caption(f"Loading Year {year}: storage_key={storage_key}, batch={batch_code}, ay={ay_code}")
            
            if year in term_data:
                terms = term_data[year]
                all_term_data[year] = {
                    "batch": batch_code,
                    "terms": terms
                }
                
                # DEBUG: Show what was actually loaded
                if year == 2:
                    st.caption(f"Year 2 loaded {len(terms)} terms, first term: {terms[0]['start_date']} to {terms[0]['end_date']}")
                
                for term in terms:
                    duration = (term['end_date'] - term['start_date']).days + 1
                    start_day = term['start_date'].strftime("%A")
                    end_day = term['end_date'].strftime("%A")
                    
                    table_data.append({
                        "Year": year,
                        "Batch": batch_code,
                        "Batch Status": batch_status,
                        "Term": term['term_number'],
                        "Label": term['label'],
                        "Start Date": term['start_date'].strftime("%Y-%m-%d"),
                        "Start Day": start_day,
                        "End Date": term['end_date'].strftime("%Y-%m-%d"),
                        "End Day": end_day,
                        "Duration (Days)": duration,
                    })
    
    # ============================================================
    # STEP 8: TABLE VIEW
    # ============================================================
    
    st.markdown("### 📊 Term Dates Table")
    
    col_view, col_mode = st.columns([3, 1])
    with col_mode:
        edit_mode = st.toggle("🖊️ Edit Mode", value=False, key="enhanced_edit_mode")
    
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No term dates found.")
    
    st.divider()
    
    # ============================================================
    # STEP 9: EDIT MODE (if enabled)
    # ============================================================
    
    if edit_mode:
        st.markdown("### ✏️ Detailed Editor")
        
        # Use a version counter that increments ONLY on copy operations
        # This forces widget recreation after copy, but not after save
        copy_version = st.session_state.get('copy_version', 0)
        
        with st.form(key=f"enhanced_term_dates_form_{copy_version}"):
            for year in range(1, num_years + 1):
                if year not in all_term_data:
                    continue
                
                year_info = all_term_data[year]
                batch_code = year_info["batch"]
                terms = year_info["terms"]
                
                # Check for dates outside range
                dates_out_of_range = any(
                    t['start_date'] < ay_start or t['start_date'] > ay_end or
                    t['end_date'] < ay_start or t['end_date'] > ay_end
                    for t in terms
                )
                
                with st.container(border=True):
                    col_title, col_batch = st.columns([3, 2])
                    with col_title:
                        st.markdown(f"#### 📚 Year {year} of Study")
                    with col_batch:
                        # Check if batch exists
                        with _safe_conn(engine) as conn:
                            batch_exists = check_batch_exists(conn, degree_code, batch_code)
                        
                        if batch_exists:
                            st.info(f"📦 Batch {batch_code}")
                        else:
                            st.warning(f"⚠️ Batch {batch_code} (not created)")
                    
                    # Warning if dates are out of range
                    if dates_out_of_range:
                        st.warning(
                            "⚠️ Some term dates are outside the AY range. "
                            "They have been clamped in the date pickers below. "
                            "Please review and save."
                        )
                    
                    # Copy button and Save All button
                    col_copy, col_save_all = st.columns(2)
                    
                    with col_copy:
                        if year > 1:
                            prev_batch = batch_mapping[year - 1]
                            if st.form_submit_button(
                                f"📋 Copy from Year {year - 1}",
                                help=f"Copy all term dates from Year {year - 1} (Batch {prev_batch})",
                                use_container_width=True,
                                key=f"enh_copy_year_{storage_key}_{year}"
                            ):
                                try:
                                    # Create a NEW connection with a transaction
                                    with engine.begin() as trans_conn:
                                        count, debug_msgs = copy_year_dates(
                                            trans_conn, storage_key, prev_batch, batch_code, ay_code,
                                            year - 1, year, terms_per_year, ay_start, ay_end
                                        )
                                        
                                        # Verify the copy worked by reading back
                                        verify_rows = trans_conn.execute(
                                            sa_text("""
                                                SELECT COUNT(*) FROM batch_term_dates
                                                WHERE degree_code = :d AND batch_code = :b 
                                                  AND ay_code = :ay AND year_of_study = :y
                                            """),
                                            {"d": storage_key, "b": batch_code, "ay": ay_code, "y": year}
                                        ).scalar()
                                    
                                    # Store results in session state for display after rerun
                                    st.session_state[f'copy_result_{storage_key}_{year}'] = {
                                        'count': count,
                                        'verify': verify_rows,
                                        'debug': debug_msgs
                                    }
                                    # Increment copy version to force widget recreation
                                    st.session_state['copy_version'] = st.session_state.get('copy_version', 0) + 1
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Copy failed: {e}")
                                    st.code(traceback.format_exc())
                    
                    # Show copy result if it exists in session state
                    result_key = f'copy_result_{storage_key}_{year}'
                    if result_key in st.session_state:
                        result = st.session_state[result_key]
                        st.success(f"✅ Copied {result['count']} terms from Year {year-1}!")
                        st.info(f"Verification: {result['verify']} records now exist in database")
                        with st.expander("🔍 Copy Debug Info"):
                            for msg in result['debug']:
                                st.text(msg)
                        # Clear the message after showing
                        del st.session_state[result_key]
                    
                    year_changes = []
                    
                    for term in terms:
                        col_label, col_start, col_end, col_days, col_save = st.columns([2, 2, 2, 1, 1])
                        
                        term_start = term['start_date']
                        term_end = term['end_date']
                        
                        display_start = max(ay_start, min(term_start, ay_end))
                        display_end = max(ay_start, min(term_end, ay_end))
                        
                        if display_start >= display_end:
                            display_end = min(display_start + datetime.timedelta(days=1), ay_end)
                        
                        with col_label:
                            new_label = st.text_input(
                                "Label",
                                value=term['label'],
                                key=f"enh_label_{storage_key}_{year}_{term['term_number']}_{copy_version}",
                                label_visibility="collapsed"
                            )
                        
                        with col_start:
                            new_start = st.date_input(
                                "Start",
                                value=display_start,
                                key=f"enh_start_{storage_key}_{year}_{term['term_number']}_{copy_version}",
                                label_visibility="collapsed"
                            )
                        
                        with col_end:
                            new_end = st.date_input(
                                "End",
                                value=display_end,
                                key=f"enh_end_{storage_key}_{year}_{term['term_number']}_{copy_version}",
                                label_visibility="collapsed"
                            )
                        
                        with col_days:
                            duration = (new_end - new_start).days + 1
                            st.metric("Days", duration, label_visibility="collapsed")
                        
                        with col_save:
                            has_changes = (
                                new_label != term['label'] or 
                                new_start != term['start_date'] or 
                                new_end != term['end_date']
                            )
                            
                            if has_changes:
                                year_changes.append({
                                    'term_number': term['term_number'],
                                    'label': new_label,
                                    'start': new_start,
                                    'end': new_end
                                })
                            
                            if st.form_submit_button(
                                "💾", 
                                key=f"enh_save_{storage_key}_{year}_{term['term_number']}",
                                help="Save this term",
                                use_container_width=True
                            ):
                                if has_changes:
                                    with engine.begin() as conn:
                                        save_term_date(
                                            conn, storage_key, batch_code, ay_code,
                                            year, term['term_number'],
                                            new_label, new_start.isoformat(), new_end.isoformat()
                                        )
                                    st.success(f"✅ Saved Term {term['term_number']} for Year {year}!")
                    
                    # Save All button
                    if year_changes:
                        if st.form_submit_button(
                            f"💾 Save All ({len(year_changes)} changes)",
                            key=f"enh_save_all_{storage_key}_{year}_{copy_version}",
                            type="primary",
                            use_container_width=True
                        ):
                            with engine.begin() as conn:
                                for change in year_changes:
                                    save_term_date(
                                        conn, storage_key, batch_code, ay_code,
                                        year, change['term_number'],
                                        change['label'], 
                                        change['start'].isoformat(), 
                                        change['end'].isoformat()
                                    )
                            st.success(f"✅ Saved {len(year_changes)} term(s) for Year {year}!")
                            st.rerun()
            
            # Global refresh button
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.form_submit_button("🔄 Refresh Data", use_container_width=True):
                    st.info("Please refresh the page manually to see latest changes")
