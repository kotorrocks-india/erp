"""
Elective Timetable Excel-Style Grid (Slide 24)
Location: screens/timetable/ui/elective_timetable_excel.py

Features:
- Topic-based (not subject-based)
- Module support with date ranges
- All-day blocks (†)
- Live capacity tracking
- Separate from regular TT
"""

import streamlit as st
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Dict, List, Optional
import pandas as pd
from datetime import date


def render_elective_timetable(ctx: Dict, engine: Engine):
    """
    Render elective timetable grid
    
    Args:
        ctx: Context dict with ay_label, degree_code, year, term, division_code
        engine: Database engine
    """
    
    st.subheader("🎓 Elective / College Project Timetable")
    
    # Context display
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Degree", ctx['degree_code'])
    col2.metric("Year", ctx['year'])
    col3.metric("Term", ctx['term'])
    col4.metric("Division", ctx.get('division_code', 'ALL'))
    
    st.divider()
    
    # Mode selection
    mode = st.radio(
        "Mode",
        ["👁️ View Only", "✏️ Edit Mode"],
        horizontal=True,
        key="elective_grid_mode"
    )
    
    # Get elective topics for this context
    topics = get_elective_topics(ctx, engine)
    
    if not topics:
        st.warning("⚠️ No elective topics found for this context.")
        st.info("💡 Please create topics in the Subject Distribution tab first.")
        
        # Show sample structure
        with st.expander("ℹ️ How to create elective topics"):
            st.markdown("""
            **Steps to create elective topics:**
            
            1. Go to **Tab 2: Subject Distribution**
            2. Select the same context (AY, Degree, Year, Term)
            3. Look for "Elective Topics" section
            4. Click "Add New Topic"
            5. Fill in:
               - Topic Code (e.g., ML-01)
               - Topic Name (e.g., "Machine Learning Applications")
               - Owner Faculty
               - Capacity (e.g., 100 students)
            6. Optionally add modules with date ranges
            7. Save and return here
            """)
        return
    
    st.success(f"📚 {len(topics)} elective topic(s) available")
    
    # Topic filter
    topic_options = ["All Topics"] + [
        f"{t['topic_code_ay']}: {t['topic_name']}" 
        for t in topics
    ]
    
    selected_topic = st.selectbox(
        "Filter by Topic (optional)",
        topic_options,
        key="elective_topic_filter"
    )
    
    st.divider()
    
    # Render based on mode
    if mode == "✏️ Edit Mode":
        st.warning("🔧 Edit mode - Create and modify elective timetable slots")
        render_elective_grid_edit(ctx, engine, topics, selected_topic)
    else:
        render_elective_grid_view(ctx, engine, topics, selected_topic)


