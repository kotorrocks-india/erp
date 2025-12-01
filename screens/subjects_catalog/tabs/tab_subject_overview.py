"""
Subject Overview Tab - Read-only view combining subject catalog and syllabus library data
UPDATED: Added proper Year and Term filters based on degree's semester structure
All original functionality preserved.
"""

import streamlit as st
import pandas as pd
import json
from typing import Dict, Any, List, Optional, Tuple
# Use relative imports
from ..helpers import exec_query, rows_to_dicts
from ..db_helpers import (
    fetch_degrees, fetch_programs, fetch_branches,
    fetch_curriculum_groups, fetch_subjects
)
from ..templates_crud import list_templates_for_subject, get_template_points


# =====================================================================
# HELPER FUNCTIONS FOR SEMESTER STRUCTURE
# =====================================================================

def fetch_degree_semester_structure(engine, degree_code: str) -> Optional[Tuple[int, int]]:
    """
    Fetch the years and terms_per_year for a degree.
    Returns (years, terms_per_year) or None if not configured.
    """
    with engine.begin() as conn:
        row = exec_query(conn, """
            SELECT years, terms_per_year 
            FROM degree_semester_struct 
            WHERE degree_code = :dc AND active = 1
            LIMIT 1
        """, {"dc": degree_code}).fetchone()
        
        if row:
            return (row[0], row[1])
        
        return None


