"""
Enhanced Weekly Planner & Timetable Application - CORRECTED QUERIES
Version: 8.5.0 - Fixed to match actual database schema
Location: app25/screens/timetable/app_weekly_planner.py

CRITICAL FIXES:
1. Query programs and branches tables SEPARATELY (like CIC filter does)
2. Use program_id for branches (not program_code)
3. Schema-corrected queries (status='open', title)
4. All imports and paths fixed
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text, create_engine
from sqlalchemy.engine import Engine
from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass
import sys
from pathlib import Path

# ========================================================================
# CRITICAL: Add ui/ directory to Python path for imports
# ========================================================================
_current_dir = Path(__file__).parent
_ui_dir = _current_dir / 'ui'
_services_dir = _current_dir / 'services'
_models_dir = _current_dir / 'models'

for _dir in [_ui_dir, _services_dir, _models_dir]:
    if _dir.exists() and str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ==============================================================================
# NEW TIMETABLE IMPORTS (Graceful degradation)
# ==============================================================================

try:
    from timetable_grid_fix import render_complete_excel_timetable
    REGULAR_TT_AVAILABLE = True
except ImportError as e:
    REGULAR_TT_AVAILABLE = False
    log.warning(f"⚠️ timetable_excel_complete not found: {e}")

try:
    from elective_timetable_excel import render_elective_timetable
    ELECTIVE_TT_AVAILABLE = True
except ImportError as e:
    ELECTIVE_TT_AVAILABLE = False
    log.warning(f"⚠️ elective_timetable_excel not found: {e}")

try:
    from cross_tt_conflict_dashboard import render_conflict_dashboard
    CONFLICTS_AVAILABLE = True
except ImportError as e:
    CONFLICTS_AVAILABLE = False
    log.warning(f"⚠️ cross_tt_conflict_dashboard not found: {e}")

# ==============================================================================
# SELF-HEALING DATABASE UTILITIES
# ==============================================================================
def auto_heal_database(engine: Engine):
    """Auto-creates missing views and tables"""
    try:
        with engine.begin() as conn:
            # v_day_templates_full view
            conn.execute(text("DROP VIEW IF EXISTS v_day_templates_full"))
            conn.execute(text("""
                CREATE VIEW v_day_templates_full AS
                SELECT 
                    t.*,
                    (SELECT COUNT(*) FROM day_template_slots s WHERE s.template_id = t.id) as total_slots,
                    (SELECT COUNT(*) FROM day_template_slots s WHERE s.template_id = t.id) as slot_count,
                    (SELECT COUNT(*) FROM day_template_slots s WHERE s.template_id = t.id AND s.is_teaching_slot = 1) as total_teaching_slots,
                    (SELECT COUNT(*) FROM day_template_slots s WHERE s.template_id = t.id AND s.is_teaching_slot = 1) as teaching_slot_count,
                    (SELECT COALESCE(SUM(duration_min),0) FROM day_template_slots s WHERE s.template_id = t.id) as total_minutes_all_slots,
                    (SELECT COALESCE(SUM(duration_min),0) FROM day_template_slots s WHERE s.template_id = t.id AND s.is_teaching_slot = 1) as total_teaching_minutes,
                    (SELECT COUNT(*) FROM day_template_weekday_overrides o WHERE o.template_id = t.id) as override_count,
                    CASE 
                        WHEN t.status = 'published' THEN '✅'
                        WHEN t.status = 'draft' THEN '📝'
                        WHEN t.status = 'archived' THEN '📦'
                        ELSE '❓'
                    END as status_display
                FROM day_templates t
                WHERE t.status != 'deleted';
            """))
    except Exception as e:
        log.warning(f"Auto-heal database warning: {e}")


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class Context:
    """Filter context for the application"""
    ay: str
    degree: str
    program: Optional[str]
    program_id: Optional[int]  # NEW: Store program_id for branch queries
    branch: Optional[str]
    branch_id: Optional[int]    # NEW: Store branch_id
    year: int
    term: int
    division: Optional[str]
    
    def to_dict(self) -> dict:
        return {
            'ay': self.ay,
            'deg': self.degree,
            'prog': self.program,
            'branch': self.branch,
            'yr': self.year,
            'term': self.term,
            'div': self.division
        }
    
    def to_context_dict(self) -> dict:
        """Return dict with standard keys for timetable functions"""
        return {
            'ay_label': self.ay,
            'degree_code': self.degree,
            'program_code': self.program,
            'branch_code': self.branch,
            'year': self.year,
            'term': self.term,
            'division_code': self.division
        }
    
    def __str__(self) -> str:
        parts = [f"{self.degree}", f"Y{self.year}T{self.term}"]
        if self.program: parts.append(f"Prog:{self.program}")
        if self.branch: parts.append(f"Branch:{self.branch}")
        if self.division: parts.append(f"Div:{self.division}")
        return " / ".join(parts)

# ==============================================================================
# DATABASE ACCESS LAYER (CORRECTED QUERIES)
# ==============================================================================

class DatabaseService:
    """Centralized database access with CORRECT queries matching CIC pattern"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def fetch_context_options(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch academic years and degrees - CORRECTED FOR USER'S SCHEMA"""
        with self.engine.connect() as conn:
            try:
                # CORRECTED: Use status='open' instead of active=1
                ays = pd.read_sql(
                    text("SELECT DISTINCT ay_code FROM academic_years WHERE status='open' ORDER BY ay_code DESC"),
                    conn
                )
            except Exception as e:
                log.error(f"Error fetching academic years: {e}")
                ays = pd.DataFrame()
            
            try:
                # CORRECTED: Use 'title' column instead of 'name'
                degrees = pd.read_sql(
                    text("SELECT DISTINCT code, title FROM degrees WHERE active=1 ORDER BY code"),
                    conn
                )
            except Exception as e:
                log.error(f"Error fetching degrees: {e}")
                degrees = pd.DataFrame()
            
            return ays, degrees
    
    def fetch_programs(self, degree: str) -> pd.DataFrame:
        """
        Fetch programs for a degree - CORRECTED to match CIC pattern.
        Returns: DataFrame with columns [id, program_code, program_name]
        """
        with self.engine.connect() as conn:
            try:
                # CORRECTED: Query programs table directly, include ID
                progs = pd.read_sql(
                    text("""
                        SELECT id, program_code, program_name
                        FROM programs 
                        WHERE degree_code=:deg AND active=1
                        ORDER BY sort_order, program_code
                    """),
                    conn, params={'deg': degree}
                )
                return progs
            except Exception as e:
                log.error(f"Error fetching programs: {e}")
                return pd.DataFrame()
    
    def fetch_branches(self, degree: str, program_id: int) -> pd.DataFrame:
        """
        Fetch branches for a program - CORRECTED to match CIC pattern.
        Uses program_id (not program_code)!
        Returns: DataFrame with columns [id, branch_code, branch_name]
        """
        if not program_id:
            return pd.DataFrame()
        
        with self.engine.connect() as conn:
            try:
                # CORRECTED: Query branches table with program_id
                branches = pd.read_sql(
                    text("""
                        SELECT id, branch_code, branch_name
                        FROM branches 
                        WHERE degree_code=:deg AND program_id=:prog_id AND active=1
                        ORDER BY sort_order, branch_code
                    """),
                    conn, params={'deg': degree, 'prog_id': program_id}
                )
                return branches
            except Exception as e:
                log.error(f"Error fetching branches: {e}")
                return pd.DataFrame()
    
    def fetch_divisions(self, ctx: Context) -> List[str]:
        """Fetch divisions for the given context"""
        with self.engine.connect() as conn:
            # Try student_enrollments first
            try:
                divs = pd.read_sql(
                    text("""
                        SELECT DISTINCT division_code 
                        FROM student_enrollments 
                        WHERE degree_code=:deg 
                        AND current_year=:yr
                        AND division_code IS NOT NULL
                        AND enrollment_status='active'
                        ORDER BY division_code
                    """),
                    conn, params={'deg': ctx.degree, 'yr': ctx.year}
                )
                if not divs.empty:
                    return divs['division_code'].tolist()
            except Exception as e:
                log.debug(f"student_enrollments query failed: {e}")
            
            # Fallback: Try division_master
            try:
                divs = pd.read_sql(
                    text("""
                        SELECT DISTINCT division_code 
                        FROM division_master 
                        WHERE degree_code=:deg 
                        AND current_year=:yr
                        AND active=1
                        ORDER BY division_code
                    """),
                    conn, params={'deg': ctx.degree, 'yr': ctx.year}
                )
                if not divs.empty:
                    return divs['division_code'].tolist()
            except Exception as e:
                log.debug(f"division_master query failed: {e}")
            
            # Final fallback - no divisions found, degree has no divisions
            return []