def get_elective_topics(ctx: Dict, engine: Engine) -> List[Dict]:
    """
    Get elective topics for the given context
    
    Returns:
        List of topic dictionaries
    """
    
    with engine.connect() as conn:
        
        # Check if elective_topics table exists
        check = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='elective_topics'
        """)).fetchone()
        
        if not check:
            return []
        
        # Get topics
        result = conn.execute(text("""
            SELECT 
                id, 
                topic_code_ay, 
                topic_name, 
                owner_faculty_email, 
                capacity,
                subject_code,
                status
            FROM elective_topics
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND year = :year
              AND term = :term
              AND status != 'deleted'
            ORDER BY topic_code_ay
        """), {
            'ay': ctx['ay_label'],
            'deg': ctx['degree_code'],
            'year': ctx['year'],
            'term': ctx['term']
        })
        
        return [dict(row._mapping) for row in result.fetchall()]


def render_elective_grid_view(
    ctx: Dict, 
    engine: Engine, 
    topics: List[Dict], 
    filter_topic: str
):
    """Render view-only elective timetable grid"""
    
    st.info("📊 Viewing published elective timetable")
    
    # Check if elective_timetable_slots table exists
    with engine.connect() as conn:
        check = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='elective_timetable_slots'
        """)).fetchone()
        
        if not check:
            st.warning("⚠️ Elective timetable table not found.")
            st.info("""
            💡 Run the schema installer first:
            ```bash
            python install_timetable_schemas.py
            ```
            """)
            return
        
        # Fetch slots
        slots_query = text("""
            SELECT 
                s.*,
                t.topic_name,
                t.capacity as topic_capacity,
                (SELECT COUNT(*) FROM elective_student_selections 
                 WHERE topic_id = s.topic_id AND status = 'confirmed') as current_enrollment
            FROM elective_timetable_slots s
            LEFT JOIN elective_topics t ON t.id = s.topic_id
            WHERE s.ay_label = :ay
              AND s.degree_code = :deg
              AND s.year = :year
              AND s.term = :term
              AND s.status = 'published'
            ORDER BY 
                CASE s.day_of_week
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                END,
                s.period_id
        """)
        
        slots = conn.execute(slots_query, {
            'ay': ctx['ay_label'],
            'deg': ctx['degree_code'],
            'year': ctx['year'],
            'term': ctx['term']
        }).fetchall()
    
    if not slots:
        st.info("📝 No elective timetable slots created yet.")
        st.info("💡 Switch to Edit Mode to create your first elective schedule.")
        return
    
    # Display slots in table format
    df_data = []
    for slot in slots:
        
        # Faculty name (extract from email)
        faculty = slot.faculty_in_charge or 'TBD'
        if '@' in faculty:
            faculty = faculty.split('@')[0].replace('.', ' ').title()
        
        # Capacity display
        capacity_str = 'Unlimited'
        if slot.topic_capacity:
            capacity_str = f"{slot.current_enrollment}/{slot.topic_capacity}"
            
            # Color indicator
            fill_pct = (slot.current_enrollment / slot.topic_capacity * 100) if slot.topic_capacity else 0
            if fill_pct >= 100:
                capacity_str += " 🔴"  # Full
            elif fill_pct >= 80:
                capacity_str += " 🟡"  # Almost full
            else:
                capacity_str += " 🟢"  # Available
        
        # Date range
        dates = 'Full term'
        if slot.start_date and slot.end_date:
            dates = f"{slot.start_date} to {slot.end_date}"
        
        # All-day indicator
        all_day = '✓ All-day †' if slot.is_all_day_block else ''
        
        df_data.append({
            'Day': slot.day_of_week,
            'Period': f"P{slot.period_id}",
            'Topic': slot.topic_name or slot.topic_code_ay,
            'Faculty': faculty,
            'Room': slot.room_code or 'TBD',
            'Capacity': capacity_str,
            'All-Day': all_day,
            'Dates': dates,
            'Module': slot.module_code or '-'
        })
    
    if df_data:
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Export options
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Export to Excel", key="export_elective_excel"):
                st.info("💡 Excel export coming in next update")
        
        with col2:
            if st.button("📄 Export to PDF", key="export_elective_pdf"):
                st.info("💡 PDF export coming in next update")
    else:
        st.info("No slots to display")


def render_elective_grid_edit(
    ctx: Dict, 
    engine: Engine, 
    topics: List[Dict], 
    filter_topic: str
):
    """Render editable elective timetable grid"""
    
    st.info("✏️ Edit Mode - Create and modify elective timetable slots")
    
    # Check if table exists
    with engine.connect() as conn:
        check = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='elective_timetable_slots'
        """)).fetchone()
        
        if not check:
            st.error("❌ Elective timetable table not found!")
            st.info("""
            Please run the schema installer first:
            ```bash
            python install_timetable_schemas.py
            ```
            """)
            return
    
    # Show available topics
    st.markdown("### 📚 Available Topics")
    
    for topic in topics[:5]:  # Show first 5
        with st.expander(f"{topic['topic_code_ay']}: {topic['topic_name']}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Owner:** {topic['owner_faculty_email']}")
                st.write(f"**Capacity:** {topic['capacity'] or 'Unlimited'}")
            
            with col2:
                st.write(f"**Subject:** {topic['subject_code']}")
                st.write(f"**Status:** {topic['status']}")
    
    if len(topics) > 5:
        st.caption(f"... and {len(topics) - 5} more topics")
    
    st.divider()
    
    # Quick create form
    st.markdown("### ➕ Quick Create Slot")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        topic_choice = st.selectbox(
            "Topic",
            [f"{t['topic_code_ay']}: {t['topic_name']}" for t in topics],
            key="quick_create_topic"
        )
    
    with col2:
        day = st.selectbox(
            "Day",
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            key="quick_create_day"
        )
    
    with col3:
        period = st.number_input(
            "Period",
            min_value=1,
            max_value=8,
            value=1,
            key="quick_create_period"
        )
    
    # All-day toggle
    is_all_day = st.checkbox("All-day block (spans entire day)", key="quick_create_all_day")
    
    if st.button("➕ Create Slot", type="primary"):
        st.warning("⚠️ Full create functionality coming in next update")
        st.info("""
        This will:
        1. Check for conflicts with Regular TT
        2. Validate faculty availability
        3. Create the slot in database
        4. Update capacity tracking
        """)
    
    st.divider()
    
    # Show current slots in edit mode
    st.markdown("### 📊 Current Slots (Draft)")
    render_elective_grid_view(ctx, engine, topics, filter_topic)


# Export for use in app_weekly_planner
__all__ = ['render_elective_timetable']
