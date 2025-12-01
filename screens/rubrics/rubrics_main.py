# screens/rubrics/rubrics_main.py
"""
Rubrics Management UI (Global Library Only).
"""

import streamlit as st
import pandas as pd
from typing import Optional, Dict
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text

# Local Imports
from core.settings import load_settings
from core.db import get_engine
from core.policy import require_page, can_edit_page, user_roles
from .rubrics_service import RubricsService

# Use shared fetchers for dropdowns
from screens.subject_cos_rubrics.shared_filters import (
    fetch_degrees, fetch_programs_by_degree, fetch_branches_by_program
)

try:
    from core.forms import tagline, success
except ImportError:
    def tagline(): pass
    def success(msg): st.success(msg)

PAGE_TITLE = "📋 Rubrics Definitions"

# ===========================================================================
# INTEGRATED RENDERER (Main Entry Point)
# ===========================================================================

def render_integrated_rubrics(engine: Engine, offering_id: Optional[int]):
    """
    Renders the Global Rubric Library.
    If offering_id is provided, it automatically filters the library 
    to match that offering's Degree.
    """
    service = RubricsService(engine)
    user = st.session_state.get("user") or {}
    actor = user.get("email", "system")
    can_edit = True 

    # 1. Context Awareness
    auto_degree_code = None
    
    if offering_id:
        with engine.begin() as conn:
            res = conn.execute(
                sa_text("""
                SELECT 
                    so.degree_code, 
                    so.subject_code, 
                    sc.subject_name 
                FROM subject_offerings so
                LEFT JOIN subjects_catalog sc ON so.subject_code = sc.subject_code
                WHERE so.id=:id
                """), 
                {"id": offering_id}
            ).fetchone()
            
            if res:
                auto_degree_code = res.degree_code
                subj_name = res.subject_name if res.subject_name else "(Unknown Name)"
                st.caption(f"Showing Rubric Categories for **{auto_degree_code}** (based on {res.subject_code} - {subj_name})")

    # 2. Render the Library
    render_criteria_catalog_tab(engine, service, actor, can_edit, default_degree=auto_degree_code)


# ===========================================================================
# TAB: GLOBAL CRITERIA CATALOG
# ===========================================================================

