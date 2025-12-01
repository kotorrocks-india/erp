"""
Syllabus Library Tab - Create and manage syllabus templates
UPDATED: Added proper Year and Term filters based on degree's semester structure
All original functionality preserved.
""" 

import streamlit as st
import pandas as pd
from typing import Optional, Tuple, List, Dict, Any
# Use relative imports
from ..helpers import exec_query, rows_to_dicts
from ..db_helpers import (
    fetch_degrees, fetch_programs, fetch_branches,
    fetch_curriculum_groups
)
from ..templates_crud import (
    create_syllabus_template, list_templates_for_subject,
    get_template_points, clone_template
)
from core.forms import success
from sqlalchemy import text as sa_text


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
# MAIN RENDER FUNCTION
# =====================================================================

def render(engine, actor: str, CAN_EDIT: bool):
    """Render the Syllabus Library tab."""
    st.subheader("📋 Syllabus Library")
    st.caption("Create and manage reusable syllabus templates")

    # --- FILTERS ---
    st.markdown("#### Filter by Scope")
    
    degrees = fetch_degrees(engine)
    degree_options = [""] + [d["code"] for d in degrees]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        filter_degree = st.selectbox(
            "Degree (optional)",
            options=degree_options,
            key="syllabus_filter_degree",
            help="Filter templates by degree"
        )
    
    with col2:
        if filter_degree:
            programs = fetch_programs(engine, filter_degree)
            program_options = [""] + [p["program_code"] for p in programs]
        else:
            program_options = [""]
        
        filter_program = st.selectbox(
            "Program (optional)",
            options=program_options,
            key="syllabus_filter_program",
            help="Filter templates by program"
        )
    
    with col3:
        if filter_degree:
            branches = fetch_branches(engine, filter_degree, filter_program or None)
            branch_options = [""] + [b["branch_code"] for b in branches]
        else:
            branch_options = [""]
        
        filter_branch = st.selectbox(
            "Branch (optional)",
            options=branch_options,
            key="syllabus_filter_branch",
            help="Filter templates by branch"
        )
    
    with col4:
        if filter_degree:
            cgs = fetch_curriculum_groups(engine, filter_degree, filter_program or None, filter_branch or None)
            cg_options = [""] + [cg["group_code"] for cg in cgs]
        else:
            cg_options = [""]
        
        filter_cg = st.selectbox(
            "Curriculum Group (optional)",
            options=cg_options,
            key="syllabus_filter_cg",
            help="Filter templates by curriculum group"
        )

    # --- NEW: Year and Term filters ---
    if filter_degree:
        semester_struct = fetch_degree_semester_structure(engine, filter_degree)
        semesters = fetch_semesters_for_filters(engine, filter_degree, filter_program or None, filter_branch or None)
        
        if semester_struct:
            years, terms_per_year = semester_struct
            
            col_year, col_term = st.columns(2)
            
            with col_year:
                year_options = ["All"] + list(range(1, years + 1))
                selected_year = st.selectbox(
                    "Year",
                    options=year_options,
                    key="syllabus_year_filter",
                    help=f"This degree has {years} year(s)"
                )
            
            with col_term:
                term_options = ["All"] + list(range(1, terms_per_year + 1))
                selected_term = st.selectbox(
                    "Term/Semester",
                    options=term_options,
                    key="syllabus_term_filter",
                    help=f"This degree has {terms_per_year} term(s) per year"
                )
        else:
            selected_year = "All"
            selected_term = "All"
    else:
        selected_year = "All"
        selected_term = "All"

    # Fetch subjects based on filters
    with engine.begin() as conn:
        query = """
            SELECT DISTINCT sc.subject_code, sc.subject_name, sc.degree_code,
                   s.year_index, s.term_index
            FROM subjects_catalog sc
            LEFT JOIN semesters s ON s.id = sc.semester_id
            WHERE sc.active = 1
        """
        params = {}
        
        if filter_degree:
            query += " AND sc.degree_code = :deg"
            params["deg"] = filter_degree
        
        if filter_program:
            query += " AND (sc.program_code = :prog OR sc.program_code IS NULL)"
            params["prog"] = filter_program
        
        if filter_branch:
            query += " AND (sc.branch_code = :branch OR sc.branch_code IS NULL)"
            params["branch"] = filter_branch
        
        if filter_cg:
            query += " AND sc.curriculum_group_code = :cg"
            params["cg"] = filter_cg
        
        if selected_year != "All":
            query += " AND s.year_index = :year"
            params["year"] = selected_year
        
        if selected_term != "All":
            query += " AND s.term_index = :term"
            params["term"] = selected_term
        
        query += " ORDER BY sc.subject_code"
        
        subjects = exec_query(conn, query, params).fetchall()

    if not subjects:
        st.warning("No subjects found for the selected filters. Adjust filters or create subjects first.")
        return

    subjects = rows_to_dicts(subjects)

    # Subject selection
    st.markdown("---")
    
    # Create subject options with year/term info
    subject_display_options = {}
    for s in subjects:
        label = f"{s['subject_code']} - {s['subject_name']} ({s['degree_code']})"
        if s.get('year_index') and s.get('term_index'):
            label += f" [Year {s['year_index']}, Term {s['term_index']}]"
        subject_display_options[label] = s['subject_code']
    
    selected_subject_display = st.selectbox(
        "Select Subject",
        options=list(subject_display_options.keys()),
        key="tmpl_subject_display",
    )
    
    subject_code = subject_display_options[selected_subject_display]

    # Get the selected subject's degree for context
    selected_subject_degree = next((s["degree_code"] for s in subjects if s["subject_code"] == subject_code), None)

    # List existing templates
    with engine.begin() as conn:
        all_templates = list_templates_for_subject(conn, subject_code)
        
        # Apply filters to templates
        templates = all_templates
        
        if filter_degree:
            templates = [t for t in templates if not t.get('degree_code') or t.get('degree_code') == filter_degree]
        
        if filter_program:
            templates = [t for t in templates if not t.get('program_code') or t.get('program_code') == filter_program]
        
        if filter_branch:
            templates = [t for t in templates if not t.get('branch_code') or t.get('branch_code') == filter_branch]

    st.markdown("---")
    st.markdown("### Existing Templates")
    
    if len(templates) < len(all_templates):
        st.caption(f"Showing {len(templates)} of {len(all_templates)} templates (filtered)")

    if templates:
        for tmpl in templates:
            status_emoji = "✅" if tmpl['is_current'] else "📦"
            deprecated_badge = " [DEPRECATED]" if tmpl.get('deprecated_from_ay') else ""
            
            with st.expander(
                f"{status_emoji} {tmpl['name']} ({tmpl['version']}){deprecated_badge}",
                expanded=tmpl['is_current']
            ):
                col1, col2, col3 = st.columns(3)
                with col1: st.metric("Points", tmpl['point_count'])
                with col2: st.metric("Used by Offerings", tmpl['usage_count'])
                with col3: st.metric("Version #", tmpl['version_number'])

                st.caption(f"**Code:** {tmpl['code']}")
                
                if tmpl.get('description'):
                    st.caption(f"**Description:** {tmpl['description']}")
                
                if tmpl.get('effective_from_ay'):
                    st.caption(f"**Effective from:** {tmpl['effective_from_ay']}")
                
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

                # Show points
                with engine.begin() as conn:
                    points = get_template_points(conn, tmpl['id'])

                if points:
                    df = pd.DataFrame(points)[['sequence', 'title', 'hours_weight']]
                    st.dataframe(df, use_container_width=True)

                if CAN_EDIT:
                    # Clone button
                    if st.button(f"Clone to New Version", key=f"clone_{tmpl['id']}"):
                        st.session_state[f'cloning_{tmpl["id"]}'] = True
                        st.rerun()
                    
                    # Handle cloning form
                    if st.session_state.get(f'cloning_{tmpl["id"]}'):
                        with st.form(f"clone_form_{tmpl['id']}"):
                            st.markdown("**Clone Template**")
                            
                            new_version = st.text_input("New Version*", placeholder="e.g., v2, 2025")
                            new_name = st.text_input("New Name*", placeholder=f"{tmpl['name']} (Updated)")
                            
                            col_submit, col_cancel = st.columns(2)
                            
                            with col_submit:
                                submit = st.form_submit_button("Create Clone", type="primary")
                            
                            with col_cancel:
                                cancel = st.form_submit_button("Cancel")
                            
                            if cancel:
                                st.session_state[f'cloning_{tmpl["id"]}'] = False
                                st.rerun()
                            
                            if submit:
                                if not new_version or not new_name:
                                    st.error("Version and Name are required")
                                else:
                                    try:
                                        new_id = clone_template(
                                            engine, tmpl['id'], new_version, new_name, actor
                                        )
                                        success(f"Template cloned with ID {new_id}")
                                        st.session_state[f'cloning_{tmpl["id"]}'] = False
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
    else:
        if filter_degree or filter_program or filter_branch or filter_cg or selected_year != "All" or selected_term != "All":
            st.info(f"No templates found for {subject_code} matching the selected filters")
        else:
            st.info(f"No templates found for {subject_code}")

    # Create new template
    if CAN_EDIT:
        st.markdown("---")
        st.markdown("### Create New Template")

        # Check if we're in create mode
        if not st.session_state.get('creating_template'):
            if st.button("➕ Create New Template", type="primary", use_container_width=True):
                st.session_state.creating_template = True
                # Reset number of points to 1
                if "template_num_points" in st.session_state:
                    st.session_state.template_num_points = 1
                st.rerun()
        else:
            # Show create form
            st.info(f"Creating template for: **{subject_code}** ({selected_subject_degree})")
            
            # Number of points input (OUTSIDE form)
            num_points = st.number_input(
                "Number of Points", 
                min_value=1, 
                max_value=50, 
                value=1,
                key="template_num_points"
            )

            with st.form("create_template_form"):
                col1, col2 = st.columns(2)

                with col1:
                    version = st.text_input("Version*", placeholder="e.g., v1, 2024")
                    name = st.text_input("Template Name*", placeholder="e.g., Standard Syllabus 2024")

                with col2:
                    effective_from_ay = st.text_input("Effective From AY", placeholder="e.g., 2024-25")
                    description = st.text_area("Description", height=80)
                
                # Scope (pre-populated with filter values)
                st.markdown("**Scope (optional - leave blank for general templates)**")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    scope_degree = st.text_input(
                        "Degree Code",
                        value=filter_degree or selected_subject_degree or "",
                        key="template_scope_degree",
                        help="Leave blank for templates applicable to all degrees"
                    )
                
                with col2:
                    scope_program = st.text_input(
                        "Program Code",
                        value=filter_program or "",
                        key="template_scope_program",
                        help="Leave blank for templates applicable to all programs"
                    )
                
                with col3:
                    scope_branch = st.text_input(
                        "Branch Code",
                        value=filter_branch or "",
                        key="template_scope_branch",
                        help="Leave blank for templates applicable to all branches"
                    )

                st.markdown("**Syllabus Points**")

                points_data = []

                for i in range(num_points):
                    with st.expander(f"Point {i+1}", expanded=i < 5):
                        cols = st.columns([1, 3, 1])

                        with cols[0]:
                            seq = st.number_input(
                                "Seq", value=i + 1, key=f"pt_seq_{i}",
                                label_visibility="collapsed",
                            )
                        with cols[1]:
                            title = st.text_input("Title*", key=f"pt_title_{i}")
                        with cols[2]:
                            hours = st.number_input(
                                "Hrs", value=2.0, step=0.5,
                                key=f"pt_hrs_{i}", label_visibility="collapsed",
                            )

                        desc = st.text_area("Description", key=f"pt_desc_{i}", height=60)
                        tags = st.text_input("Tags", key=f"pt_tags_{i}")
                        resources = st.text_input("Resources", key=f"pt_res_{i}")

                        points_data.append({
                            "sequence": seq, "title": title, "description": desc,
                            "tags": tags, "resources": resources, "hours_weight": hours
                        })

                col_submit, col_cancel = st.columns(2)
                
                with col_submit:
                    submitted = st.form_submit_button("Create Template", type="primary")
                
                with col_cancel:
                    cancel_create = st.form_submit_button("Cancel")

                if cancel_create:
                    st.session_state.creating_template = False
                    if "template_num_points" in st.session_state:
                        st.session_state.template_num_points = 1
                    st.rerun()

                if submitted:
                    if not version or not name:
                        st.error("Version and Name are required")
                    elif not any(p["title"] for p in points_data):
                        st.error("At least one point with a title is required")
                    else:
                        try:
                            valid_points = [p for p in points_data if p["title"]]

                            template_id = create_syllabus_template(
                                engine, subject_code, version, name,
                                valid_points, actor,
                                description=description,
                                effective_from_ay=effective_from_ay or None,
                                degree_code=scope_degree or None,
                                program_code=scope_program or None,
                                branch_code=scope_branch or None,
                            )

                            success(f"Template created with ID {template_id}")
                            
                            # Reset state
                            st.session_state.creating_template = False
                            if "template_num_points" in st.session_state:
                                st.session_state.template_num_points = 1
                            
                            st.cache_data.clear()
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error: {str(e)}")