# ==============================================================================
# UI COMPONENTS
# ==============================================================================

class ContextSelector:
    """Main page context selection component - CORRECTED"""
    
    @staticmethod
    def render(db: DatabaseService, key_prefix: str = "main") -> Optional[Context]:
        """Render context selection on main page."""
        st.subheader("🎯 Select Context")
        
        ays, degrees = db.fetch_context_options()
        
        if ays.empty or degrees.empty:
            st.warning("⚠️ Database missing Academic Years or Degrees.")
            
            with st.expander("🔍 Debug Info"):
                st.write("**Academic Years found:**", len(ays))
                if not ays.empty:
                    st.dataframe(ays)
                else:
                    st.error("No academic years with status='open' found")
                
                st.write("**Degrees found:**", len(degrees))
                if not degrees.empty:
                    st.dataframe(degrees)
                else:
                    st.error("No active degrees found")
            
            return None
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            ay = st.selectbox("Academic Year", ays['ay_code'].tolist(), key=f'{key_prefix}_ctx_ay')
        
        with col2:
            degree_options = degrees['code'].tolist()
            degree_display = {row['code']: f"{row['code']} - {row['title']}" for _, row in degrees.iterrows()}
            
            degree = st.selectbox(
                "Degree", 
                degree_options,
                format_func=lambda x: degree_display.get(x, x),
                key=f'{key_prefix}_ctx_degree'
            )
        
        with col3:
            year = st.number_input("Year", min_value=1, max_value=5, value=1, key=f'{key_prefix}_ctx_year')
        
        # CORRECTED: Fetch programs with ID
        progs = db.fetch_programs(degree)
        program = None
        program_id = None
        branch = None
        branch_id = None
        
        col4, col5, col6 = st.columns(3)
        
        with col4:
            if not progs.empty:
                if len(progs) > 1:
                    prog_options = [None] + progs['program_code'].tolist()
                    prog_display = {None: "-- Select --"}
                    prog_display.update({
                        row['program_code']: f"{row['program_code']} - {row['program_name']}" 
                        for _, row in progs.iterrows()
                    })
                    
                    program = st.selectbox(
                        "Program", 
                        prog_options,
                        format_func=lambda x: prog_display.get(x, x),
                        key=f'{key_prefix}_ctx_prog'
                    )
                    
                    if program:
                        program_id = progs[progs['program_code'] == program]['id'].iloc[0]
                else:
                    program = progs['program_code'].iloc[0]
                    program_id = progs['id'].iloc[0]
                    st.info(f"Program: **{program}**")
        
        with col5:
            if program_id:
                # CORRECTED: Fetch branches using program_id
                branches = db.fetch_branches(degree, program_id)
                if not branches.empty:
                    branch_options = [None] + branches['branch_code'].tolist()
                    branch_display = {None: "-- Select --"}
                    branch_display.update({
                        row['branch_code']: f"{row['branch_code']} - {row['branch_name']}" 
                        for _, row in branches.iterrows()
                    })
                    
                    branch = st.selectbox(
                        "Branch", 
                        branch_options,
                        format_func=lambda x: branch_display.get(x, x),
                        key=f'{key_prefix}_ctx_branch'
                    )
                    
                    if branch:
                        branch_id = branches[branches['branch_code'] == branch]['id'].iloc[0]
        
        with col6:
            term = st.number_input("Term", min_value=1, max_value=2, value=1, key=f'{key_prefix}_ctx_term')
        
        # Create temp context for division fetch
        ctx_temp = Context(ay, degree, program, program_id, branch, branch_id, year, term, None)
        available_divisions = db.fetch_divisions(ctx_temp)
        division = None
        
        if available_divisions:
            col7, col8 = st.columns([1, 2])
            with col7:
                # Add "None (All Divisions)" option
                division_options = ['None (All Divisions)'] + available_divisions
                selected = st.selectbox("Division", division_options, key=f'{key_prefix}_ctx_div')
                # Convert "None (All Divisions)" to actual None
                division = None if selected == 'None (All Divisions)' else selected
        else:
            # No divisions exist for this degree - don't show selector
            st.info("ℹ️ This degree has no divisions configured")
        
        return Context(ay, degree, program, program_id, branch, branch_id, year, term, division)

