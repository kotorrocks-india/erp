"""
Weekly Timetable - Main Application Integration
This file bridges the modular timetable package with the main LPEP application.
"""

import streamlit as st
import sys
from pathlib import Path
import uuid

# Add timetable module to Python path
TIMETABLE_PATH = Path(__file__).parent / "timetable"
if str(TIMETABLE_PATH) not in sys.path:
    sys.path.insert(0, str(TIMETABLE_PATH))


def render_timetable_screen():
    """
    Main render function for the timetable screen.
    Uses a container to isolate rendering.
    """
    # Create a unique container for this screen
    with st.container():
        try:
            from app_weekly_planner import main as run_timetable_app
            
            # Generate a truly unique key prefix using session + timestamp
            if 'timetable_key_base' not in st.session_state:
                import time
                st.session_state['timetable_key_base'] = f"tt_{uuid.uuid4().hex[:8]}_{int(time.time())}"
            
            key_prefix = st.session_state['timetable_key_base']
            
            # Clear the key on any interaction to force regeneration
            if st.session_state.get('_clear_timetable_keys', False):
                if 'timetable_key_base' in st.session_state:
                    del st.session_state['timetable_key_base']
                st.session_state['_clear_timetable_keys'] = False
                st.rerun()
            
            # Run the timetable application
            run_timetable_app(key_prefix=key_prefix)
            
        except ImportError as e:
            st.error(f"""
            ⚠️ **Timetable Module Not Found**
            
            The modular timetable package is not properly installed.
            
            **Error:** {str(e)}
            
            **Expected location:** `screens/timetable/`
            """)
            st.stop()
        
        except Exception as e:
            st.error(f"""
            ⚠️ **Timetable Module Error**
            
            **Error:** {str(e)}
            """)
            
            with st.expander("🔍 View Full Error Traceback"):
                import traceback
                st.code(traceback.format_exc())
            
            # Add a reset button
            if st.button("🔄 Reset Timetable Screen"):
                # Clear all timetable-related session state
                keys_to_clear = [k for k in st.session_state.keys() if 'timetable' in k.lower() or 'tt_' in k]
                for key in keys_to_clear:
                    try:
                        del st.session_state[key]
                    except:
                        pass
                st.rerun()
            
            st.stop()


# Export the main function
timetable_main = render_timetable_screen

# Only auto-run if executed directly
if __name__ == "__main__":
    render_timetable_screen()
