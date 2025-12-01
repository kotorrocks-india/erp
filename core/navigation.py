# app/core/navigation.py
from dataclasses import dataclass
from typing import List, Set
import streamlit as st

# Existing navigation functions
def navigate_to_login():
    """Navigate to login page"""
    st.session_state["show_login"] = True
    st.rerun()

def navigate_to_logout():
    """Navigate to logout page"""
    st.session_state["show_logout"] = True
    st.rerun()

def navigate_to_app():
    """Navigate to main app"""
    if "show_login" in st.session_state:
        del st.session_state["show_login"]
    if "show_logout" in st.session_state:
        del st.session_state["show_logout"]
    st.rerun()


# New collapsible navigation functionality
@dataclass
class NavSection:
    """Represents a collapsible navigation section"""
    key: str
    title: str
    icon: str
    pages: List[tuple]  # List of (policy_name, route_stem, title)

# Define your navigation structure
NAV_SECTIONS = [
    NavSection(
        key="core_config",
        title="Core Configuration",
        icon="⚙️",
        pages=[
            ("Profile", "profile", "👤 Profile"),
            ("Users & Roles", "users_roles", "👥 Users & Roles"),
            ("Branding (Login)", "branding", "🎨 Branding (Login)"),
            ("Appearance / Theme", "appearance_theme", "🎛️ Appearance / Theme"),
            ("Footer", "footer", "🦶 Footer"),
            ("Office Admins", "office_admin", "📋 Office Admin"),
        ]
    ),
    NavSection(
        key="academic_structure",
        title="Academic Structure",
        icon="🏛️",
        pages=[
            ("Degrees", "degrees", "🎓 Degrees"),
            ("Programs / Branches", "programs_branches", "📚 Programs / Branches"),
            ("Semesters", "semesters", "📅 Semesters"),
            ("Academic Years", "academic_years", "🗓️ Academic Years"),
            ("Electives Policy", "electives_policy_admin", "⚙️ Electives Policy"),
        ]
    ),
    NavSection(
        key="faculty_students",
        title="Faculty & Students",
        icon="👥",
        pages=[
            ("Faculty", "faculty", "👨‍🏫 Faculty"),
            ("Students", "students", "🎓 Students"),
            ("Class-in-Charge Assignments", "class_in_charge", "📚 Class in Charge"),
        ]
    ),
    NavSection(
        key="curriculum_planning",
        title="Curriculum & Planning",
        icon="📋",
        pages=[
            ("Outcomes", "outcomes", "📌 Program Outcomes (PEO/PO/PSO)"),
            ("Subjects Catalog", "subjects_catalog", "📘 Subjects Catalog"),
            ("Electives & College Projects", "electives_topics", "🎯 Electives & College Projects"),
            ("Subjects Offerings", "subject_offerings", "🏫 Subjects AY Offerings"),
            ("Subject COs Rubrics", "subject_cos_rubrics", "📖 Subject COs & Rubrics"),
            ("Weekly Timetable", "weekly_timetable", "📅 Weekly Timetable"),
        ]
    ),
    NavSection(
        key="approvals",
        title="Approvals & Management",
        icon="✅",
        pages=[
            ("Approvals", "approvals", "📬 Approvals"),
            ("Approval Management", "approval_management", "⚙️ Approval Management"),
        ]
    ),
]

def initialize_nav_state():
    """Initialize navigation state in session_state"""
    if "nav_expanded_sections" not in st.session_state:
        # Start with first section expanded by default
        st.session_state.nav_expanded_sections = {"core_config"}
    
    if "nav_current_page" not in st.session_state:
        st.session_state.nav_current_page = "profile"

def toggle_section(section_key: str):
    """Toggle a section's expanded state"""
    if section_key in st.session_state.nav_expanded_sections:
        st.session_state.nav_expanded_sections.remove(section_key)
    else:
        st.session_state.nav_expanded_sections.add(section_key)

def is_section_expanded(section_key: str) -> bool:
    """Check if a section is expanded"""
    return section_key in st.session_state.nav_expanded_sections

def set_current_page(route_stem: str):
    """Set the current page"""
    st.session_state.nav_current_page = route_stem

def get_current_page() -> str:
    """Get the current page route"""
    return st.session_state.get("nav_current_page", "profile")

def render_collapsible_nav(roles: Set[str], can_view_page_fn, add_page_fn, pages_out: list, missing_out: list):
    """
    Render collapsible navigation sections - only builds the pages list.
    The actual sidebar rendering is handled by Streamlit's st.navigation().
    
    Args:
        roles: User's roles
        can_view_page_fn: Function to check if user can view a page
        add_page_fn: Function to add a page to the navigation
        pages_out: List to collect valid pages
        missing_out: List to collect missing pages
    """
    initialize_nav_state()
    
    # Just build the pages list organized by sections
    for section in NAV_SECTIONS:
        # Check if any page in this section is accessible
        accessible_pages = [
            page for page in section.pages 
            if can_view_page_fn(page[0], roles)
        ]
        
        if not accessible_pages:
            continue  # Skip sections with no accessible pages
        
        # Add all accessible pages in this section
        for policy_name, route_stem, page_title in accessible_pages:
            # Add the page to the pages list
            add_page_fn(policy_name, route_stem, page_title, roles, pages_out, missing_out)