# ==============================================================================
# TAB RENDER FUNCTIONS
# ==============================================================================

def render_distribution_tab(ctx: Context, engine: Engine):
    """Render distribution tab"""
    try:
        from distribution_tab import DistributionTab
        DistributionTab(ctx, engine).render()
    except ImportError as e:
        st.warning(f"📋 Distribution module not found: {e}")
        st.info("Looking for: ui/distribution_tab.py")

def render_periods_config_tab(engine: Engine):
    """Render periods configuration tab - CORRECTED IMPORT"""
    try:
        from periods_page import PeriodsConfigPage
        PeriodsConfigPage(engine).render()
    except ImportError as e:
        st.error(f"❌ Periods module import error")
        
        with st.expander("🐛 Diagnostic Info"):
            st.code(f"Error: {e}")
            st.write("**Python path:**")
            for p in sys.path[:5]:
                st.code(p)
            
            st.write("**Looking for files in:**")
            ui_dir = Path(__file__).parent / 'ui'
            st.code(str(ui_dir))
            
            if ui_dir.exists():
                st.write("**Files found:**")
                files = list(ui_dir.glob('periods*.py'))
                for f in files:
                    st.write(f"✅ {f.name}")
            else:
                st.error(f"❌ Directory not found: {ui_dir}")
        
        st.info("""
        **Required files in ui/ folder:**
        1. periods_page.py
        2. periods_config_ui.py
        3. periods_config_ui_part2.py
        """)

