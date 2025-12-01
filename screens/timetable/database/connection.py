"""
Database Connection Utilities
"""

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    """
    Get database engine.
    
    Uses Streamlit session state for caching.
    Modify the connection string as needed for your setup.
    """
    if 'engine' not in st.session_state:
        # Try to import from existing database module
        try:
            from database import get_engine as db_get_engine
            st.session_state['engine'] = db_get_engine()
        except ImportError:
            # Fallback: create from configuration
            # TODO: Update with your actual database path
            db_path = "lpep.db"  # Update this
            connection_string = f"sqlite:///{db_path}"
            
            st.session_state['engine'] = create_engine(
                connection_string,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True  # Verify connections before using
            )
    
    return st.session_state['engine']


def test_connection() -> bool:
    """Test database connection"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return False


def get_table_names() -> list:
    """Get list of all tables in database"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            return [row[0] for row in result]
    except:
        return []


def verify_schema() -> tuple[bool, list]:
    """
    Verify required tables exist.
    
    Returns: (all_present, missing_tables)
    """
    required_tables = [
        'faculty_profiles',
        'faculty_affiliations',
        'affiliation_types',
        'subject_offerings',
        'weekly_subject_distribution',
        'normalized_weekly_assignment',
        'degrees',
        'programs',
        'branches',
        'academic_years',
    ]
    
    existing_tables = {t.lower() for t in get_table_names()}
    missing = [t for t in required_tables if t.lower() not in existing_tables]
    
    return len(missing) == 0, missing
