# screens/academic_years/main.py - SIMPLIFIED VERSION
from __future__ import annotations

import traceback
import streamlit as st
from sqlalchemy import text as sa_text

# --- Core imports ---
try:
    from core.settings import load_settings
    from core.db import get_engine
    from core.rbac import user_roles
except Exception as e:
    st.error(f"Startup import failed: {e}")
    st.code(traceback.format_exc())
    st.stop()

# --- Schema import ---
try:
    from screens.academic_years.schema import install_all as install_academic_years_schema
except Exception as e:
    st.error(f"Schema import failed: {e}")
    st.code(traceback.format_exc())
    st.stop()

# --- UI imports ---
try:
    from screens.academic_years.ui import (
        render_ay_list,
        render_ay_editor,
        render_ay_status_changer,
    )
    #from screens.academic_years.simple_term_dates import render_simple_term_dates
    #from screens.academic_years.term_preview import render_term_preview
    # With these:
    from screens.academic_years.enhanced_term_dates import render_enhanced_term_dates
    from screens.academic_years.enhanced_term_preview import render_enhanced_term_preview

    
except Exception as e:
    st.error(f"UI import failed: {e}")
    st.code(traceback.format_exc())
    st.stop()

PAGE_TITLE = "🎓 Academic Years & Term Dates"


def _get_engine_roles_email():
    """Create engine and derive roles/email for this session."""
    settings = load_settings()
    engine = get_engine(settings.db.url)
    user = st.session_state.get("user") or {}
    email = user.get("email") or "anonymous"
    roles = user_roles(engine, email) if email != "anonymous" else set()
    return engine, roles, email


def _degrees_exist(engine) -> bool:
    """Return True if there is at least one active degree."""
    try:
        with engine.connect() as conn:
            row = conn.execute(sa_text("SELECT 1 FROM degrees WHERE active=1 LIMIT 1")).fetchone()
            return row is not None
    except Exception:
        return False


def render():
    """Main render function - SIMPLIFIED with only essential tabs."""
    st.title(PAGE_TITLE)

    # Init engine/roles/email
    try:
        engine, roles, email = _get_engine_roles_email()
    except Exception as e:
        st.error(f"Initialization failed: {e}")
        st.code(traceback.format_exc())
        st.stop()

    # Ensure database tables are installed
    try:
        install_academic_years_schema(engine)
    except Exception as e:
        st.error(f"Database schema installation failed: {e}")
        st.code(traceback.format_exc())
        st.stop()

    # Create tabs - SIMPLIFIED (removed Calendar Profiles and Assignment Editor)
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 AY List",
        "✏️ AY Editor",
        "🔄 AY Status",
        "📅 Term Dates Editor",
        "📊 Term Preview",
    ])

    # Render each tab with proper error handling
    with tab1:
        try:
            render_ay_list(engine)
        except Exception as e:
            st.error(f"AY List failed: {e}")
            st.code(traceback.format_exc())

    with tab2:
        try:
            render_ay_editor(engine, roles, email)
        except Exception as e:
            st.error(f"AY Editor failed: {e}")
            st.code(traceback.format_exc())

    with tab3:
        try:
            render_ay_status_changer(engine, roles, email)
        except Exception as e:
            st.error(f"AY Status failed: {e}")
            st.code(traceback.format_exc())

    with tab4:
        try:
            # CHANGED: Use enhanced editor
            render_enhanced_term_dates(engine, roles, email)
        except Exception as e:
            st.error(f"Term Dates Editor failed: {e}")
            st.code(traceback.format_exc())
    
    with tab5:
        try:
            if not _degrees_exist(engine):
                st.warning("No active Degrees found.")
            else:
                # CHANGED: Use enhanced preview
                render_enhanced_term_preview(engine, roles, email)
        except Exception as e:
            st.error(f"Term Preview failed: {e}")
            st.code(traceback.format_exc())

if __name__ == "__main__":
    render()