# ==============================================================================
# MAIN APPLICATION
# ==============================================================================

def get_engine() -> Engine:
    """Get database engine"""
    if 'engine' not in st.session_state:
        try:
            # Try config.py first
            from config import get_engine as config_get_engine
            st.session_state['engine'] = config_get_engine()
            log.info("Engine loaded from config.py")
        except ImportError:
            try:
                # Try database/connection.py
                from database.connection import get_engine as db_get_engine
                st.session_state['engine'] = db_get_engine()
                log.info("Engine loaded from database/connection.py")
            except ImportError:
                # Fallback - look for database
                current_dir = Path(__file__).parent
                db_candidates = [
                    current_dir.parent.parent / "app_v2.db",  # app25/app_v2.db
                    current_dir.parent / "app_v2.db",         # screens/app_v2.db
                    current_dir / "database" / "app_v2.db",   # timetable/database/app_v2.db
                    Path("app_v2.db"),                        # current directory
                    Path("lpep.db"),                          # fallback name
                ]
                
                for db_path in db_candidates:
                    if db_path.exists():
                        st.session_state['engine'] = create_engine(f"sqlite:///{db_path}")
                        log.info(f"Engine created for database: {db_path}")
                        break
                else:
                    # Last resort - create new database
                    st.session_state['engine'] = create_engine("sqlite:///lpep.db")
                    log.warning("Created new database: lpep.db")
    
    return st.session_state['engine']

