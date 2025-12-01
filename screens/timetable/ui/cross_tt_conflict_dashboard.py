"""
Cross-TT Conflict Dashboard
Location: screens/timetable/ui/cross_tt_conflict_dashboard.py

Displays conflicts between:
- Regular TT (Slide 23) - timetable_slots
- Elective TT (Slide 24) - elective_timetable_slots
"""

import streamlit as st
from sqlalchemy.engine import Engine
from typing import Dict
import sys
import os

# Add services path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.join(os.path.dirname(current_dir), 'services')
sys.path.insert(0, services_dir)

try:
    from cross_tt_conflict_detector import (
        detect_all_cross_tt_conflicts, 
        export_cross_tt_conflicts_to_dict
    )
    CONFLICT_DETECTOR_AVAILABLE = True
except ImportError as e:
    CONFLICT_DETECTOR_AVAILABLE = False
    print(f"⚠️ cross_tt_conflict_detector import failed: {e}")


def render_conflict_dashboard(ctx: Dict, engine: Engine):
    """
    Render cross-TT conflict detection dashboard
    
    Args:
        ctx: Context dict with ay_label, degree_code, year, term, division_code
        engine: Database engine
    """
    
    st.subheader("🔍 Cross-Timetable Conflict Detection")
    st.caption("Detects conflicts between Regular TT (Slide 23) and Elective TT (Slide 24)")
    
    # Context display
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Degree", ctx['degree_code'])
    col2.metric("Year", ctx['year'])
    col3.metric("Term", ctx['term'])
    col4.metric("Division", ctx.get('division_code', 'ALL'))
    
    st.divider()
    
    # Check if conflict detector is available
    if not CONFLICT_DETECTOR_AVAILABLE:
        st.error("❌ Conflict detector module not found!")
        st.info("""
        Please ensure:
        1. File exists at: `screens/timetable/services/cross_tt_conflict_detector.py`
        2. Schema is installed: `python install_timetable_schemas.py`
        """)
        return
    
    # Scan button
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("""
        **What this checks:**
        - ✅ Faculty teaching in both TTs simultaneously
        - ✅ Students attending overlapping classes
        - ✅ Rooms double-booked
        - ✅ Date range overlaps for elective modules
        - ✅ All-day block conflicts
        """)
    
    with col2:
        scan_button = st.button(
            "🔍 Scan for Conflicts",
            type="primary",
            use_container_width=True
        )
    
    # Run scan
    if scan_button or st.session_state.get('show_conflicts', False):
        
        with st.spinner("🔍 Scanning both timetables for conflicts..."):
            
            try:
                conflicts = detect_all_cross_tt_conflicts(
                    ay_label=ctx['ay_label'],
                    term=ctx['term'],
                    degree_code=ctx['degree_code'],
                    year=ctx['year'],
                    division_code=ctx.get('division_code'),
                    engine=engine
                )
                
                st.session_state['conflicts'] = conflicts
                st.session_state['show_conflicts'] = True
                
            except Exception as e:
                st.error(f"❌ Error scanning for conflicts: {e}")
                st.exception(e)
                return
    
    # Display results
    if st.session_state.get('show_conflicts') and 'conflicts' in st.session_state:
        
        conflicts = st.session_state['conflicts']
        
        st.divider()
        
        # Summary metrics
        st.markdown("### 📊 Conflict Summary")
        
        col1, col2, col3 = st.columns(3)
        
        col1.metric(
            "❌ Critical Errors",
            conflicts['total_errors'],
            help="Blocking conflicts that MUST be resolved before publishing"
        )
        
        col2.metric(
            "⚠️ Warnings",
            conflicts['total_warnings'],
            help="Non-blocking conflicts (can override with approval)"
        )
        
        status_text = "🚫 BLOCKED" if conflicts['has_blocking_conflicts'] else "✅ CLEAR"
        status_delta = "Fix errors to proceed" if conflicts['has_blocking_conflicts'] else "Ready to publish"
        delta_color = "inverse" if conflicts['has_blocking_conflicts'] else "normal"
        
        col3.metric(
            "Publishing Status",
            status_text,
            delta=status_delta,
            delta_color=delta_color
        )
        
        st.divider()
        
        # ========================================
        # FACULTY CONFLICTS
        # ========================================
        if conflicts['faculty_conflicts']:
            st.markdown("### 👨‍🏫 Faculty Conflicts")
            st.caption(f"{len(conflicts['faculty_conflicts'])} conflict(s) found")
            
            for idx, c in enumerate(conflicts['faculty_conflicts'], 1):
                with st.expander(
                    f"❌ #{idx}: {c['faculty_name']} - {c['day_of_week']} Period {c['period_id']}",
                    expanded=(idx <= 3)  # Auto-expand first 3
                ):
                    # Show conflict details side-by-side
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**📊 Regular TT (Slide 23)**")
                        st.info(c['regular_subject'])
                        if c.get('regular_room'):
                            st.caption(f"🏛️ Room: {c['regular_room']}")
                    
                    with col2:
                        st.markdown("**🎓 Elective TT (Slide 24)**")
                        st.warning(c['elective_topic'])
                        st.caption(f"📅 Dates: {c['elective_dates']}")
                        
                        if c.get('is_all_day'):
                            st.caption("† All-day block")
                        
                        if c.get('elective_room'):
                            st.caption(f"🏛️ Room: {c['elective_room']}")
                    
                    # Show conflict message
                    st.error(c['message'])
                    
                    # Suggested actions
                    st.markdown("**💡 Suggested Actions:**")
                    st.markdown("""
                    1. Reassign faculty in Elective TT to different time slot
                    2. Change elective timing to avoid overlap
                    3. Use different faculty for elective topic
                    """)
        
        # ========================================
        # STUDENT CONFLICTS
        # ========================================
        if conflicts['student_conflicts']:
            st.markdown("### 🎓 Student Conflicts")
            st.caption(f"{len(conflicts['student_conflicts'])} conflict(s) found")
            
            for idx, c in enumerate(conflicts['student_conflicts'], 1):
                with st.expander(
                    f"❌ #{idx}: Division {c['division']} - {c['day_of_week']} Period {c['period_id']}",
                    expanded=(idx <= 3)
                ):
                    # Show student count affected
                    st.metric(
                        "Students Affected",
                        c['students_affected'],
                        help="Number of students with overlapping classes"
                    )
                    
                    # Show conflict details
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Regular TT Class**")
                        st.info(c['regular_subject'])
                    
                    with col2:
                        st.markdown("**Elective TT Class**")
                        st.warning(c['elective_topic'])
                    
                    st.error(c['message'])
                    
                    # Suggested actions
                    st.markdown("**💡 Suggested Actions:**")
                    st.markdown("""
                    1. Reschedule elective to different time slot
                    2. Make regular class optional for students in elective
                    3. Split elective into multiple sections at different times
                    """)
        
        # ========================================
        # ROOM CONFLICTS
        # ========================================
        if conflicts['room_conflicts']:
            st.markdown("### 🏛️ Room Conflicts")
            st.caption(f"{len(conflicts['room_conflicts'])} conflict(s) found")
            
            for idx, c in enumerate(conflicts['room_conflicts'], 1):
                with st.expander(
                    f"⚠️ #{idx}: Room {c['room_code']} - {c['day_of_week']} Period {c['period_id']}"
                ):
                    # Show room bookings
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Regular TT Booking**")
                        st.info(c['regular_subject'])
                    
                    with col2:
                        st.markdown("**Elective TT Booking**")
                        st.warning(c['elective_topic'])
                    
                    st.warning(c['message'])
                    
                    # Suggested actions
                    st.markdown("**💡 Suggested Actions:**")
                    st.markdown("""
                    1. Assign different room to elective
                    2. Use online/virtual mode for one class
                    3. Coordinate with admin for larger room that fits both
                    """)
        
        # ========================================
        # NO CONFLICTS
        # ========================================
        if not any([
            conflicts['faculty_conflicts'],
            conflicts['student_conflicts'],
            conflicts['room_conflicts']
        ]):
            st.success("✅ No conflicts detected!")
            st.info("Both Regular TT and Elective TT are compatible. Safe to publish.")
            st.balloons()
        
        # ========================================
        # ACTIONS
        # ========================================
        st.divider()
        st.markdown("### 🔧 Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Re-scan", use_container_width=True):
                st.session_state['show_conflicts'] = False
                st.rerun()
        
        with col2:
            if st.button("📥 Export Report", use_container_width=True):
                st.info("💡 Export functionality coming in next update")
        
        with col3:
            if st.button("❌ Clear Results", use_container_width=True):
                st.session_state.pop('conflicts', None)
                st.session_state['show_conflicts'] = False
                st.rerun()
    
    else:
        # Initial state - no scan yet
        st.info("👆 Click 'Scan for Conflicts' button above to check for conflicts")
        
        # Show example conflict types
        with st.expander("ℹ️ What kinds of conflicts are detected?"):
            st.markdown("""
            ### Conflict Types
            
            **1. Faculty Conflicts ❌ (Critical)**
            - Faculty teaching in Regular TT and Elective TT at same time
            - Checks date range overlaps for elective modules
            - Example: Dr. Smith teaches TOS1 Mon P1 AND ML Elective Mon P1 (Oct 1-31)
            
            **2. Student Conflicts ❌ (Critical)**
            - Students attending Regular class and Elective class simultaneously
            - Checks division assignments and student selections
            - Example: Div A has TOS1 Mon P1 AND students selected ML Elective Mon P1
            
            **3. Room Conflicts ⚠️ (Warning)**
            - Same room booked for Regular TT and Elective TT
            - Can usually be resolved by reassigning room
            - Example: Lab 101 booked for TOS1 practicals AND ML hands-on
            
            **4. All-Day Block Conflicts ❌ (Critical)**
            - All-day elective blocks conflicting with regular classes
            - Spans entire day (P1-P8)
            - Example: All-day workshop scheduled when regular classes exist
            
            **5. Date Range Overlaps ❌ (Critical)**
            - Elective module dates overlapping with regular term dates
            - Only checks when elective has specific date ranges
            - Example: Module runs Oct 1-31, conflicts with term-wide regular classes
            """)


# Export for use in app_weekly_planner
__all__ = ['render_conflict_dashboard']
