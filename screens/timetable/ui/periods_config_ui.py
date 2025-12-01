"""
Periods/Timegrid Configuration UI
- Visual timeline with drag-and-drop
- Period types management
- Day template builder
- Weekday overrides
- Draft/Publish/Archive workflow
- AY-to-AY copy functionality
- CSV Import functionality
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# ===================================================================
# CONSTANTS
# ===================================================================

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

ROLE_COLORS = {
    'teaching': '#2196F3',
    'break': '#FFC107',
    'lunch': '#FF5722',
    'assembly': '#607D8B',
    'buffer': '#9E9E9E',
    'other': '#757575'
}

ROLE_ICONS = {
    'teaching': '📚',
    'break': '☕',
    'lunch': '🍽️',
    'assembly': '🎤',
    'buffer': '⏸️',
    'other': '⚙️'
}

# ===================================================================
# HELPER FUNCTIONS
# ===================================================================

def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight"""
    if not time_str:
        return 0
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def minutes_to_time(minutes: int) -> str:
    """Convert minutes since midnight to HH:MM"""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def add_minutes_to_time(time_str: str, minutes: int) -> str:
    """Add minutes to a time string"""
    base_minutes = time_to_minutes(time_str)
    new_minutes = base_minutes + minutes
    return minutes_to_time(new_minutes)


# ===================================================================
# DATA ACCESS LAYER
# ===================================================================