def main(key_prefix: str = "weekly_planner_v8"):
    """Main application entry point"""
    
    try:
        st.set_page_config(
            page_title="LPEP - Weekly Planner", 
            layout="wide", 
            initial_sidebar_state="collapsed"
        )
    except Exception:
        pass

    st.title("🗓️ LPEP - Weekly Planner & Timetable Studio")
    st.caption("Complete workflow: Configure → Plan → Schedule → Validate")
    
    engine = get_engine()
    db = DatabaseService(engine)
    
    try:
        auto_heal_database(engine)
    except Exception as e:
        log.warning(f"Auto-heal warning: {e}")
    
    ctx = ContextSelector.render(db, key_prefix=key_prefix)
    
    if ctx:
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📚 Degree", ctx.degree)
        col2.metric("📅 AY", ctx.ay)
        col3.metric("🎓 Year", f"Year {ctx.year}")
        col4.metric("📖 Term", f"Term {ctx.term}")
    
    # Dynamic tab creation
    tab_list = ["⚙️ Timegrid Configuration", "📋 Subject Distribution"]
    
    if REGULAR_TT_AVAILABLE:
        tab_list.append("📊 Weekly Timetable")
    
    if ELECTIVE_TT_AVAILABLE:
        tab_list.append("🎓 Elective Timetable")
    
    if CONFLICTS_AVAILABLE:
        tab_list.append("🔍 Cross-TT Conflicts")
    
    tab_list.append("ℹ️ Help")
    
    tabs = st.tabs(tab_list)
    tab_idx = 0
    
    # Tab 1: Timegrid Configuration
    with tabs[tab_idx]:
        render_periods_config_tab(engine)
    tab_idx += 1
    
    # Tab 2: Subject Distribution
    with tabs[tab_idx]:
        if ctx:
            render_distribution_tab(ctx, engine)
        else:
            st.info("👈 Please select a context above.")
    tab_idx += 1
    
    # Tab 3: Weekly Timetable (if available)
    if REGULAR_TT_AVAILABLE:
        with tabs[tab_idx]:
            st.header("📊 Weekly Timetable (Regular Subjects)")
            
            if ctx:
                try:
                    context_dict = ctx.to_context_dict()
                    render_complete_excel_timetable(context_dict, engine)
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    with st.expander("🐛 Debug"):
                        st.exception(e)
            else:
                st.info("👈 Select context above")
        tab_idx += 1
    
    # Tab 4: Elective Timetable (if available)
    if ELECTIVE_TT_AVAILABLE:
        with tabs[tab_idx]:
            st.header("🎓 Elective Timetable")
            
            if ctx:
                try:
                    context_dict = ctx.to_context_dict()
                    render_elective_timetable(context_dict, engine)
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    with st.expander("🐛 Debug"):
                        st.exception(e)
            else:
                st.info("👈 Select context above")
        tab_idx += 1
    
    # Tab 5: Cross-TT Conflicts (if available)
    if CONFLICTS_AVAILABLE:
        with tabs[tab_idx]:
            st.header("🔍 Cross-Timetable Conflicts")
            
            if ctx:
                try:
                    context_dict = ctx.to_context_dict()
                    render_conflict_dashboard(context_dict, engine)
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    with st.expander("🐛 Debug"):
                        st.exception(e)
            else:
                st.info("👈 Select context above")
        tab_idx += 1
    
    # Help Tab
    with tabs[tab_idx]:
        st.markdown("### 📖 LPEP Timetable System")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Regular TT", "✅" if REGULAR_TT_AVAILABLE else "❌")
        col2.metric("🎓 Elective TT", "✅" if ELECTIVE_TT_AVAILABLE else "❌")
        col3.metric("🔍 Conflicts", "✅" if CONFLICTS_AVAILABLE else "❌")
        
        st.caption("LPEP v8.5.0 | Corrected Queries | Production Ready")

if __name__ == "__main__":
    main()
