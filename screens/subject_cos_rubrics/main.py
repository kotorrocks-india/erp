# screens/subject_cos_rubrics/main.py
"""
Main entry point for Subject COs and Rubrics Management
"""

import streamlit as st
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def check_permissions() -> bool:
    user = st.session_state.get("user", {})
    roles = user.get("roles", set())
    allowed_roles = {"superadmin", "principal", "director", "academic_admin", "faculty", "tech_admin"}
    return bool(roles & allowed_roles) or not roles

def render_subject_cos_rubrics_page():
    st.title("📚 Subject Course Outcomes & Rubrics")
    
    if not check_permissions():
        st.error("⛔ You don't have permission to access this module.")
        return
    
    engine = st.session_state.get("engine")
    if not engine:
        st.error("❌ Database engine not initialized")
        return
    
    try:
        from screens.subject_cos_rubrics.subject_catalog_tab import render_subject_catalog_tab
        from screens.subject_cos_rubrics.shared_filters import render_co_filters
        from screens.subject_cos_rubrics.course_outcomes_tab import render_course_outcomes_tab
        from screens.subject_cos_rubrics.course_outcomes_import_export_tab import render_co_import_export_tab
        from screens.subject_cos_rubrics.mass_import_tab import render_mass_import_tab
        from screens.subject_cos_rubrics.course_outcomes_audit_tab import render_co_audit_tab
        
        # --- FIX: Import from the correct rubrics folder ---
        from screens.rubrics.rubrics_main import render_integrated_rubrics 

    except ImportError as e:
        st.error(f"❌ Failed to import module components: {e}")
        logger.error(f"Import error: {e}", exc_info=True)
        return
    
    # 1. Catalog View
    st.markdown("---")
    with st.expander("📋 View Subject Catalog Details (Reference)"):
        render_subject_catalog_tab(engine)
    st.markdown("---")

    # 2. Shared Filters
    offering_id, offering_info = render_co_filters(engine)
    
    if "co_main_degree" in st.session_state:
        st.session_state.co_main_degree_val = st.session_state.co_main_degree
    if "co_main_ay" in st.session_state:
        st.session_state.co_main_ay_val = st.session_state.co_main_ay

    # 3. Tabs
    tab_co, tab_rubrics, tab_single_io, tab_mass_io, tab_audit = st.tabs([
        "🎯 Course Outcomes",
        "📊 Rubrics",
        "⬆️ Single Import/Export",
        "📦 Mass Import (Degree)",
        "📜 CO Audit Trail"
    ])
    
    with tab_co:
        render_course_outcomes_tab(engine, offering_id, offering_info)
    
    with tab_rubrics:
        # --- FIX: Use the new integrated renderer ---
        render_integrated_rubrics(engine, offering_id)

    with tab_single_io:
        render_co_import_export_tab(engine, offering_id, offering_info)

    with tab_mass_io:
        render_mass_import_tab(engine)

    with tab_audit:
        render_co_audit_tab(engine, offering_id, offering_info)


if __name__ == "__main__":
    render_subject_cos_rubrics_page()