def render_criteria_catalog_tab(engine: Engine, service: RubricsService, actor: str, can_edit: bool, default_degree: str = None):
    """Tab for managing global criteria categories."""
    
    st.subheader("📚 Global Rubric Categories")
    st.markdown("""
    Define standard grading buckets (e.g., **Content**, **Expression**) here.
    These are used when defining assessments.
    """)

    cat_tab1, cat_tab2 = st.tabs(["Manage Categories", "Import / Export"])

    # --- SUB-TAB 1: MANAGE ---
    with cat_tab1:
        if "edit_category_id" not in st.session_state: st.session_state.edit_category_id = None

        # 1. EDIT FORM
        if st.session_state.edit_category_id:
            st.markdown("#### ✏️ Edit Category")
            catalog = service.get_criteria_catalog(active_only=False)
            current_data = next((c for c in catalog if c['id'] == st.session_state.edit_category_id), None)
            
            if current_data:
                # --- EDIT SCOPE SELECTION (Cascading) ---
                st.caption("Scope (Leave Degree empty for Global)")
                
                # Degree Dropdown
                degrees = fetch_degrees(engine)
                deg_opts = {"Global (All Degrees)": None}
                deg_opts.update({f"{d['code']} - {d['title']}": d['code'] for d in degrees})
                
                # Find current index
                curr_deg = current_data['degree_code']
                deg_idx = 0
                if curr_deg:
                    deg_keys = list(deg_opts.keys())
                    for i, k in enumerate(deg_keys):
                        if deg_opts[k] == curr_deg:
                            deg_idx = i
                            break
                
                c_sc1, c_sc2, c_sc3 = st.columns(3)
                sel_deg_label = c_sc1.selectbox("Degree", options=list(deg_opts.keys()), index=deg_idx, key="edit_deg")
                sel_deg_code = deg_opts[sel_deg_label]

                # Program Dropdown (Dependent on Degree)
                sel_prog_code = None
                sel_prog_id = None # Needed for branch fetch
                
                if sel_deg_code:
                    progs = fetch_programs_by_degree(engine, sel_deg_code)
                    prog_opts = {"All Programs": (None, None)}
                    prog_opts.update({f"{p['code']}": (p['code'], p['id']) for p in progs})
                    
                    # Find current index
                    curr_prog = current_data['program_code']
                    prog_idx = 0
                    if curr_prog:
                        prog_keys = list(prog_opts.keys())
                        for i, k in enumerate(prog_keys):
                            if prog_opts[k][0] == curr_prog:
                                prog_idx = i
                                break
                    
                    sel_prog_label = c_sc2.selectbox("Program", options=list(prog_opts.keys()), index=prog_idx, key="edit_prog")
                    sel_prog_code, sel_prog_id = prog_opts[sel_prog_label]
                else:
                    c_sc2.selectbox("Program", ["- Select Degree First -"], disabled=True, key="edit_prog_dis")

                # Branch Dropdown (Dependent on Program)
                sel_branch_code = None
                if sel_prog_id:
                    branches = fetch_branches_by_program(engine, sel_deg_code, sel_prog_id)
                    branch_opts = {"All Branches": None}
                    branch_opts.update({f"{b['code']}": b['code'] for b in branches})
                    
                    # Find current index
                    curr_branch = current_data['branch_code']
                    branch_idx = 0
                    if curr_branch:
                        branch_keys = list(branch_opts.keys())
                        for i, k in enumerate(branch_keys):
                            if branch_opts[k] == curr_branch:
                                branch_idx = i
                                break

                    sel_branch_label = c_sc3.selectbox("Branch", options=list(branch_opts.keys()), index=branch_idx, key="edit_branch")
                    sel_branch_code = branch_opts[sel_branch_label]
                else:
                    c_sc3.selectbox("Branch", ["- Select Program First -"], disabled=True, key="edit_branch_dis")

                # Form Content
                with st.form("edit_cat_form_inner"):
                    c1, c2 = st.columns(2)
                    new_label = c1.text_input("Category Name*", value=current_data['label'])
                    new_desc = c2.text_area("Description", value=current_data['description'] or "", height=38)
                    
                    c_submit, c_cancel = st.columns([1, 6])
                    if c_submit.form_submit_button("Update"):
                        service.update_catalog_criterion(
                            current_data['id'], new_label, new_desc, 
                            sel_deg_code, sel_prog_code, sel_branch_code
                        )
                        success("Updated!")
                        st.session_state.edit_category_id = None
                        st.rerun()
                    if c_cancel.form_submit_button("Cancel"):
                        st.session_state.edit_category_id = None
                        st.rerun()

        # 2. ADD FORM
        elif can_edit:
            with st.expander("➕ Add New Category", expanded=False):
                st.caption("Scope Selection")
                
                # Degree
                degrees = fetch_degrees(engine)
                deg_opts = {"Global (All Degrees)": None}
                deg_opts.update({f"{d['code']} - {d['title']}": d['code'] for d in degrees})
                
                # Default selection logic
                def_idx = 0
                if default_degree:
                    keys = list(deg_opts.keys())
                    for i, k in enumerate(keys):
                        if deg_opts[k] == default_degree:
                            def_idx = i
                            break

                cols = st.columns(3)
                
                # 1. Degree Select
                sel_d_label = cols[0].selectbox("Degree", options=list(deg_opts.keys()), index=def_idx, key="add_cat_deg")
                sel_d_code = deg_opts[sel_d_label]
                
                # 2. Program Select (Dynamic)
                sel_p_code = None
                sel_p_id = None
                if sel_d_code:
                    progs = fetch_programs_by_degree(engine, sel_d_code)
                    prog_opts = {"All Programs": (None, None)}
                    prog_opts.update({f"{p['code']}": (p['code'], p['id']) for p in progs})
                    
                    sel_p_label = cols[1].selectbox("Program", options=list(prog_opts.keys()), key="add_cat_prog")
                    sel_p_code, sel_p_id = prog_opts[sel_p_label]
                else:
                    cols[1].selectbox("Program", ["- Select Degree First -"], disabled=True, key="add_cat_prog_dis")

                # 3. Branch Select (Dynamic)
                sel_b_code = None
                if sel_p_id:
                    branches = fetch_branches_by_program(engine, sel_d_code, sel_p_id)
                    branch_opts = {"All Branches": None}
                    branch_opts.update({f"{b['code']}": b['code'] for b in branches})
                    
                    sel_b_label = cols[2].selectbox("Branch", options=list(branch_opts.keys()), key="add_cat_branch")
                    sel_b_code = branch_opts[sel_b_label]
                else:
                    cols[2].selectbox("Branch", ["- Select Program First -"], disabled=True, key="add_cat_branch_dis")

                with st.form("submit_cat"):
                    c1, c2 = st.columns(2)
                    l = c1.text_input("Category Name*", placeholder="e.g., Content")
                    d = c2.text_area("Description", height=38, placeholder="Short description")
                    
                    if st.form_submit_button("Create Category"):
                        if not l:
                            st.error("Name required")
                        else:
                            k = l.strip().lower().replace(" ", "_")
                            service.add_catalog_criterion(k, l, d, sel_d_code, sel_p_code, sel_b_code)
                            success(f"Created '{l}'!")
                            st.rerun()

        # 3. LIST VIEW
        st.markdown("---")
        
        # Filter View based on Context
        catalog = service.get_criteria_catalog(active_only=False)
        
        if default_degree:
            # Show Global AND Degree specific
            filtered_catalog = [c for c in catalog if c['degree_code'] is None or c['degree_code'] == default_degree]
        else:
            filtered_catalog = catalog

        if filtered_catalog:
            for cat in filtered_catalog:
                col_info, col_actions = st.columns([4, 1])
                with col_info:
                    # Badge Logic
                    badges = []
                    if cat['degree_code']: badges.append(f"🎓 {cat['degree_code']}")
                    else: badges.append("🌐 Global")
                    
                    if cat['program_code']: badges.append(f"📂 {cat['program_code']}")
                    if cat['branch_code']: badges.append(f"🌿 {cat['branch_code']}")
                    
                    st.markdown(f"**{cat['label']}** · <small>{' '.join(badges)}</small>", unsafe_allow_html=True)
                    if cat['description']: st.caption(cat['description'])
                
                if can_edit:
                    with col_actions:
                        c_edit, c_del = st.columns(2)
                        if c_edit.button("✏️", key=f"edit_{cat['id']}"):
                            st.session_state.edit_category_id = cat['id']
                            st.rerun()
                        if c_del.button("🗑️", key=f"del_{cat['id']}"):
                            if service.delete_catalog_criterion(cat['id']):
                                success("Deleted")
                                st.rerun()
                st.divider()
        else:
            st.info("No categories found for this scope.")

    # --- SUB-TAB 2: IMPORT / EXPORT ---
    with cat_tab2:
        st.markdown("#### 📥 Import / Export Categories")
        st.info("Use this to bulk update descriptions or add new categories. The system matches records by **Label + Degree + Program + Branch**.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 Download Template", service.generate_catalog_template(), "rubric_cat_template.csv", "text/csv")
            csv = service.export_catalog_csv()
            if csv: st.download_button("📥 Export Catalog", csv, "rubric_cat_export.csv", "text/csv")
        
        with c2:
            file = st.file_uploader("Upload CSV", type=["csv"], key="cat_imp")
        
        if file:
            try:
                df = pd.read_csv(file)
                st.markdown("#### 🔍 Preview")
                
                # DRY RUN
                if st.button("Run Dry Run (Check Changes)", type="primary"):
                    with st.spinner("Analyzing..."):
                        report = service.process_import_catalog(df, execute=False)
                        st.session_state.cat_report = report
                
                if 'cat_report' in st.session_state:
                    report_df = pd.DataFrame(st.session_state.cat_report)
                    
                    # Metrics
                    updates = len(report_df[report_df['Action'] == 'Update'])
                    creates = len(report_df[report_df['Action'] == 'Create'])
                    
                    m1, m2 = st.columns(2)
                    m1.metric("🆕 New Records", creates)
                    m2.metric("♻️ Updates", updates)
                    
                    def highlight(val):
                        if val == 'Update': return 'color: orange; font-weight: bold'
                        if val == 'Create': return 'color: green; font-weight: bold'
                        return ''

                    st.dataframe(
                        report_df.style.map(highlight, subset=['Action']),
                        use_container_width=True,
                        column_config={"Action": st.column_config.TextColumn("Action", width="small")}
                    )
                    
                    st.markdown("---")
                    
                    # EXECUTE
                    ex1, ex2 = st.columns([1, 3])
                    with ex1:
                        if st.button("🚀 Execute Import"):
                            with st.spinner("Importing..."):
                                res = service.process_import_catalog(df, execute=True)
                                errors = [r for r in res if "Error" in r['Status']]
                                
                                if not errors:
                                    success(f"✅ Import Successful! ({creates} created, {updates} updated)")
                                    del st.session_state.cat_report
                                    st.rerun()
                                else:
                                    st.error(f"Completed with {len(errors)} errors.")
                                    st.dataframe(pd.DataFrame(errors))
                    with ex2:
                        if st.button("❌ Clear Preview"):
                            del st.session_state.cat_report
                            st.rerun()

            except Exception as e:
                st.error(f"Error processing file: {e}")


# ===========================================================================
# STANDALONE RENDER
# ===========================================================================

@require_page("Rubrics Management")
def render():
    st.title(PAGE_TITLE)
    tagline()
    settings = load_settings()
    engine = get_engine(settings.db.url)
    render_integrated_rubrics(engine, None)

if __name__ == "__main__":
    render()
