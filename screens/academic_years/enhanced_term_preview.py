# screens/academic_years/enhanced_term_preview.py
"""
Enhanced Term Preview Module - Hierarchy-Aware
Displays term dates respecting degree/program/branch binding.
Works with the composite storage keys from enhanced_term_dates.py
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text as sa_text
from datetime import datetime
import re  # <--- ADDED for robust parsing
from typing import Optional, Dict, List, Tuple

def _safe_conn(engine):
    """Get a database connection."""
    try:
        return engine.connect()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.stop()


def parse_storage_key(key: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Parse a storage key back into components."""
    parts = key.split("::")
    degree = parts[0]
    program = parts[1] if len(parts) > 1 else None
    branch = parts[2] if len(parts) > 2 else None
    return degree, program, branch


def create_storage_key(degree_code: str, program_code: Optional[str] = None, 
                       branch_code: Optional[str] = None) -> str:
    """Create a composite key for storing hierarchical data."""
    parts = [degree_code]
    if program_code:
        parts.append(program_code)
    if branch_code:
        parts.append(branch_code)
    return "::".join(parts)


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
    """Get programs for a degree with their structure."""
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
    """Get branches for a program with their structure."""
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


def get_calculated_batch(ay_code: str, year_of_study: int) -> str:
    """
    Calculate the expected batch for a specific Year of Study in an AY.
    ROBUST: Uses regex to find the year, handling formats like 'AY 2024-25' or '2024-2025'.
    """
    try:
        # Extract first 4-digit number found
        match = re.search(r'\d{4}', ay_code)
        if match:
            start_year = int(match.group(0))
            return str(start_year - (year_of_study - 1))
        
        # Fallback to simple split if regex fails
        start_year = int(ay_code.split('-')[0])
        return str(start_year - (year_of_study - 1))
    except:
        return "UNKNOWN"


def check_batch_exists(conn, degree_code: str, batch_code: str) -> bool:
    """Check if a batch exists in the degree_batches table."""
    try:
        result = conn.execute(
            sa_text("SELECT 1 FROM degree_batches WHERE degree_code = :d AND batch_code = :b LIMIT 1"),
            {"d": degree_code, "b": batch_code}
        ).fetchone()
        return result is not None
    except Exception:
        return False


