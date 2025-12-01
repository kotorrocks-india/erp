"""
Timetable Tab - Integrated with Periods Configuration - FIXED VERSION
Now with working dropdown menus instead of placeholder + buttons
"""

import streamlit as st
import pandas as pd
import json
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional, Dict, List

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_MAP = {d: i + 1 for i, d in enumerate(DAYS)}


class TimetableTabIntegrated:
    """Timetable Grid Tab with Periods Integration and Working Dropdowns"""
    
    def __init__(self, ctx, engine: Engine):
        self.ctx = ctx
        self.engine = engine
        self._ensure_assignment_table()
    
    def _ensure_assignment_table(self):
        """Creates normalized_weekly_assignment table if missing"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS normalized_weekly_assignment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ay_label TEXT,
                    degree_code TEXT,
                    program_code TEXT,
                    branch_code TEXT,
                    year INTEGER,
                    term INTEGER,
                    division_code TEXT,
                    offering_id INTEGER,
                    subject_code TEXT,
                    subject_type TEXT,
                    day_of_week INTEGER,
                    period_index INTEGER,
                    faculty_ids TEXT,
                    room_code TEXT,
                    is_override_in_charge INTEGER DEFAULT 0,
                    is_all_day_block INTEGER DEFAULT 0,
                    module_start_date DATE,
                    module_end_date DATE,
                    week_start INTEGER,
                    week_end INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
    
    def render(self):
        """Render timetable grid"""
        st.header("🗓️ Weekly Timetable Grid")
        st.caption("Assign subjects to specific day/period slots using dropdown menus")
        
        # Fetch published template
        template = self._fetch_published_template()
        
        if not template:
            st.warning("⚠️ No published timegrid template found for this context")
            self._render_no_template_guidance()
            return
        
        # Show template info
        with st.expander(f"✅ Using Template: {template['template_name']}", expanded=False):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Code", template['template_code'])
            with col2:
                st.metric("Teaching Slots", template.get('teaching_slot_count', 'N/A'))
            with col3:
                st.metric("Total Minutes", template.get('total_teaching_minutes', 'N/A'))
            with col4:
                published_by = template.get('published_by', 'Unknown')
                st.caption(f"Published by: {published_by}")
        
        st.divider()
        
        # Fetch template slots and assignments
        template_slots = self._fetch_template_slots(template['id'])
        overrides = self._fetch_overrides(template['id'])
        assignments = self._fetch_assignments()
        
        # Build override map
        override_map = self._build_override_map(overrides)
        
        # Render grid
        self._render_grid(template_slots, override_map, assignments)
    
    def _fetch_published_template(self) -> Optional[Dict]:
        """Fetch published template for current context"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    t.id,
                    t.template_code,
                    t.template_name,
                    t.count_mode,
                    t.published_by,
                    (SELECT COUNT(*) FROM day_template_slots s 
                     WHERE s.template_id = t.id AND s.is_teaching_slot = 1) as teaching_slot_count,
                    (SELECT COALESCE(SUM(duration_min),0) FROM day_template_slots s 
                     WHERE s.template_id = t.id AND s.is_teaching_slot = 1) as total_teaching_minutes
                FROM day_templates t
                WHERE t.status = 'published'
                  AND t.ay_code = :ay
                  AND t.degree_code = :degree
                  AND (t.program_code = :program OR t.program_code IS NULL)
                  AND t.term_number = :term
                ORDER BY t.published_at DESC
                LIMIT 1
            """), {
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'program': self.ctx.program,
                'term': self.ctx.term
            })
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    
    def _fetch_template_slots(self, template_id: int) -> pd.DataFrame:
        """Fetch slots for a template"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT 
                    slot_index,
                    slot_label,
                    duration_min,
                    fixed_start_time,
                    fixed_end_time,
                    is_teaching_slot,
                    period_kind_id
                FROM day_template_slots
                WHERE template_id = :tid
                ORDER BY slot_index
            """), conn, params={'tid': template_id})
    
    def _fetch_overrides(self, template_id: int) -> pd.DataFrame:
        """Fetch weekday overrides"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT 
                    weekday_name,
                    override_slots_json
                FROM day_template_weekday_overrides
                WHERE template_id = :tid
            """), conn, params={'tid': template_id})
    
    def _fetch_assignments(self) -> pd.DataFrame:
        """Fetch current assignments"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT *
                FROM normalized_weekly_assignment
                WHERE ay_label = :ay
                  AND degree_code = :degree
                  AND (program_code = :program OR program_code IS NULL)
                  AND year = :year
                  AND term = :term
            """), conn, params={
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'program': self.ctx.program,
                'year': self.ctx.year,
                'term': self.ctx.term
            })
    
    def _build_override_map(self, overrides: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Build map of day -> override slots"""
        override_map = {}
        for _, row in overrides.iterrows():
            day = row['weekday_name']
            slots_json = row['override_slots_json']
            if slots_json:
                slots = json.loads(slots_json)
                override_map[day] = pd.DataFrame(slots)
        return override_map
    
    def _get_available_subjects(self) -> pd.DataFrame:
        """Get subjects available for assignment from weekly_subject_distribution"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT DISTINCT
                    wsd.subject_code,
                    wsd.division_code,
                    wsd.subject_type,
                    cs.subject_name,
                    wsd.subject_code || ' - ' || cs.subject_name as display_name
                FROM weekly_subject_distribution wsd
                LEFT JOIN comprehensive_subjects cs ON wsd.subject_code = cs.subject_code
                WHERE wsd.ay_label = :ay
                  AND wsd.degree_code = :degree
                  AND (wsd.program_code = :program OR wsd.program_code IS NULL)
                  AND wsd.year = :year
                  AND wsd.term = :term
                ORDER BY wsd.subject_code
            """), conn, params={
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'program': self.ctx.program,
                'year': self.ctx.year,
                'term': self.ctx.term
            })
    
    def _get_faculty_for_subject(self, subject_code: str, division_code: str) -> List[Dict]:
        """Get faculty from weekly_subject_distribution"""
        with self.engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT DISTINCT faculty_id, faculty_name
                FROM weekly_subject_distribution
                WHERE subject_code = :subj
                  AND division_code = :div
                  AND ay_label = :ay
                  AND degree_code = :degree
                  AND year = :year
                  AND term = :term
                  AND faculty_id IS NOT NULL
                ORDER BY faculty_name
            """), conn, params={
                'subj': subject_code,
                'div': division_code,
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'year': self.ctx.year,
                'term': self.ctx.term
            })
            return df.to_dict('records')
    
    def _save_assignment(self, day_num: int, period_idx: int, subject_code: str, 
                        division_code: str, faculty_ids: str, subject_type: str):
        """Save or update assignment"""
        with self.engine.begin() as conn:
            # Check if exists
            existing = conn.execute(text("""
                SELECT id FROM normalized_weekly_assignment
                WHERE ay_label = :ay AND degree_code = :degree
                AND year = :year AND term = :term
                AND day_of_week = :day AND period_index = :per
                AND division_code = :div
            """), {
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'year': self.ctx.year,
                'term': self.ctx.term,
                'day': day_num,
                'per': period_idx,
                'div': division_code
            }).fetchone()
            
            if existing:
                # Update
                conn.execute(text("""
                    UPDATE normalized_weekly_assignment
                    SET subject_code = :subj,
                        subject_type = :type,
                        faculty_ids = :fac
                    WHERE id = :id
                """), {
                    'subj': subject_code,
                    'type': subject_type,
                    'fac': faculty_ids,
                    'id': existing[0]
                })
            else:
                # Insert
                conn.execute(text("""
                    INSERT INTO normalized_weekly_assignment
                    (ay_label, degree_code, program_code, year, term, division_code,
                     day_of_week, period_index, subject_code, subject_type, faculty_ids)
                    VALUES (:ay, :degree, :program, :year, :term, :div,
                            :day, :per, :subj, :type, :fac)
                """), {
                    'ay': self.ctx.ay,
                    'degree': self.ctx.degree,
                    'program': self.ctx.program,
                    'year': self.ctx.year,
                    'term': self.ctx.term,
                    'div': division_code,
                    'day': day_num,
                    'per': period_idx,
                    'subj': subject_code,
                    'type': subject_type,
                    'fac': faculty_ids
                })
    
    def _delete_assignment(self, day_num: int, period_idx: int, division_code: str):
        """Delete an assignment"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM normalized_weekly_assignment
                WHERE ay_label = :ay AND degree_code = :degree
                AND year = :year AND term = :term
                AND day_of_week = :day AND period_index = :per
                AND division_code = :div
            """), {
                'ay': self.ctx.ay,
                'degree': self.ctx.degree,
                'year': self.ctx.year,
                'term': self.ctx.term,
                'day': day_num,
                'per': period_idx,
                'div': division_code
            })
    
    def _render_grid(self, template_slots: pd.DataFrame, 
                     override_map: Dict[str, pd.DataFrame],
                     assignments: pd.DataFrame):
        """Render the timetable grid with dropdown menus"""
        
        # Filter teaching slots only
        teaching_slots = template_slots[template_slots['is_teaching_slot'] == 1]
        
        if teaching_slots.empty:
            st.warning("No teaching slots defined in template")
            return
        
        # Header row
        cols = st.columns([1.5] + [1] * 6)
        cols[0].markdown("### Period")
        for i, day in enumerate(DAYS):
            label = f"**{day}**"
            if day in override_map:
                label += " ⚠️"
            cols[i + 1].markdown(label)
        
        st.divider()
        
        # Period rows
        for _, slot in teaching_slots.iterrows():
            period_idx = slot['slot_index']
            
            # Period info column
            row_cols = st.columns([1.5] + [1] * 6)
            
            p_label = f"**{slot['slot_label']}**"
            if slot['fixed_start_time']:
                p_label += f"<br><span style='color:gray;font-size:0.8em'>{slot['fixed_start_time']} - {slot['fixed_end_time']}</span>"
            row_cols[0].markdown(p_label, unsafe_allow_html=True)
            
            # Day columns
            for day_idx, day in enumerate(DAYS):
                with row_cols[day_idx + 1]:
                    # Check if this slot is active for this day
                    is_active = True
                    if day in override_map:
                        o_slots = override_map[day]
                        teaching_overrides = o_slots[o_slots['is_teaching_slot'] == 1]
                        if period_idx not in teaching_overrides['slot_index'].values:
                            is_active = False
                    
                    if not is_active:
                        st.markdown("---")
                    else:
                        self._render_cell(day, period_idx, assignments)
    
    def _render_cell(self, day: str, period: int, assignments: pd.DataFrame):
        """Render a single cell with dropdown menus"""
        day_num = DAY_MAP[day]
        
        # Get available subjects
        subjects_df = self._get_available_subjects()
        
        if subjects_df.empty:
            st.info("No subjects in distribution")
            return
        
        # Find assignment for this cell
        match = assignments[
            (assignments['day_of_week'] == day_num) & 
            (assignments['period_index'] == period)
        ]
        
        key = f"cell_{day}_{period}"
        
        # Current assignment
        current_subject = None
        current_division = None
        current_faculty = None
        
        if not match.empty:
            row = match.iloc[0]
            current_subject = row['subject_code']
            current_division = row['division_code']
            current_faculty = row.get('faculty_ids', '')
        
        # Subject + Division dropdown
        subject_div_options = ["-- Select Subject --"] + subjects_df['display_name'].tolist()
        
        current_idx = 0
        if current_subject:
            for idx, subj_div in enumerate(subjects_df.itertuples()):
                if subj_div.subject_code == current_subject and subj_div.division_code == current_division:
                    current_idx = idx + 1
                    break
        
        selected_subject_div = st.selectbox(
            "Subject",
            options=subject_div_options,
            index=current_idx,
            key=f"subj_{key}",
            label_visibility="collapsed"
        )
        
        # If subject selected, show faculty dropdown
        if selected_subject_div != "-- Select Subject --":
            selected_row = subjects_df[subjects_df['display_name'] == selected_subject_div].iloc[0]
            subject_code = selected_row['subject_code']
            division_code = selected_row['division_code']
            subject_type = selected_row['subject_type']
            
            # Get faculty
            faculty_list = self._get_faculty_for_subject(subject_code, division_code)
            
            if faculty_list:
                faculty_options = ["-- Select Faculty --"] + [f"{f['faculty_id']} - {f['faculty_name']}" for f in faculty_list]
                
                faculty_idx = 0
                if current_faculty:
                    for idx, fac in enumerate(faculty_list):
                        if str(fac['faculty_id']) == current_faculty:
                            faculty_idx = idx + 1
                            break
                
                selected_faculty = st.selectbox(
                    "Faculty",
                    options=faculty_options,
                    index=faculty_idx,
                    key=f"fac_{key}",
                    label_visibility="collapsed"
                )
                
                if selected_faculty != "-- Select Faculty --":
                    faculty_id = selected_faculty.split(' - ')[0]
                    
                    # Save button
                    if st.button("💾 Save", key=f"save_{key}", use_container_width=True):
                        self._save_assignment(
                            day_num, period, subject_code, division_code,
                            faculty_id, subject_type
                        )
                        st.success("Saved!")
                        st.rerun()
                    
                    # Show current if exists
                    if not match.empty:
                        st.caption(f"✓ {current_subject} ({current_division})")
            else:
                st.info("No faculty assigned")
        
        # Clear button if exists
        if not match.empty:
            if st.button("🗑️ Clear", key=f"clear_{key}", use_container_width=True):
                self._delete_assignment(day_num, period, current_division)
                st.success("Cleared!")
                st.rerun()
    
    def _render_no_template_guidance(self):
        """Show guidance when no template found"""
        st.info("**What you need to do:**")
        
        st.markdown("""
        1. **Go to 'Timegrid Configuration' tab**
        2. **Create a new template** for this context:
           - Academic Year: `{ay}`
           - Degree: `{degree}`
           - Term: `{term}`
        3. **Add teaching periods** (e.g., Period 1, Period 2, Break, Period 3...)
        4. **Publish the template**
        5. **Return to this tab** to assign subjects
        """.format(
            ay=self.ctx.ay,
            degree=self.ctx.degree,
            term=self.ctx.term
        ))
        
        with st.expander("🔍 Debug: What I'm looking for", expanded=False):
            st.code(f"""
Context being searched:
- Academic Year: {self.ctx.ay}
- Degree: {self.ctx.degree}
- Program: {self.ctx.program or 'NULL (matches any)'}
- Term: {self.ctx.term}

Looking for a published template matching this context.
            """)
