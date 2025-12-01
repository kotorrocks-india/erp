"""
Reusable UI Components
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import List

from models.context import Context
from models.faculty import FacultyWithAffiliation
from config import COLORS, DAYS


class UIComponents:
    """Reusable UI components"""
    
    @staticmethod
    def render_context_filters(engine: Engine) -> Context:
        """Render sidebar filters and return Context"""
        st.sidebar.header("🎯 Context Filters")
        
        # Fetch options
        with engine.connect() as conn:
            ays = pd.read_sql(
                "SELECT ay_code FROM academic_years WHERE status='open' ORDER BY ay_code DESC",
                conn
            )
            # FIX: Changed 'name' to 'title as name'
            degrees = pd.read_sql(
                "SELECT code, title as name FROM degrees WHERE active=1 ORDER BY code",
                conn
            )
        
        if ays.empty or degrees.empty:
            st.sidebar.error("No Academic Years or Degrees configured")
            st.stop()
        
        # AY & Degree
        # ... (Rest of the function remains the same)        
        # AY & Degree
        ay = st.sidebar.selectbox("Academic Year", ays['ay_code'].tolist(), key='ctx_ay')
        degree = st.sidebar.selectbox("Degree", degrees['code'].tolist(), key='ctx_degree')
        
        # Program & Branch
        with engine.connect() as conn:
            progs = pd.read_sql(
                text("SELECT program_code FROM programs WHERE degree_code=:d AND active=1 ORDER BY program_code"),
                conn, params={"d": degree}
            )
        
        program = None
        branch = None
        
        if not progs.empty:
            if len(progs) > 1:
                program = st.sidebar.selectbox("Program", [None] + progs['program_code'].tolist(), key='ctx_prog')
            else:
                program = progs['program_code'].iloc[0]
                st.sidebar.info(f"Program: {program}")
        
        if program:
            with engine.connect() as conn:
                branches = pd.read_sql(
                    text("""
                        SELECT b.branch_code 
                        FROM branches b
                        JOIN programs p ON b.program_id = p.id
                        WHERE p.program_code=:p AND b.active=1
                        ORDER BY b.branch_code
                    """),
                    conn, params={"p": program}
                )
            
            if not branches.empty:
                branch = st.sidebar.selectbox("Branch", [None] + branches['branch_code'].tolist(), key='ctx_branch')
        
        # Year & Term
        col1, col2 = st.sidebar.columns(2)
        year = col1.number_input("Year", 1, 5, 1, key='ctx_year')
        term = col2.number_input("Term", 1, 2, 1, key='ctx_term')
        
        # Division
        ctx_temp = Context(ay, degree, program, branch, year, term, None)
        
        with engine.connect() as conn:
            # Check if degree uses divisions
            uses_div = conn.execute(
                text("SELECT uses_divisions FROM degrees WHERE code=:d"),
                {"d": degree}
            ).scalar()
            
            division = None
            if uses_div:
                # Fetch actual divisions or use defaults
                divs = pd.read_sql(
                    text("""
                        SELECT DISTINCT division_code 
                        FROM student_enrollments 
                        WHERE degree_code=:deg AND ay_label=:ay AND year=:yr
                        ORDER BY division_code
                    """),
                    conn, params=ctx_temp.to_dict()
                )
                
                if not divs.empty:
                    division = st.sidebar.selectbox("Division", divs['division_code'].tolist(), key='ctx_div')
                else:
                    division = st.sidebar.selectbox("Division", ['A', 'B', 'C'], key='ctx_div')
        
        st.sidebar.divider()
        ctx = Context(ay, degree, program, branch, year, term, division)
        st.sidebar.info(f"**Editing:** {ctx}")
        
        return ctx
    
    @staticmethod
    def render_legend():
        """Render color legend for timetable"""
        st.markdown(f"""
        <div style="padding: 10px; background: #f8f9fa; border-radius: 5px; margin: 10px 0;">
            <strong>Legend:</strong><br/>
            <span style="color: {COLORS['in_charge']};">●</span> Subject In-Charge &nbsp;
            <span style="color: {COLORS['regular']};">●</span> Subject Faculty &nbsp;
            <span style="color: {COLORS['visiting']};">●</span> Visiting Faculty &nbsp;
            <span style="background: {COLORS['extended']}; padding: 2px 6px;">*</span> Extended Afternoon &nbsp;
            <span style="background: {COLORS['all_day']}; padding: 2px 6px;">†</span> All-Day Elective
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def render_faculty_picker(faculty_list: List[FacultyWithAffiliation],
                             label: str = "Select Faculty",
                             key: str = "faculty_picker",
                             allow_visiting_in_charge: bool = False,
                             min_selection: int = 1,
                             max_selection: int = 10) -> List[str]:
        """
        Render faculty multi-select picker.
        
        Returns: List of selected faculty emails
        """
        if not faculty_list:
            st.warning("No faculty available")
            return []
        
        # Build options
        options = {f.email: f.display_name for f in faculty_list}
        
        # Multi-select
        selected = st.multiselect(
            label,
            options=list(options.keys()),
            format_func=lambda x: options[x],
            key=key,
            help=f"Select {min_selection} to {max_selection} faculty. First will be Subject In-Charge."
        )
        
        # Validation messages
        if selected:
            if len(selected) < min_selection:
                st.warning(f"Select at least {min_selection} faculty")
            elif len(selected) > max_selection:
                st.error(f"Maximum {max_selection} faculty allowed")
            else:
                # Show in-charge info
                in_charge_email = selected[0]
                in_charge = next((f for f in faculty_list if f.email == in_charge_email), None)
                
                if in_charge:
                    if in_charge.is_visiting:
                        if allow_visiting_in_charge:
                            st.info(f"👑 In-Charge: {in_charge.name} (Visiting - Override Active)")
                        else:
                            st.error(f"⚠️ {in_charge.name} is Visiting. Cannot be In-Charge. Enable override or reorder.")
                    else:
                        st.success(f"👑 In-Charge: {in_charge.name} (Core)")
        
        return selected
    
    @staticmethod
    def render_faculty_pill(faculty: FacultyWithAffiliation, is_in_charge: bool = False) -> str:
        """Render a faculty name as colored pill HTML"""
        if is_in_charge:
            css_class = "faculty-pill in-charge"
            prefix = "👑 "
        elif faculty.is_visiting:
            css_class = "faculty-pill visiting"
            prefix = ""
        else:
            css_class = "faculty-pill regular"
            prefix = ""
        
        return f'<span class="{css_class}">{prefix}{faculty.name}</span>'
    
    @staticmethod
    def render_status_badge(status: str) -> str:
        """Render status badge HTML"""
        labels = {
            'draft': '📝 Draft',
            'published': '✅ Published',
            'archived': '📦 Archived',
        }
        css_class = f"status-{status}"
        return f'<span class="{css_class}"><strong>{labels.get(status, status)}</strong></span>'
    
    @staticmethod
    def render_quick_jump_buttons():
        """Render quick jump buttons between tabs"""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("← Subject Distribution"):
                st.session_state['active_tab'] = 0
                st.rerun()
        
        with col2:
            if st.button("🗓️ Timetable Grid"):
                st.session_state['active_tab'] = 1
                st.rerun()
        
        with col3:
            if st.button("Operations →"):
                st.session_state['active_tab'] = 2
                st.rerun()
    
    @staticmethod
    def confirm_action(message: str, key: str) -> bool:
        """
        Confirm a destructive action.
        
        Returns: True if confirmed
        """
        if st.session_state.get(f'confirm_{key}') != True:
            st.warning(f"⚠️ {message}")
            if st.button("Click again to confirm", key=f'confirm_btn_{key}'):
                st.session_state[f'confirm_{key}'] = True
                st.rerun()
            return False
        else:
            # Reset confirmation after action
            st.session_state[f'confirm_{key}'] = False
            return True