def fetch_semesters_for_filters(engine, degree_code: str, 
                                program_code: Optional[str] = None,
                                branch_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch all semesters for a degree (optionally filtered by program/branch).
    Returns list of semester dicts with year_index, term_index, semester_number, label.
    """
    with engine.begin() as conn:
        query = """
            SELECT DISTINCT year_index, term_index, semester_number, label
            FROM semesters
            WHERE degree_code = :dc
        """
        params = {"dc": degree_code}
        
        if program_code:
            query += " AND (program_id IS NULL OR program_id = (SELECT id FROM programs WHERE program_code = :pc LIMIT 1))"
            params["pc"] = program_code
        
        if branch_code:
            query += " AND (branch_id IS NULL OR branch_id = (SELECT id FROM branches WHERE branch_code = :bc LIMIT 1))"
            params["bc"] = branch_code
        
        query += " ORDER BY semester_number"
        
        rows = exec_query(conn, query, params).fetchall()
        return rows_to_dicts(rows)


# =====================================================================
# DISPLAY FUNCTIONS
# =====================================================================

def _display_subject_details(subject: Dict[str, Any]):
    """Display subject catalog details in a structured format."""
    st.markdown("### 📚 Subject Information")
    
    # Basic Information
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Basic Details")
        st.markdown(f"**Subject Code:** {subject.get('subject_code', 'N/A')}")
        st.markdown(f"**Subject Name:** {subject.get('subject_name', 'N/A')}")
        st.markdown(f"**Type:** {subject.get('subject_type', 'N/A')}")
        st.markdown(f"**Status:** {subject.get('status', 'N/A')}")
        st.markdown(f"**Active:** {'Yes' if subject.get('active') else 'No'}")
        
    with col2:
        st.markdown("#### Academic Scope")
        st.markdown(f"**Degree:** {subject.get('degree_code', 'N/A')}")
        st.markdown(f"**Program:** {subject.get('program_code') or 'All'}")
        st.markdown(f"**Branch:** {subject.get('branch_code') or 'All'}")
        st.markdown(f"**Curriculum Group:** {subject.get('curriculum_group_code') or 'N/A'}")
        
        semester_id = subject.get('semester_id')
        year_index = subject.get('year_index')
        term_index = subject.get('term_index')
        
        if semester_id:
            sem_display = f"Semester {semester_id}"
            if year_index and term_index:
                sem_display += f" (Year {year_index}, Term {term_index})"
            st.markdown(f"**Semester:** {sem_display}")
    
    # Credits and Workload
    st.markdown("---")
    st.markdown("#### Credits & Workload")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Credits", subject.get('credits_total', 0))
        st.caption(f"Student: {subject.get('student_credits', subject.get('credits_total', 0))}")
        st.caption(f"Teaching: {subject.get('teaching_credits', subject.get('credits_total', 0))}")
    
    with col2:
        st.markdown("**Contact Hours**")
        L = subject.get('L', 0) or 0
        T = subject.get('T', 0) or 0
        P = subject.get('P', 0) or 0
        S = subject.get('S', 0) or 0
        
        st.caption(f"L (Lecture): {L}")
        st.caption(f"T (Tutorial): {T}")
        st.caption(f"P (Practical): {P}")
        st.caption(f"S (Studio): {S}")
    
    with col3:
        st.markdown("**Other Components**")
        workload_json = subject.get('workload_breakup_json')
        if workload_json:
            try:
                components = json.loads(workload_json)
                if isinstance(components, list):
                    other_components = [c for c in components if c.get('code') not in ['L', 'T', 'P', 'S']]
                    if other_components:
                        for comp in other_components:
                            st.caption(f"{comp.get('code')}: {comp.get('hours', 0)} hrs")
                    else:
                        st.caption("None")
                else:
                    st.caption("None")
            except (json.JSONDecodeError, TypeError):
                st.caption("None")
        else:
            st.caption("None")
    
    # Assessment Configuration
    st.markdown("---")
    st.markdown("#### Assessment & Marks")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Maximum Marks**")
        st.caption(f"Internal: {subject.get('internal_marks_max', 0)}")
        st.caption(f"External (Exam): {subject.get('exam_marks_max', 0)}")
        st.caption(f"Jury/Viva: {subject.get('jury_viva_marks_max', 0)}")
    
    with col2:
        st.markdown("**Minimum Passing %**")
        st.caption(f"Internal: {subject.get('min_internal_percent', 0)}%")
        st.caption(f"External: {subject.get('min_external_percent', 0)}%")
        st.caption(f"Overall: {subject.get('min_overall_percent', 0)}%")
    
    with col3:
        st.markdown("**Direct Attainment**")
        st.caption(f"Source Mode: {subject.get('direct_source_mode', 'overall')}")
        st.caption(f"Internal Weight: {subject.get('direct_internal_weight_percent', 0)}%")
        st.caption(f"External Weight: {subject.get('direct_external_weight_percent', 0)}%")
    
    # Attainment Targets
    st.markdown("---")
    st.markdown("#### Attainment Targets")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Direct Attainment**")
        st.caption(f"Target: {subject.get('direct_target_students_percent', 0)}% of students")
        st.caption(f"Weight in Overall: {subject.get('overall_direct_weight_percent', 0)}%")
    
    with col2:
        st.markdown("**Indirect Attainment**")
        st.caption(f"Target: {subject.get('indirect_target_students_percent', 0)}% of students")
        st.caption(f"Min Response Rate: {subject.get('indirect_min_response_rate_percent', 0)}%")
        st.caption(f"Weight in Overall: {subject.get('overall_indirect_weight_percent', 0)}%")
    
    # Description
    if subject.get('description'):
        st.markdown("---")
        st.markdown("#### Description")
        st.markdown(subject['description'])


def _display_syllabus_templates(conn, subject_code: str, degree_code: str):
    """Display syllabus templates for the subject."""
    st.markdown("### 📋 Syllabus Templates")
    
    # Fetch templates
    templates = list_templates_for_subject(conn, subject_code, include_deprecated=True)
    
    if not templates:
        st.info(f"No syllabus templates found for {subject_code}")
        return
    
    # Filter by degree if specified
    if degree_code:
        templates = [
            t for t in templates 
            if not t.get('degree_code') or t.get('degree_code') == degree_code
        ]
    
    if not templates:
        st.info(f"No syllabus templates found for {subject_code} in {degree_code}")
        return
    
    # Display each template
    for tmpl in templates:
        status_emoji = "✅" if tmpl['is_current'] else "📦"
        deprecated_badge = " [DEPRECATED]" if tmpl.get('deprecated_from_ay') else ""
        
        with st.expander(
            f"{status_emoji} {tmpl['name']} ({tmpl['version']}){deprecated_badge}",
            expanded=tmpl['is_current']
        ):
            # Template metadata
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Version #", tmpl['version_number'])
            with col2:
                st.metric("Points", tmpl['point_count'])
            with col3:
                st.metric("Used by Offerings", tmpl['usage_count'])
            
            st.caption(f"**Code:** {tmpl['code']}")
            
            if tmpl.get('description'):
                st.markdown(f"**Description:** {tmpl['description']}")
            
            if tmpl.get('effective_from_ay'):
                st.markdown(f"**Effective from:** {tmpl['effective_from_ay']}")
            
            if tmpl.get('deprecated_from_ay'):
                st.warning(f"Deprecated from: {tmpl['deprecated_from_ay']}")
            
            # Display scope
            scope_parts = []
            if tmpl.get('degree_code'):
                scope_parts.append(f"Degree: {tmpl['degree_code']}")
            if tmpl.get('program_code'):
                scope_parts.append(f"Program: {tmpl['program_code']}")
            if tmpl.get('branch_code'):
                scope_parts.append(f"Branch: {tmpl['branch_code']}")
            
            if scope_parts:
                st.caption("**Scope:** " + " | ".join(scope_parts))
            
            # Display points
            points = get_template_points(conn, tmpl['id'])
            
            if points:
                st.markdown("**Syllabus Points:**")
                
                # Create a clean dataframe for display
                points_display = []
                for p in points:
                    points_display.append({
                        "Seq": p['sequence'],
                        "Title": p['title'],
                        "Hours": p.get('hours_weight', 0) or 0,
                        "Type": p.get('point_type', 'unit'),
                    })
                
                df = pd.DataFrame(points_display)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Show detailed view in expandable section
                with st.expander("View Full Details"):
                    for p in points:
                        st.markdown(f"**{p['sequence']}. {p['title']}**")
                        if p.get('description'):
                            st.caption(p['description'])
                        if p.get('tags'):
                            st.caption(f"🏷️ Tags: {p['tags']}")
                        if p.get('resources'):
                            st.caption(f"📚 Resources: {p['resources']}")
                        st.markdown("---")


# =====================================================================
# MAIN RENDER FUNCTION
# =====================================================================

def render(engine, actor: str, CAN_EDIT: bool):
    """Render the Subject Overview tab."""
    st.subheader("📖 Subject Overview")
    st.caption("Read-only comprehensive view of subjects with their syllabus templates")
    
    # --- FILTERS ---
    st.markdown("#### Select Subject to View")
    
    degrees = fetch_degrees(engine)
    degree_options = [d["code"] for d in degrees]
    
    if not degrees:
        st.warning("No degrees found.")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        degree_code = st.selectbox(
            "Degree*",
            options=degree_options,
            key="overview_degree",
        )
    
    with col2:
        programs = fetch_programs(engine, degree_code)
        program_options = [""] + [p["program_code"] for p in programs]
        program_code = st.selectbox(
            "Program (optional)",
            options=program_options,
            key="overview_program",
        )
    
    with col3:
        branches = fetch_branches(engine, degree_code, program_code or None)
        branch_options = [""] + [b["branch_code"] for b in branches]
        branch_code = st.selectbox(
            "Branch (optional)",
            options=branch_options,
            key="overview_branch",
        )
    
    with col4:
        cgs = fetch_curriculum_groups(engine, degree_code, program_code or None, branch_code or None)
        cg_options = [""] + [cg["group_code"] for cg in cgs]
        cg_code = st.selectbox(
            "Curriculum Group (optional)",
            options=cg_options,
            key="overview_cg",
        )
    
    # --- NEW: Year and Term filters ---
    semester_struct = fetch_degree_semester_structure(engine, degree_code)
    semesters = fetch_semesters_for_filters(engine, degree_code, program_code or None, branch_code or None)
    
    if semester_struct:
        years, terms_per_year = semester_struct
        
        col_year, col_term = st.columns(2)
        
        with col_year:
            year_options = ["All"] + list(range(1, years + 1))
            selected_year = st.selectbox(
                "Year",
                options=year_options,
                key="overview_year_filter",
                help=f"This degree has {years} year(s)"
            )
        
        with col_term:
            term_options = ["All"] + list(range(1, terms_per_year + 1))
            selected_term = st.selectbox(
                "Term/Semester",
                options=term_options,
                key="overview_term_filter",
                help=f"This degree has {terms_per_year} term(s) per year"
            )
    else:
        selected_year = "All"
        selected_term = "All"
    
    # Fetch subjects based on filters
    with engine.begin() as conn:
        query = """
            SELECT sc.*, s.year_index, s.term_index
            FROM subjects_catalog sc
            LEFT JOIN semesters s ON s.id = sc.semester_id
            WHERE sc.degree_code = :d AND sc.active = 1
        """
        params = {"d": degree_code}
        
        if program_code:
            query += " AND (sc.program_code = :p OR sc.program_code IS NULL)"
            params["p"] = program_code
        
        if branch_code:
            query += " AND (sc.branch_code = :b OR sc.branch_code IS NULL)"
            params["b"] = branch_code
        
        if cg_code:
            query += " AND sc.curriculum_group_code = :cg"
            params["cg"] = cg_code
        
        if selected_year != "All":
            query += " AND s.year_index = :year"
            params["year"] = selected_year
        
        if selected_term != "All":
            query += " AND s.term_index = :term"
            params["term"] = selected_term
        
        query += " ORDER BY sc.sort_order, sc.subject_code"
        
        rows = exec_query(conn, query, params).fetchall()
        subjects = rows_to_dicts(rows)
    
    if not subjects:
        st.info("No subjects found for the selected filters.")
        return
    
    # Subject selection
    st.markdown("---")
    
    subject_options = {}
    for s in subjects:
        label = f"{s['subject_code']} - {s['subject_name']}"
        if s.get('year_index') and s.get('term_index'):
            label += f" (Year {s['year_index']}, Term {s['term_index']})"
        subject_options[label] = s
    
    selected_subject_label = st.selectbox(
        "Select Subject",
        options=list(subject_options.keys()),
        key="overview_subject_select",
    )
    
    if not selected_subject_label:
        return
    
    selected_subject = subject_options[selected_subject_label]
    
    # Display subject details
    st.markdown("---")
    _display_subject_details(selected_subject)
    
    # Display syllabus templates
    st.markdown("---")
    with engine.begin() as conn:
        _display_syllabus_templates(
            conn,
            selected_subject['subject_code'],
            selected_subject['degree_code']
        )
