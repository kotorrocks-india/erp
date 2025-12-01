"""
Periods Configuration Page - CORRECTED IMPORTS
Integrates periods_config_ui.py and periods_config_ui_part2.py
All files should be in: screens/timetable/ui/
"""

import streamlit as st
from sqlalchemy.engine import Engine

# CORRECTED: Import from same directory (not from ui.*)
# All these files are in screens/timetable/ui/ together
try:
    from periods_config_ui import PeriodsDataService, PeriodKindsManager, TemplateSelector
    from periods_config_ui_part2 import DayStructureBuilder, WeekdayOverridesManager, PreviewSummary
    PERIODS_MODULES_AVAILABLE = True
except ImportError as e:
    PERIODS_MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)

class PeriodsConfigPage:
    """
    Main page for configuring Timegrids/Periods.
    Combines all sub-components into a tabbed interface.
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine
        if PERIODS_MODULES_AVAILABLE:
            self.service = PeriodsDataService(engine)
        else:
            self.service = None

    def render(self):
        if not PERIODS_MODULES_AVAILABLE:
            st.error("❌ Periods configuration modules not found")
            st.info("""
            **Missing Files:**
            
            Please ensure these files exist in `screens/timetable/ui/`:
            1. `periods_config_ui.py` (Part 1)
            2. `periods_config_ui_part2.py` (Part 2)
            
            Both files should be in the same directory as this file.
            """)
            
            with st.expander("🐛 Debug Info"):
                st.code(f"Import Error: {IMPORT_ERROR}")
            
            return
        
        st.subheader("⚙️ Timegrid & Periods Configuration")
        
        # 1. Period Kinds (Global)
        with st.expander("🎨 Manage Period Types (Lecture, Break, etc.)", expanded=False):
            PeriodKindsManager(self.service).render()

        st.divider()

        # 2. Template Selection (Context)
        st.info("Select a template below to edit its structure.")
        
        # TemplateSelector returns the ID of the template user clicked 'Edit' on
        active_template_id = TemplateSelector(self.service, self.engine).render()

        # If a template is selected, persist it in session state
        if active_template_id:
            st.session_state['active_config_template_id'] = active_template_id
        
        current_id = st.session_state.get('active_config_template_id')

        if current_id:
            st.markdown("---")
            st.markdown("### 🗓️ Template Structure Editor")
            
            tab1, tab2, tab3 = st.tabs([
                "1. Day Structure", 
                "2. Weekday Overrides", 
                "3. Preview & Validate"
            ])
            
            with tab1:
                DayStructureBuilder(self.service, current_id).render()
                
            with tab2:
                WeekdayOverridesManager(self.service, current_id).render()
                
            with tab3:
                PreviewSummary(self.service, current_id).render()
        else:
            st.caption("👆 Select or Create a template above to start building the grid.")