def render_enhanced_term_preview(engine, roles, email):
    """Render the enhanced hierarchy-aware term preview."""
    st.subheader("👀 Enhanced Term Preview (Hierarchy-Aware)")
    
    # Info box
    with st.expander("ℹ️ How This Works", expanded=False):
        st.markdown("""
        This preview respects your curriculum hierarchy:
        
        - **Degree-level**: Shows unified schedule for all programs/branches
        - **Program-level**: Shows schedule per program (each can have different structure)
        - **Branch-level**: Shows schedule per branch (each can have different structure)
        
        The preview automatically adapts based on binding mode and available data.
        """)
    
    # ============================================================
    # STEP 1: DEGREE SELECTION
    # ============================================================
    
    with engine.begin() as conn:
        degrees = conn.execute(sa_text("""
            SELECT code, title
            FROM degrees d 
            WHERE d.active = 1 
            ORDER BY d.sort_order
        """)).fetchall()
        
        ays = conn.execute(sa_text("""
            SELECT ay_code FROM academic_years ORDER BY start_date DESC
        """)).fetchall()

    if not degrees or not ays:
        st.info("Configuration missing - need active degrees and academic years.")
        return

    # Selection UI
    c1, c2 = st.columns(2)
    
    with c1:
        d_map = {f"{d.title} ({d.code})": d for d in degrees}
        sel_d = st.selectbox("Degree", options=list(d_map.keys()), key="prev_enh_d")
        degree = d_map[sel_d]
        degree_code = degree.code

    with c2:
        ay_opts = [a.ay_code for a in ays]
        ay_code = st.selectbox("Academic Year", options=ay_opts, key="prev_enh_ay")
    
    # Load degree info
    with _safe_conn(engine) as conn:
        degree_info = get_degree_info(conn, degree_code)
    
    if not degree_info:
        st.error("Could not load degree information.")
        return
    
    binding_mode = degree_info["binding_mode"]
    cg_program = degree_info["cg_program"]
    cg_branch = degree_info["cg_branch"]
    
    st.divider()
    
    # ============================================================
    # STEP 2: DISPLAY BINDING INFO
    # ============================================================
    
    st.markdown("### 🎯 Curriculum Structure")
    col_bind1, col_bind2, col_bind3 = st.columns(3)
    
    with col_bind1:
        st.metric("Binding Mode", binding_mode.upper())
    with col_bind2:
        st.metric("Programs", "Enabled" if cg_program else "Disabled")
    with col_bind3:
        st.metric("Branches", "Enabled" if cg_branch else "Disabled")
    
    st.divider()
    
    # ============================================================
    # STEP 3: DETERMINE WHAT TO PREVIEW
    # ============================================================
    
    # Determine what to preview - BINDING MODE OVERRIDES cg flags
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
    
    # ============================================================
    # CASE 1: DEGREE-LEVEL BINDING (Simple Preview)
    # ============================================================
    
    if not show_programs:
        st.markdown("### 📊 Degree-Level Schedule")
        st.info(f"All programs/branches share the same term schedule for **{degree_code}**")
        
        storage_key = degree_code
        num_years = degree_info["years"]
        terms_per_year = degree_info["terms_per_year"]
        
        table_data = generate_schedule_table(
            engine, storage_key, ay_code, degree_code, 
            num_years, terms_per_year, None, None
        )
        
        if table_data:
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("No term dates found. Please configure in the Term Dates Editor.")
        
        return
    
    # ============================================================
    # CASE 2: PROGRAM-LEVEL BINDING
    # ============================================================
    
    if show_programs and not show_branches:
        st.markdown("### 📚 Program-Level Schedules")
        
        with _safe_conn(engine) as conn:
            programs = get_programs_for_degree(conn, degree_code)
        
        if not programs:
            st.warning("No programs configured for this degree.")
            return
        
        # Preview mode selector
        preview_mode = st.radio(
            "Preview Mode",
            options=["All Programs", "Single Program"],
            horizontal=True,
            key="prev_enh_prog_mode"
        )
        
        if preview_mode == "Single Program":
            # Single program selection
            program_options = {f"{p['name']} ({p['code']})": p for p in programs}
            selected_program_name = st.selectbox(
                "Select Program",
                options=list(program_options.keys()),
                key="prev_enh_single_prog"
            )
            selected_program = program_options[selected_program_name]
            
            storage_key = create_storage_key(degree_code, selected_program["code"])
            table_data = generate_schedule_table(
                engine, storage_key, ay_code, degree_code,
                selected_program["years"], selected_program["terms_per_year"],
                selected_program["code"], None
            )
            
            if table_data:
                st.markdown(f"**Schedule for: {selected_program['name']}**")
                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("No term dates found for this program.")
        
        else:
            # Show all programs
            for program in programs:
                with st.expander(f"📚 {program['name']} ({program['code']})", expanded=False):
                    st.info(f"Structure: **{program['years']} Years, {program['terms_per_year']} Terms/Year**")
                    
                    storage_key = create_storage_key(degree_code, program["code"])
                    table_data = generate_schedule_table(
                        engine, storage_key, ay_code, degree_code,
                        program["years"], program["terms_per_year"],
                        program["code"], None
                    )
                    
                    if table_data:
                        df = pd.DataFrame(table_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.warning("No term dates configured.")
        
        return
    
    # ============================================================
    # CASE 3: BRANCH-LEVEL BINDING
    # ============================================================
    
    if show_branches:
        st.markdown("### 🌿 Branch-Level Schedules")
        
        with _safe_conn(engine) as conn:
            programs = get_programs_for_degree(conn, degree_code)
        
        if not programs:
            st.warning("No programs configured for this degree.")
            return
        
        # Preview mode selector
        preview_mode = st.radio(
            "Preview Mode",
            options=["All Programs & Branches", "Single Branch"],
            horizontal=True,
            key="prev_enh_branch_mode"
        )
        
        if preview_mode == "Single Branch":
            # Program selection
            program_options = {f"{p['name']} ({p['code']})": p for p in programs}
            selected_program_name = st.selectbox(
                "Select Program",
                options=list(program_options.keys()),
                key="prev_enh_single_prog_b"
            )
            selected_program = program_options[selected_program_name]
            
            # Branch selection
            with _safe_conn(engine) as conn:
                branches = get_branches_for_program(conn, selected_program["id"])
            
            if not branches:
                st.warning("No branches configured for this program.")
                return
            
            branch_options = {f"{b['name']} ({b['code']})": b for b in branches}
            selected_branch_name = st.selectbox(
                "Select Branch",
                options=list(branch_options.keys()),
                key="prev_enh_single_branch"
            )
            selected_branch = branch_options[selected_branch_name]
            
            storage_key = create_storage_key(degree_code, selected_program["code"], selected_branch["code"])
            table_data = generate_schedule_table(
                engine, storage_key, ay_code, degree_code,
                selected_branch["years"], selected_branch["terms_per_year"],
                selected_program["code"], selected_branch["code"]
            )
            
            if table_data:
                st.markdown(f"**Schedule for: {selected_program['name']} → {selected_branch['name']}**")
                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("No term dates found for this branch.")
        
        else:
            # Show all programs and their branches
            for program in programs:
                with st.expander(f"📚 {program['name']} ({program['code']})", expanded=False):
                    with _safe_conn(engine) as conn:
                        branches = get_branches_for_program(conn, program["id"])
                    
                    if not branches:
                        st.info("No branches configured for this program.")
                        continue
                    
                    for branch in branches:
                        st.markdown(f"#### 🌿 {branch['name']} ({branch['code']})")
                        st.info(f"Structure: **{branch['years']} Years, {branch['terms_per_year']} Terms/Year**")
                        
                        storage_key = create_storage_key(degree_code, program["code"], branch["code"])
                        table_data = generate_schedule_table(
                            engine, storage_key, ay_code, degree_code,
                            branch["years"], branch["terms_per_year"],
                            program["code"], branch["code"]
                        )
                        
                        if table_data:
                            df = pd.DataFrame(table_data)
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.warning("No term dates configured.")
                        
                        st.markdown("---")


def generate_schedule_table(
    engine,
    storage_key: str,
    ay_code: str,
    degree_code: str,
    num_years: int,
    terms_per_year: int,
    program_code: Optional[str],
    branch_code: Optional[str]
) -> List[Dict]:
    """Generate the schedule table for a specific hierarchy level."""
    table_data = []
    
    with engine.begin() as conn:
        # Fetch ALL rows for this storage key + AY
        db_rows = conn.execute(sa_text("""
            SELECT year_of_study, batch_code, term_number, term_label, start_date, end_date
            FROM batch_term_dates
            WHERE degree_code = :d AND ay_code = :ay
        """), {"d": storage_key, "ay": ay_code}).fetchall()
        
        # Index data by (Year, Term) only - we trust the DB record for the batch code
        # This prevents mismatches if calculated batch doesn't match stored batch exactly
        db_data = {}
        for row in db_rows:
            key = (row.year_of_study, row.term_number)
            db_data[key] = row
        
        # Generate structure
        for year in range(1, num_years + 1):
            # Calculate batch primarily for checking "Status", 
            # but rely on DB record for actual display if available
            calculated_batch = get_calculated_batch(ay_code, year)
            batch_exists = check_batch_exists(conn, degree_code, calculated_batch)
            batch_status_str = "✅ Created" if batch_exists else "⚠️ Not Created"
            
            for term in range(1, terms_per_year + 1):
                sem_num = (year - 1) * terms_per_year + term
                
                # Loose lookup by Year+Term (ignores batch code in key)
                record = db_data.get((year, term))
                
                label = f"Semester {sem_num}"
                s_date_display = None
                e_date_display = None
                s_day = "-"
                e_day = "-"
                duration = "-"
                
                # Use stored batch if available, otherwise calculated
                display_batch = str(record.batch_code) if record else calculated_batch
                
                if record:
                    label = record.term_label
                    try:
                        s_ts = pd.to_datetime(record.start_date)
                        e_ts = pd.to_datetime(record.end_date)
                        
                        if not pd.isna(s_ts) and not pd.isna(e_ts):
                            s_date_display = s_ts.date()
                            e_date_display = e_ts.date()
                            s_day = s_ts.day_name()
                            e_day = e_ts.day_name()
                            duration = f"{(e_ts - s_ts).days + 1} Days"
                    except Exception:
                        pass
                
                # Build row
                row_data = {
                    "Year": year,
                    "Batch": display_batch,
                    "Batch Status": batch_status_str,
                    "Term": term,
                    "Label": label,
                    "Start Date": s_date_display,
                    "Start Day": s_day,
                    "End Date": e_date_display,
                    "End Day": e_day,
                    "Duration": duration
                }
                
                # Add program/branch info if applicable
                if program_code:
                    row_data["Program"] = program_code
                if branch_code:
                    row_data["Branch"] = branch_code
                
                table_data.append(row_data)
    
    return table_data