class PeriodsDataService:
    """Handles all database operations for periods configuration"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    # ---- PERIOD KINDS ----
    
    def fetch_period_kinds(self, active_only: bool = True) -> pd.DataFrame:
        """Fetch period types"""
        with self.engine.connect() as conn:
            query = "SELECT * FROM period_kinds"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY role, sort_order, label"
            return pd.read_sql(query, conn)
    
    def create_period_kind(self, data: dict) -> int:
        """Create new period kind"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO period_kinds 
                (code, label, role, default_duration_min, color_hex, icon, 
                 is_blockable, is_extendable, description, created_by)
                VALUES (:code, :label, :role, :duration, :color, :icon,
                        :blockable, :extendable, :desc, :actor)
            """), data)
            return result.lastrowid
    
    def update_period_kind(self, kind_id: int, data: dict) -> None:
        """Update period kind"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE period_kinds
                SET label = :label,
                    default_duration_min = :duration,
                    color_hex = :color,
                    icon = :icon,
                    is_blockable = :blockable,
                    is_extendable = :extendable,
                    description = :desc,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {**data, 'id': kind_id})
    
    def delete_period_kind(self, kind_id: int) -> None:
        """Soft delete period kind"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE period_kinds SET active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {'id': kind_id})
    
    # ---- TEMPLATES ----
    
    def fetch_templates_for_context(self, ay: str, term: int, degree: str,
                                    program: str = None, branch: str = None,
                                    year: int = None) -> pd.DataFrame:
        """Fetch templates for specific context"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT * FROM v_day_templates_full
                WHERE ay_label = :ay
                  AND term = :term
                  AND degree_code = :degree
                  AND (:prog IS NULL OR program_code = :prog OR program_code IS NULL)
                  AND (:branch IS NULL OR branch_code = :branch OR branch_code IS NULL)
                  AND (:yr IS NULL OR year = :yr OR year IS NULL)
                  AND status != 'deleted'
                ORDER BY status, template_name
            """), conn, params={
                'ay': ay, 'term': term, 'degree': degree,
                'prog': program, 'branch': branch, 'yr': year
            })
    
    def get_template_by_id(self, template_id: int) -> Optional[dict]:
        """Get full template details"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM day_templates WHERE id = :id
            """), {'id': template_id}).fetchone()
            return dict(result._mapping) if result else None
    
    def create_template(self, data: dict) -> int:
        """Create new template"""
        params = {
            'code': data['code'],
            'name': data['name'],
            'ay': data['ay'],
            'term': data['term'],
            'degree': data['degree'],
            'prog': data.get('program'),
            'branch': data.get('branch'),
            'yr': data.get('year'),
            'count_mode': data['count_mode'],
            'actor': data['actor']
        }
        
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO day_templates
                (template_code, template_name, ay_label, term, degree_code,
                 program_code, branch_code, year, status, count_mode,
                 created_by, created_at)
                VALUES (:code, :name, :ay, :term, :degree,
                        :prog, :branch, :yr, 'draft', :count_mode,
                        :actor, CURRENT_TIMESTAMP)
            """), params)
            
            template_id = result.lastrowid
            
            # Log audit
            conn.execute(text("""
                INSERT INTO day_template_audit
                (template_id, template_code, action, actor, note)
                VALUES (:id, :code, 'create', :actor, :note)
            """), {
                'id': template_id,
                'code': data['code'],
                'actor': data['actor'],
                'note': f"Created template '{data['name']}'"
            })
            
            return template_id
    
    def publish_template(self, template_id: int, actor: str) -> None:
        """Publish template"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE day_templates
                SET status = 'published',
                    published_by = :actor,
                    published_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {'id': template_id, 'actor': actor})
            
            conn.execute(text("""
                INSERT INTO day_template_audit
                (template_id, action, actor, note)
                VALUES (:id, 'publish', :actor, 'Template published')
            """), {'id': template_id, 'actor': actor})
    
    def archive_template(self, template_id: int, actor: str, reason: str) -> None:
        """Archive template"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE day_templates
                SET status = 'archived',
                    archived_by = :actor,
                    archived_at = CURRENT_TIMESTAMP,
                    archived_reason = :reason,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {'id': template_id, 'actor': actor, 'reason': reason})
            
            conn.execute(text("""
                INSERT INTO day_template_audit
                (template_id, action, actor, note)
                VALUES (:id, 'archive', :actor, :reason)
            """), {'id': template_id, 'actor': actor, 'reason': reason})
    
    def delete_template(self, template_id: int, actor: str) -> None:
        """Soft delete template"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE day_templates
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {'id': template_id})
            
            conn.execute(text("""
                INSERT INTO day_template_audit
                (template_id, action, actor, note)
                VALUES (:id, 'delete', :actor, 'Template deleted')
            """), {'id': template_id, 'actor': actor})
    
    # ---- SLOTS ----
    
    def fetch_template_slots(self, template_id: int) -> pd.DataFrame:
        """Fetch slots for template"""
        # FIX: Removed 'pk.role' to avoid duplicate 'role' columns
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT s.*, pk.label as kind_label, pk.color_hex, pk.icon
                FROM day_template_slots s
                JOIN period_kinds pk ON s.period_kind_code = pk.code
                WHERE s.template_id = :id
                ORDER BY s.slot_index
            """), conn, params={'id': template_id})
    
    def add_slot(self, template_id: int, slot_data: dict) -> int:
        """Add new slot to template"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO day_template_slots
                (template_id, slot_index, slot_code, slot_label, period_kind_code,
                 duration_min, fixed_start_time, fixed_end_time, is_teaching_slot, role)
                VALUES (:template_id, :index, :code, :label, :kind,
                        :duration, :start, :end, :is_teaching, :role)
            """), {**slot_data, 'template_id': template_id})
            
            return result.lastrowid
    
    def update_slot(self, slot_id: int, slot_data: dict) -> None:
        """Update slot"""
        params = {
            'label': slot_data['label'],
            'duration': slot_data['duration'],
            'start': slot_data['start'],
            'end': slot_data['end'],
            'notes': slot_data['notes'],
            'id': slot_id
        }
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE day_template_slots
                SET slot_label = :label,
                    duration_min = :duration,
                    fixed_start_time = :start,
                    fixed_end_time = :end,
                    notes = :notes
                WHERE id = :id
            """), params)
    
    def delete_slot(self, slot_id: int) -> None:
        """Delete slot"""
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM day_template_slots WHERE id = :id"), {'id': slot_id})
    
    def reorder_slots(self, template_id: int, slot_order: List[int]) -> None:
        """Reorder slots"""
        with self.engine.begin() as conn:
            for new_index, slot_id in enumerate(slot_order, start=1):
                conn.execute(text("""
                    UPDATE day_template_slots
                    SET slot_index = :index
                    WHERE id = :id
                """), {'index': new_index, 'id': slot_id})
    
    # ---- WEEKDAY OVERRIDES ----
    
    def fetch_overrides(self, template_id: int) -> pd.DataFrame:
        """Fetch weekday overrides"""
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT * FROM day_template_weekday_overrides
                WHERE template_id = :id
                ORDER BY 
                    CASE weekday
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END
            """), conn, params={'id': template_id})
    
    def create_override(self, template_id: int, weekday: str, reason: str, actor: str) -> int:
        """Create weekday override"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO day_template_weekday_overrides
                (template_id, weekday, override_reason, created_by)
                VALUES (:template_id, :weekday, :reason, :actor)
            """), {
                'template_id': template_id,
                'weekday': weekday,
                'reason': reason,
                'actor': actor
            })
            return result.lastrowid
    
    def fetch_override_slots(self, override_id: int) -> pd.DataFrame:
        """Fetch slots for override"""
        # FIX: Removed 'pk.role' to avoid duplicate 'role' columns
        with self.engine.connect() as conn:
            return pd.read_sql(text("""
                SELECT s.*, pk.label as kind_label, pk.color_hex, pk.icon
                FROM day_template_override_slots s
                JOIN period_kinds pk ON s.period_kind_code = pk.code
                WHERE s.override_id = :id
                ORDER BY s.slot_index
            """), conn, params={'id': override_id})
    
    def add_override_slot(self, override_id: int, slot_data: dict) -> int:
        """Add slot to override"""
        with self.engine.begin() as conn:
            result = conn.execute(text("""
                INSERT INTO day_template_override_slots
                (override_id, slot_index, slot_code, slot_label, period_kind_code,
                 duration_min, fixed_start_time, fixed_end_time, is_teaching_slot, role)
                VALUES (:override_id, :index, :code, :label, :kind,
                        :duration, :start, :end, :is_teaching, :role)
            """), {**slot_data, 'override_id': override_id})
            return result.lastrowid
    
    def delete_override(self, override_id: int) -> None:
        """Delete weekday override"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM day_template_weekday_overrides WHERE id = :id
            """), {'id': override_id})
    
    # ---- COPY OPERATIONS ----
    
    def copy_template_from_ay(self, source_template_id: int, target_ay: str,
                              target_term: int, actor: str) -> int:
        """Copy template from previous AY"""
        with self.engine.begin() as conn:
            # Get source template
            source = conn.execute(text("""
                SELECT * FROM day_templates WHERE id = :id
            """), {'id': source_template_id}).fetchone()
            
            if not source:
                raise ValueError(f"Source template {source_template_id} not found")
            
            source_dict = dict(source._mapping)
            
            # Create new template
            result = conn.execute(text("""
                INSERT INTO day_templates
                (template_code, template_name, ay_label, term, degree_code,
                 program_code, branch_code, year, status, count_mode,
                 copied_from_template_id, copy_source_ay, created_by, created_at)
                VALUES (:code, :name, :ay, :term, :degree,
                        :prog, :branch, :yr, 'draft', :count_mode,
                        :source_id, :source_ay, :actor, CURRENT_TIMESTAMP)
            """), {
                'code': source_dict['template_code'],
                'name': source_dict['template_name'],
                'ay': target_ay,
                'term': target_term,
                'degree': source_dict['degree_code'],
                'prog': source_dict['program_code'],
                'branch': source_dict['branch_code'],
                'yr': source_dict['year'],
                'count_mode': source_dict['count_mode'],
                'source_id': source_template_id,
                'source_ay': source_dict['ay_label'],
                'actor': actor
            })
            
            new_template_id = result.lastrowid
            
            # Copy slots
            slots = conn.execute(text("""
                SELECT * FROM day_template_slots WHERE template_id = :id
                ORDER BY slot_index
            """), {'id': source_template_id}).fetchall()
            
            for slot in slots:
                slot_dict = dict(slot._mapping)
                conn.execute(text("""
                    INSERT INTO day_template_slots
                    (template_id, slot_index, slot_code, slot_label, period_kind_code,
                     duration_min, fixed_start_time, fixed_end_time, is_teaching_slot,
                     role, is_block_start, is_block_part, block_group_id, notes)
                    VALUES (:template_id, :index, :code, :label, :kind,
                            :duration, :start, :end, :is_teaching,
                            :role, :block_start, :block_part, :block_group, :notes)
                """), {
                    'template_id': new_template_id,
                    'index': slot_dict['slot_index'],
                    'code': slot_dict['slot_code'],
                    'label': slot_dict['slot_label'],
                    'kind': slot_dict['period_kind_code'],
                    'duration': slot_dict['duration_min'],
                    'start': slot_dict['fixed_start_time'],
                    'end': slot_dict['fixed_end_time'],
                    'is_teaching': slot_dict['is_teaching_slot'],
                    'role': slot_dict['role'],
                    'block_start': slot_dict['is_block_start'],
                    'block_part': slot_dict['is_block_part'],
                    'block_group': slot_dict['block_group_id'],
                    'notes': slot_dict['notes']
                })
            
            # Copy overrides
            overrides = conn.execute(text("""
                SELECT * FROM day_template_weekday_overrides WHERE template_id = :id
            """), {'id': source_template_id}).fetchall()
            
            for override in overrides:
                override_dict = dict(override._mapping)
                override_result = conn.execute(text("""
                    INSERT INTO day_template_weekday_overrides
                    (template_id, weekday, override_reason, created_by)
                    VALUES (:template_id, :weekday, :reason, :actor)
                """), {
                    'template_id': new_template_id,
                    'weekday': override_dict['weekday'],
                    'reason': override_dict['override_reason'],
                    'actor': actor
                })
                
                new_override_id = override_result.lastrowid
                
                # Copy override slots
                override_slots = conn.execute(text("""
                    SELECT * FROM day_template_override_slots WHERE override_id = :id
                    ORDER BY slot_index
                """), {'id': override_dict['id']}).fetchall()
                
                for oslot in override_slots:
                    oslot_dict = dict(oslot._mapping)
                    conn.execute(text("""
                        INSERT INTO day_template_override_slots
                        (override_id, slot_index, slot_code, slot_label, period_kind_code,
                         duration_min, fixed_start_time, fixed_end_time, is_teaching_slot,
                         role, notes)
                        VALUES (:override_id, :index, :code, :label, :kind,
                                :duration, :start, :end, :is_teaching, :role, :notes)
                    """), {
                        'override_id': new_override_id,
                        'index': oslot_dict['slot_index'],
                        'code': oslot_dict['slot_code'],
                        'label': oslot_dict['slot_label'],
                        'kind': oslot_dict['period_kind_code'],
                        'duration': oslot_dict['duration_min'],
                        'start': oslot_dict['fixed_start_time'],
                        'end': oslot_dict['fixed_end_time'],
                        'is_teaching': oslot_dict['is_teaching_slot'],
                        'role': oslot_dict['role'],
                        'notes': oslot_dict['notes']
                    })
            
            # Log audit
            conn.execute(text("""
                INSERT INTO day_template_audit
                (template_id, template_code, action, actor, note)
                VALUES (:id, :code, 'copy_from_ay', :actor, :note)
            """), {
                'id': new_template_id,
                'code': source_dict['template_code'],
                'actor': actor,
                'note': f"Copied from {source_dict['ay_label']} T{source_dict['term']}"
            })
            
            return new_template_id


# ===================================================================
# UI COMPONENTS
# ===================================================================

class PeriodKindsManager:
    """UI for managing period types"""
    
    def __init__(self, service: PeriodsDataService):
        self.service = service
    
    def render(self):
        st.header("🎨 Period Types Manager")
        st.caption("Define reusable period types (Lecture, Studio, Practical, etc.)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_kinds_list()
        
        with col2:
            # FIX: Check if we are in edit mode based on session state
            if 'editing_kind' in st.session_state:
                self._render_edit_form(st.session_state['editing_kind'])
            else:
                self._render_create_form()
    
    def _render_kinds_list(self):
        """Display existing period kinds"""
        kinds = self.service.fetch_period_kinds()
        
        if kinds.empty:
            st.info("No period types defined yet")
            return
        
        st.subheader("Existing Period Types")
        
        for _, kind in kinds.iterrows():
            with st.expander(
                f"{kind['icon']} **{kind['label']}** ({kind['default_duration_min']} min)",
                expanded=False
            ):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"**Code:** `{kind['code']}`")
                    st.markdown(f"**Role:** {kind['role']}")
                
                with col2:
                    st.markdown(f"**Duration:** {kind['default_duration_min']} min")
                    st.markdown(f"**Color:** {kind['color_hex']}")
                
                with col3:
                    if kind['is_blockable']:
                        st.success("✅ Blockable")
                    if kind['is_extendable']:
                        st.info("🔧 Extendable")
                
                if kind['description']:
                    st.caption(kind['description'])
                
                # Edit/Delete buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    # Sets the session state to trigger edit mode
                    if st.button("✏️ Edit", key=f"edit_kind_{kind['id']}"):
                        st.session_state['editing_kind'] = kind['id']
                        st.rerun()
                
                with col2:
                    if st.button("🗑️ Delete", key=f"del_kind_{kind['id']}"):
                        self.service.delete_period_kind(kind['id'])
                        st.success("Deleted!")
                        st.rerun()

    def _render_edit_form(self, kind_id):
        """Form to edit an existing period kind"""
        st.subheader("✏️ Edit Period Type")
        
        # Fetch fresh data to ensure we have the specific row
        kinds = self.service.fetch_period_kinds(active_only=False)
        target_kind = kinds[kinds['id'] == kind_id]
        
        if target_kind.empty:
            st.error("Period type not found.")
            if st.button("Cancel"):
                del st.session_state['editing_kind']
                st.rerun()
            return

        kind = target_kind.iloc[0]

        with st.form("edit_period_kind_form"):
            st.caption(f"Editing Code: **{kind['code']}**")
            
            label = st.text_input(
                "Label*",
                value=kind['label'],
                placeholder="Lecture - 50 min"
            )
            
            role = st.selectbox(
                "Role*",
                options=['teaching', 'break', 'lunch', 'assembly', 'buffer', 'other'],
                index=['teaching', 'break', 'lunch', 'assembly', 'buffer', 'other'].index(kind['role']) if kind['role'] in ['teaching', 'break', 'lunch', 'assembly', 'buffer', 'other'] else 0
            )
            
            duration = st.number_input(
                "Default Duration (minutes)*",
                min_value=5,
                max_value=300,
                value=int(kind['default_duration_min']),
                step=5
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                color = st.color_picker(
                    "Color",
                    value=kind['color_hex']
                )
            
            with col2:
                icon = st.text_input(
                    "Icon (emoji)",
                    value=kind['icon']
                )
            
            col1, col2 = st.columns(2)
            
            with col1:
                blockable = st.checkbox(
                    "Blockable",
                    value=bool(kind['is_blockable']),
                    help="Can span multiple grid slots"
                )
            
            with col2:
                extendable = st.checkbox(
                    "Extendable",
                    value=bool(kind['is_extendable']),
                    help="Can be extended beyond default duration"
                )
            
            description = st.text_area(
                "Description",
                value=kind['description'] if kind['description'] else "",
                placeholder="Optional description..."
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                submitted = st.form_submit_button("💾 Save Changes", type="primary")
            
            with col2:
                cancel = st.form_submit_button("Cancel")
            
            if submitted:
                if not label:
                    st.error("Label is required")
                else:
                    try:
                        self.service.update_period_kind(kind_id, {
                            'label': label,
                            'duration': duration,
                            'color': color,
                            'icon': icon,
                            'blockable': 1 if blockable else 0,
                            'extendable': 1 if extendable else 0,
                            'desc': description
                            # Note: Code and Role are typically kept stable or handled carefully, 
                            # here we updated Role but not Code.
                        })
                        st.success(f"✅ Updated '{label}'")
                        del st.session_state['editing_kind']
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            if cancel:
                del st.session_state['editing_kind']
                st.rerun()
    
    def _render_create_form(self):
        """Form to create new period kind"""
        st.subheader("➕ Create New Period Type")
        
        with st.form("create_period_kind"):
            code = st.text_input(
                "Code*",
                placeholder="LECTURE_50",
                help="Unique identifier (e.g., LECTURE_50, STUDIO_180)"
            )
            
            label = st.text_input(
                "Label*",
                placeholder="Lecture - 50 min",
                help="Display name"
            )
            
            role = st.selectbox(
                "Role*",
                options=['teaching', 'break', 'lunch', 'assembly', 'buffer', 'other'],
                help="Period classification"
            )
            
            duration = st.number_input(
                "Default Duration (minutes)*",
                min_value=5,
                max_value=300,
                value=40,
                step=5
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                color = st.color_picker(
                    "Color",
                    value=ROLE_COLORS.get(role, '#2196F3')
                )
            
            with col2:
                icon = st.text_input(
                    "Icon (emoji)",
                    value=ROLE_ICONS.get(role, '📚')
                )
            
            col1, col2 = st.columns(2)
            
            with col1:
                blockable = st.checkbox(
                    "Blockable",
                    help="Can span multiple grid slots"
                )
            
            with col2:
                extendable = st.checkbox(
                    "Extendable",
                    help="Can be extended beyond default duration"
                )
            
            description = st.text_area(
                "Description",
                placeholder="Optional description..."
            )
            
            submitted = st.form_submit_button("Create Period Type", type="primary")
            
            if submitted:
                if not code or not label:
                    st.error("Code and Label are required")
                else:
                    try:
                        self.service.create_period_kind({
                            'code': code.upper(),
                            'label': label,
                            'role': role,
                            'duration': duration,
                            'color': color,
                            'icon': icon,
                            'blockable': 1 if blockable else 0,
                            'extendable': 1 if extendable else 0,
                            'desc': description,
                            'actor': 'user'
                        })
                        st.success(f"✅ Created period type '{label}'")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")


class TemplateSelector:
    """UI for selecting/creating templates - IMPROVED VERSION"""
    
    def __init__(self, service: PeriodsDataService, engine: Engine):
        self.service = service
        self.engine = engine
    
    def render(self) -> Optional[int]:
        st.header("📋 Template Manager")
        
        ctx = self._render_context_selector()
        if not ctx: return None
        
        # ============================================================================
        # FIX 1: Show currently selected template
        # ============================================================================
        current_template_id = st.session_state.get('active_config_template_id')
        
        if current_template_id:
            current_template = self.service.get_template_by_id(current_template_id)
            if current_template:
                if current_template['status'] == 'deleted':
                    st.error("⚠️ Currently selected template is DELETED. Please select a different template below.")
                    st.session_state['active_config_template_id'] = None
                    current_template_id = None
                else:
                    status_icons = {'draft': '📝', 'published': '✅', 'archived': '📦'}
                    status_icon = status_icons.get(current_template['status'], '📄')
                    st.success(f"**Currently Selected:** {status_icon} {current_template['template_name']} ({current_template['status']})")
                    if st.button("🔄 Select Different Template"):
                        st.session_state['active_config_template_id'] = None
                        st.rerun()
                    st.divider()
        
        # --- 1. RENDER ACTION BAR FIRST (So it always appears) ---
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("➕ Create New", type="primary"):
                self._reset_modes()
                st.session_state['creating_template'] = True
                st.rerun()
        
        with col2:
            if st.button("📂 Import CSV"):
                self._reset_modes()
                st.session_state['importing_csv'] = True
                st.rerun()

        with col3:
            if st.button("📋 Copy Prev AY"):
                self._reset_modes()
                st.session_state['copying_from_ay'] = True
                st.rerun()
        
        st.divider()
        
        # --- 2. RENDER MODES ---
        if st.session_state.get('creating_template'):
            return self._render_create_template_form(ctx)
        
        if st.session_state.get('copying_from_ay'):
            return self._render_copy_from_ay_form(ctx)

        if st.session_state.get('importing_csv'):
            return self._render_csv_import_form(ctx)
        
        # --- 3. FETCH & LIST DATA (Wrapped in try/except) ---
        try:
            templates = self.service.fetch_templates_for_context(**ctx)
            
            # ============================================================================
            # FIX 2: Filter out deleted templates
            # ============================================================================
            if not templates.empty:
                templates = templates[templates['status'] != 'deleted'].copy()
            
            if templates.empty:
                st.info(f"No active templates found for {ctx['degree']} - AY {ctx['ay']} Term {ctx['term']}")
                st.caption("Create a new template or copy from a previous academic year to get started.")
                return None
            
            # ============================================================================
            # FIX 3: Group templates by status and use new card renderer
            # ============================================================================
            st.subheader("Available Templates")
            
            published = templates[templates['status'] == 'published']
            drafts = templates[templates['status'] == 'draft']
            archived = templates[templates['status'] == 'archived']
            
            # Show published templates first
            if not published.empty:
                st.markdown("#### ✅ Published Templates")
                for _, template in published.iterrows():
                    self._render_template_card(template, current_template_id)
            
            # Then show drafts
            if not drafts.empty:
                st.markdown("#### 📝 Draft Templates")
                for _, template in drafts.iterrows():
                    self._render_template_card(template, current_template_id)
            
            # Finally archived
            if not archived.empty:
                with st.expander("📦 Archived Templates", expanded=False):
                    for _, template in archived.iterrows():
                        self._render_template_card(template, current_template_id)
            
            return current_template_id

        except Exception as e:
            st.warning(f"Could not load templates. Database view might be missing.")
            st.error(f"Error details: {e}")
            return None

    def _reset_modes(self):
        """Helper to clear other modes"""
        st.session_state['creating_template'] = False
        st.session_state['importing_csv'] = False
        st.session_state['copying_from_ay'] = False
    
    # ============================================================================
    # FIX 4: New method for rendering template cards
    # ============================================================================
    def _render_template_card(self, template, current_template_id):
        """Render a single template card with selection capability"""
        
        is_current = (template['id'] == current_template_id)
        
        # Different styling for currently selected template
        if is_current:
            container = st.container(border=True)
            container.success("👈 **Currently Selected**")
        else:
            container = st.container(border=True)
        
        with container:
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"### {template['template_name']}")
                st.caption(f"Code: {template.get('template_code', 'N/A')}")
            
            with col2:
                status_colors = {'published': 'green', 'draft': 'orange', 'archived': 'gray'}
                status_color = status_colors.get(template['status'], 'blue')
                st.markdown(f"<span style='color:{status_color}; font-weight:bold;'>{template['status'].upper()}</span>", unsafe_allow_html=True)
            
            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Slots", template.get('slot_count', 0))
            with col2:
                st.metric("Teaching Slots", template.get('teaching_slot_count', 0))
            with col3:
                st.metric("Total Time", f"{template.get('total_teaching_minutes', 0)} min")
            
            # Action buttons
            button_cols = st.columns([1, 1, 1, 1, 2])
            
            with button_cols[0]:
                if not is_current:
                    if st.button("🎯 Select", key=f"select_tmpl_{template['id']}"):
                        st.session_state['active_config_template_id'] = template['id']
                        st.rerun()
            
            with button_cols[1]:
                if st.button("✏️ Edit", key=f"edit_tmpl_{template['id']}"):
                    st.session_state['active_config_template_id'] = template['id']
                    st.session_state['editing_template'] = template['id']
                    st.rerun()
            
            with button_cols[2]:
                if template['status'] == 'draft':
                    if st.button("✅ Publish", key=f"pub_tmpl_{template['id']}"):
                        self.service.publish_template(template['id'], 'user')
                        st.success("Published!")
                        st.rerun()
            
            with button_cols[3]:
                if template['status'] == 'published':
                    if st.button("📦 Archive", key=f"arch_tmpl_{template['id']}"):
                        if st.session_state.get(f'confirm_archive_{template["id"]}'):
                            self.service.archive_template(template['id'], 'user', 'Archived via UI')
                            st.success("Archived!")
                            # Clear selection if this was active
                            if current_template_id == template['id']:
                                st.session_state['active_config_template_id'] = None
                            st.rerun()
                        else:
                            st.session_state[f'confirm_archive_{template["id"]}'] = True
                            st.warning("Click again to confirm archive")
            
            with button_cols[4]:
                if template['status'] in ['draft', 'archived']:
                    if st.button("🗑️ Delete", key=f"del_tmpl_{template['id']}"):
                        if st.session_state.get(f'confirm_del_{template["id"]}'):
                            self.service.delete_template(template['id'], 'user')
                            st.success("Deleted!")
                            # Clear selection if this was active
                            if current_template_id == template['id']:
                                st.session_state['active_config_template_id'] = None
                            st.rerun()
                        else:
                            st.session_state[f'confirm_del_{template["id"]}'] = True
                            st.warning("⚠️ Click again to confirm deletion")

    def _reset_modes(self):
        """Helper to clear other modes"""
        st.session_state['creating_template'] = False
        st.session_state['importing_csv'] = False
        st.session_state['copying_from_ay'] = False

    def _render_csv_import_form(self, ctx: dict):
        st.subheader("📂 Import Template from CSV")
        
        sample_csv = "Index,Label,Start Time,Duration,Type\n1,Period 1,08:00,50,Teaching\n2,Period 2,08:50,50,Teaching\n3,Break,11:20,40,Break"
        st.download_button(
            label="⬇️ Download Sample CSV Template",
            data=sample_csv,
            file_name="timegrid_template.csv",
            mime="text/csv"
        )
        
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                # Normalize headers: remove spaces, lowercase
                df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
                
                # Validation: Check required columns
                required = {'index', 'label', 'duration'} # 'start_time' is technically optional in logic but good to have
                if not required.issubset(set(df.columns)):
                    st.error(f"Missing required columns. Found: {list(df.columns)}")
                else:
                    st.dataframe(df.head())
                    
                    with st.form("csv_import_settings"):
                        t_name = st.text_input("Template Name", value="Imported Schedule")
                        # Generate a safe unique code
                        safe_ay = ctx['ay'].replace('-', '')
                        t_code = st.text_input("Template Code", value=f"IMP_{safe_ay}_{datetime.now().strftime('%M%S')}")
                        
                        if st.form_submit_button("🚀 Process & Import"):
                            self._process_csv_import(df, ctx, t_name, t_code)
            except Exception as e:
                st.error(f"Error reading CSV: {e}")

        if st.button("Cancel Import"):
            self._reset_modes()
            st.rerun()

    def _process_csv_import(self, df, ctx, name, code):
        try:
            # 1. Create Template
            template_id = self.service.create_template({
                'code': code.upper(),
                'name': name,
                **ctx,
                'count_mode': 'teaching_only',
                'actor': 'user'
            })
            
            # 2. Process Rows
            for _, row in df.iterrows():
                idx = row.get('index', 0)
                label = row.get('label', f"Period {idx}")
                duration = int(row.get('duration', 50))
                
                # Safe Time Parsing
                start_str = str(row.get('start_time', '')).strip()
                start = None
                end = None
                
                if start_str and start_str.lower() != 'nan':
                    try:
                        # Try parsing flexible formats (8:00, 08:00, 8:00:00)
                        start_dt = pd.to_datetime(start_str, format='%H:%M', errors='coerce')
                        if pd.isna(start_dt):
                             start_dt = pd.to_datetime(start_str, format='%H:%M:%S', errors='coerce')
                        
                        if not pd.isna(start_dt):
                            start = start_dt.strftime("%H:%M")
                            # Calculate End Time
                            end_dt = start_dt + timedelta(minutes=duration)
                            end = end_dt.strftime("%H:%M")
                    except:
                        pass # Leave as None if parse fails

                # Determine Type
                raw_type = str(row.get('type', 'Teaching')).lower()
                role = 'break' if any(x in raw_type for x in ['break', 'lunch', 'recess']) else 'teaching'
                is_teaching = 1 if role == 'teaching' else 0
                
                # Kind Code
                kind_code = f"{'LEC' if is_teaching else 'BRK'}_{duration}"
                self._ensure_period_kind(kind_code, role, duration)
                
                # Add Slot
                self.service.add_slot(template_id, {
                    'index': idx,
                    'code': f"P{idx}",
                    'label': label,
                    'kind': kind_code,
                    'duration': duration,
                    'start': start,
                    'end': end,
                    'is_teaching': is_teaching,
                    'role': role
                })
            
            st.success("✅ Import Successful!")
            st.session_state['importing_csv'] = False
            st.session_state['editing_template'] = template_id
            st.rerun()
            
        except Exception as e:
            st.error(f"Import Failed: {e}")
            # st.exception(e) # Uncomment to see full traceback in UI

    def _ensure_period_kind(self, code, role, duration):
        """Helper to create period kind on the fly if it doesn't exist"""
        with self.engine.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM period_kinds WHERE code=:c"), {'c': code}).scalar()
            if not exists:
                conn.execute(text("""
                    INSERT INTO period_kinds (code, label, role, default_duration_min, color_hex, icon, is_blockable, created_by)
                    VALUES (:c, :l, :r, :d, :col, :icon, 1, 'system')
                """), {
                    'c': code,
                    'l': f"{code} (Auto)",
                    'r': role,
                    'd': duration,
                    'col': '#FFF3E0' if role == 'break' else '#E3F2FD',
                    'icon': '☕' if role == 'break' else '📚'
                })
    
    def _render_context_selector(self) -> Optional[dict]:
        """Render context selection UI"""
        with self.engine.connect() as conn:
            ays = pd.read_sql(
                "SELECT ay_code FROM academic_years ORDER BY ay_code DESC",
                conn
            )
            degrees = pd.read_sql(
                "SELECT code, title FROM degrees WHERE active=1 ORDER BY code",
                conn
            )
        
        if ays.empty or degrees.empty:
            st.error("No Academic Years or Degrees configured")
            return None
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            ay = st.selectbox("Academic Year", ays['ay_code'].tolist(), key='periods_ay')
        
        with col2:
            degree = st.selectbox("Degree", degrees['code'].tolist(), key='periods_degree')
        
        with col3:
            term = st.number_input("Term", 1, 2, 1, key='periods_term')
        
        # Optional: Program/Branch/Year
        col1, col2, col3 = st.columns(3)
        
        with col1:
            with self.engine.connect() as conn:
                progs = pd.read_sql(text("""
                    SELECT program_code FROM programs 
                    WHERE degree_code=:d AND active=1 
                    ORDER BY program_code
                """), conn, params={'d': degree})
            
            program = None
            if not progs.empty:
                program = st.selectbox(
                    "Program (optional)",
                    [None] + progs['program_code'].tolist(),
                    key='periods_prog'
                )
        
        with col2:
            branch = None
            if program:
                with self.engine.connect() as conn:
                    branches = pd.read_sql(text("""
                        SELECT b.branch_code FROM branches b
                        JOIN programs p ON b.program_id = p.id
                        WHERE p.program_code=:p AND b.active=1
                        ORDER BY b.branch_code
                    """), conn, params={'p': program})
                
                if not branches.empty:
                    branch = st.selectbox(
                        "Branch (optional)",
                        [None] + branches['branch_code'].tolist(),
                        key='periods_branch'
                    )
        
        with col3:
            year = st.selectbox(
                "Year (optional)",
                [None, 1, 2, 3, 4, 5],
                key='periods_year'
            )
        
        return {
            'ay': ay,
            'term': term,
            'degree': degree,
            'program': program,
            'branch': branch,
            'year': year
        }
    
    def _render_create_template_form(self, ctx: dict) -> None:
        """Form to create new template"""
        st.subheader("Create New Template")
        
        with st.form("create_template"):
            template_code = st.text_input(
                "Template Code*",
                placeholder="STANDARD_8P",
                help="Unique identifier"
            )
            
            template_name = st.text_input(
                "Template Name*",
                placeholder="Standard 8-Period Day",
                help="Descriptive name"
            )
            
            count_mode = st.radio(
                "Count Mode",
                options=['teaching_only', 'all_slots'],
                format_func=lambda x: 'Teaching Slots Only' if x == 'teaching_only' else 'All Slots',
                help="How to count periods in reports"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                submit = st.form_submit_button("Create Template", type="primary")
            
            with col2:
                cancel = st.form_submit_button("Cancel")
            
            if submit:
                if not template_code or not template_name:
                    st.error("Code and Name are required")
                else:
                    try:
                        template_id = self.service.create_template({
                            'code': template_code.upper(),
                            'name': template_name,
                            **ctx,
                            'count_mode': count_mode,
                            'actor': 'user'
                        })
                        st.success(f"✅ Created template '{template_name}'")
                        st.session_state['creating_template'] = False
                        st.session_state['editing_template'] = template_id
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            if cancel:
                st.session_state['creating_template'] = False
                st.rerun()
    
    def _render_copy_from_ay_form(self, ctx: dict) -> None:
        """Form to copy template from previous AY"""
        st.subheader("Copy Template from Previous AY")
        
        # Fetch templates from previous AYs
        with self.engine.connect() as conn:
            prev_ays = pd.read_sql(text("""
                SELECT DISTINCT ay_label FROM day_templates
                WHERE degree_code = :degree
                  AND ay_label != :current_ay
                ORDER BY ay_label DESC
            """), conn, params={'degree': ctx['degree'], 'current_ay': ctx['ay']})
        
        if prev_ays.empty:
            st.warning("No templates found in previous AYs to copy from")
            if st.button("Cancel"):
                st.session_state['copying_from_ay'] = False
                st.rerun()
            return
        
        source_ay = st.selectbox("Source AY", prev_ays['ay_label'].tolist())
        
        # Fetch templates from source AY
        source_templates = self.service.fetch_templates_for_context(
            ay=source_ay,
            term=ctx['term'],
            degree=ctx['degree'],
            program=ctx.get('program'),
            branch=ctx.get('branch'),
            year=ctx.get('year')
        )
        
        if source_templates.empty:
            st.warning(f"No templates found in {source_ay}")
            if st.button("Cancel"):
                st.session_state['copying_from_ay'] = False
                st.rerun()
            return
        
        source_template_id = st.selectbox(
            "Select Template to Copy",
            options=source_templates['id'].tolist(),
            format_func=lambda x: source_templates[source_templates['id'] == x]['template_name'].iloc[0]
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📋 Copy Template", type="primary"):
                try:
                    new_id = self.service.copy_template_from_ay(
                        source_template_id,
                        ctx['ay'],
                        ctx['term'],
                        'user'
                    )
                    st.success(f"✅ Template copied successfully!")
                    st.session_state['copying_from_ay'] = False
                    st.session_state['editing_template'] = new_id
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with col2:
            if st.button("Cancel"):
                st.session_state['copying_from_ay'] = False
                st.rerun()
