# ui/periods_config_ui_part2.py
"""
Periods Configuration UI - Part 2
- Day Structure Builder with Visual Timeline
- Weekday Overrides
- Preview & Summary
- Main Application
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime

# Import from part 1
from periods_config_ui import (
    PeriodsDataService, time_to_minutes, minutes_to_time, 
    add_minutes_to_time, WEEKDAYS, ROLE_COLORS, ROLE_ICONS
)


class DayStructureBuilder:
    """Visual timeline builder for day structure"""
    
    def __init__(self, service: PeriodsDataService, template_id: int):
        self.service = service
        self.template_id = template_id
    
    def render(self):
        st.header("🗓️ Day Structure Builder")
        
        template = self.service.get_template_by_id(self.template_id)
        
        if not template:
            st.error("Template not found")
            return
        
        st.caption(f"Editing: **{template['template_name']}**")
        
        # Fetch existing slots
        slots_df = self.service.fetch_template_slots(self.template_id)
        
        # Render visual timeline
        self._render_visual_timeline(slots_df)
        
        st.divider()
        
        # Slot editor
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_slots_list(slots_df)
        
        with col2:
            self._render_add_slot_form(slots_df)
    
    def _render_visual_timeline(self, slots_df: pd.DataFrame):
        """Render visual timeline of periods"""
        st.subheader("📊 Visual Timeline")
        
        if slots_df.empty:
            st.info("No periods defined yet. Add periods below to see the timeline.")
            return
        
        # Calculate timeline metrics
        total_minutes = slots_df['duration_min'].sum()
        teaching_minutes = slots_df[slots_df['is_teaching_slot'] == 1]['duration_min'].sum()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Duration", f"{total_minutes} min")
        
        with col2:
            st.metric("Teaching Time", f"{teaching_minutes} min")
        
        with col3:
            st.metric("Slots", len(slots_df))
        
        # Render timeline bars
        st.markdown("---")
        
        current_time = "08:00" # Default start
        
        for _, slot in slots_df.iterrows():
            if slot['fixed_start_time']:
                current_time = slot['fixed_start_time']
            
            end_time = slot['fixed_end_time'] if slot['fixed_end_time'] else add_minutes_to_time(current_time, slot['duration_min'])
            
            self._render_slot_bar(slot, current_time, end_time)
            current_time = end_time
    
    def _render_slot_bar(self, slot: pd.Series, start_time: str, end_time: str):
        """Render a single slot as a colored bar"""
        width_pct = min(100, max(20, slot['duration_min'] * 1.5)) 
        color = slot.get('color_hex', ROLE_COLORS.get(slot['role'], '#2196F3'))
        
        html = f"""
        <div style="
            background: {color};
            color: white;
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            width: {width_pct}%;
            min-width: 250px;
        ">
            <div style="overflow: hidden; white-space: nowrap; text-overflow: ellipsis;">
                <strong>{slot['icon']} {slot['slot_label']}</strong>
                <br>
                <small style="opacity: 0.9">{slot['kind_label']}</small>
            </div>
            <div style="text-align: right; min-width: 80px;">
                <strong>{start_time} - {end_time}</strong>
                <br>
                <small>{slot['duration_min']} min</small>
            </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
    
    def _render_slots_list(self, slots_df: pd.DataFrame):
        """Render editable list of slots"""
        st.subheader("📋 Period Slots")
        
        if slots_df.empty:
            st.info("No slots defined yet")
            return
        
        st.caption("💡 Use Move Up/Down to reorder slots")
        
        for idx, slot in slots_df.iterrows():
            with st.expander(
                f"**{slot['slot_index']}.** {slot['icon']} {slot['slot_label']} ({slot['duration_min']} min)",
                expanded=False
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Code:** `{slot['slot_code']}`")
                    st.markdown(f"**Type:** {slot['kind_label']}")
                    st.markdown(f"**Duration:** {slot['duration_min']} min")
                with col2:
                    if slot['fixed_start_time']:
                        st.markdown(f"**Start:** {slot['fixed_start_time']}")
                    if slot['fixed_end_time']:
                        st.markdown(f"**End:** {slot['fixed_end_time']}")
                    st.markdown(f"**Teaching:** {'Yes' if slot['is_teaching_slot'] else 'No'}")
                
                if slot['notes']:
                    st.caption(f"📝 {slot['notes']}")
                
                # Actions
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    if st.button("✏️ Edit", key=f"edit_slot_{slot['id']}"):
                        st.session_state[f'editing_slot_{slot["id"]}'] = True
                        st.rerun()
                with col2:
                    if idx > 0:
                        if st.button("⬆️ Up", key=f"up_slot_{slot['id']}"):
                            self._move_slot_up(slots_df, idx)
                with col3:
                    if idx < len(slots_df) - 1:
                        if st.button("⬇️ Down", key=f"down_slot_{slot['id']}"):
                            self._move_slot_down(slots_df, idx)
                with col4:
                    if st.button("🗑️ Del", key=f"del_slot_{slot['id']}"):
                        if st.session_state.get(f'confirm_del_slot_{slot["id"]}'):
                            self.service.delete_slot(slot['id'])
                            st.success("Deleted!")
                            st.rerun()
                        else:
                            st.session_state[f'confirm_del_slot_{slot["id"]}'] = True
                            st.warning("Click again")
                
                if st.session_state.get(f'editing_slot_{slot["id"]}'):
                    self._render_edit_slot_form(slot)
    
    def _render_edit_slot_form(self, slot: pd.Series):
        """Form to edit a slot"""
        with st.form(f"edit_slot_{slot['id']}"):
            st.subheader("Edit Slot")
            
            label = st.text_input("Label", value=slot['slot_label'])
            
            # Duration is READ-ONLY in Edit mode too
            duration = st.number_input(
                "Duration (min)", 
                value=int(slot['duration_min']), 
                disabled=True, 
                help="Fixed by Period Type"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                current_start = None
                if slot['fixed_start_time']:
                    current_start = datetime.strptime(slot['fixed_start_time'], "%H:%M").time()
                
                start_time = st.time_input("Start Time", value=current_start)
            
            with col2:
                # Calculate End Time (Read Only)
                calculated_end = ""
                if start_time:
                    calculated_end = add_minutes_to_time(start_time.strftime("%H:%M"), duration)
                st.text_input("End Time (Auto)", value=calculated_end, disabled=True)
            
            notes = st.text_area("Notes", value=slot.get('notes', ''))
            
            col1, col2 = st.columns(2)
            with col1:
                save = st.form_submit_button("💾 Save Changes", type="primary")
            with col2:
                cancel = st.form_submit_button("Cancel")
            
            if save:
                self.service.update_slot(slot['id'], {
                    'label': label,
                    'duration': duration,
                    'start': start_time.strftime("%H:%M") if start_time else None,
                    'end': calculated_end if start_time else None,
                    'notes': notes
                })
                st.session_state[f'editing_slot_{slot["id"]}'] = False
                st.success("Saved!")
                st.rerun()
            
            if cancel:
                st.session_state[f'editing_slot_{slot["id"]}'] = False
                st.rerun()
    
    def _move_slot_up(self, slots_df: pd.DataFrame, current_idx: int):
        if current_idx == 0: return
        slots_list = slots_df['id'].tolist()
        slots_list[current_idx], slots_list[current_idx - 1] = slots_list[current_idx - 1], slots_list[current_idx]
        self.service.reorder_slots(self.template_id, slots_list)
        st.rerun()
    
    def _move_slot_down(self, slots_df: pd.DataFrame, current_idx: int):
        if current_idx >= len(slots_df) - 1: return
        slots_list = slots_df['id'].tolist()
        slots_list[current_idx], slots_list[current_idx + 1] = slots_list[current_idx + 1], slots_list[current_idx]
        self.service.reorder_slots(self.template_id, slots_list)
        st.rerun()
    
    def _render_add_slot_form(self, slots_df: pd.DataFrame):
        """Form to add new slot"""
        st.subheader("➕ Add Period Slot")
        
        kinds = self.service.fetch_period_kinds()
        if kinds.empty:
            st.warning("No period types defined.")
            return
        
        with st.form("add_slot"):
            next_index = len(slots_df) + 1
            suggested_code = f"P{next_index}"
            
            slot_code = st.text_input("Slot Code", value=suggested_code)
            slot_label = st.text_input("Slot Label", placeholder=f"Period {next_index}")
            
            # Select Type
            kind_code = st.selectbox(
                "Period Type",
                options=kinds['code'].tolist(),
                format_func=lambda x: f"{kinds[kinds['code'] == x]['icon'].iloc[0]} {kinds[kinds['code'] == x]['label'].iloc[0]}"
            )
            
            # Get default duration from selected kind
            default_duration = kinds[kinds['code'] == kind_code]['default_duration_min'].iloc[0]
            
            # Duration is READ-ONLY based on Type
            duration = st.number_input(
                "Duration (minutes)",
                value=int(default_duration),
                disabled=True,
                help="Duration is determined by the Period Type"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                suggested_start = None
                if not slots_df.empty:
                    last_slot = slots_df.iloc[-1]
                    if last_slot['fixed_end_time']:
                        suggested_start = datetime.strptime(last_slot['fixed_end_time'], "%H:%M").time()
                        
                start_time = st.time_input("Start Time (optional)", value=suggested_start)
            
            with col2:
                # End Time is READ-ONLY based on Start + Duration
                calculated_end = ""
                if start_time:
                    calculated_end = add_minutes_to_time(start_time.strftime("%H:%M"), duration)
                st.text_input("End Time (Auto)", value=calculated_end, disabled=True)
            
            notes = st.text_area("Notes (optional)")
            
            submitted = st.form_submit_button("Add Slot", type="primary")
            
            if submitted:
                if not slot_code or not slot_label:
                    st.error("Code and Label are required")
                else:
                    kind = kinds[kinds['code'] == kind_code].iloc[0]
                    try:
                        self.service.add_slot(self.template_id, {
                            'index': next_index,
                            'code': slot_code.upper(),
                            'label': slot_label,
                            'kind': kind_code,
                            'duration': duration,
                            'start': start_time.strftime("%H:%M") if start_time else None,
                            'end': calculated_end if start_time else None,
                            'is_teaching': 1 if kind['role'] == 'teaching' else 0,
                            'role': kind['role']
                        })
                        st.success(f"✅ Added slot '{slot_label}'")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

class WeekdayOverridesManager:
    """UI for managing weekday-specific structures"""
    
    def __init__(self, service: PeriodsDataService, template_id: int):
        self.service = service
        self.template_id = template_id
    
    def render(self):
        st.header("📅 Weekday Overrides")
        st.caption("Define different period structures for specific days (e.g., Saturday)")
        
        # Fetch existing overrides
        overrides_df = self.service.fetch_overrides(self.template_id)
        
        # Display existing overrides
        if not overrides_df.empty:
            st.subheader("Existing Overrides")
            
            for _, override in overrides_df.iterrows():
                self._render_override_card(override)
        
        st.divider()
        
        # Add new override
        self._render_add_override_form(overrides_df)
    
    def _render_override_card(self, override: pd.Series):
        """Render a single override"""
        with st.expander(
            f"📆 **{override['weekday']}** ({override['total_teaching_slots']} teaching slots, {override['total_teaching_minutes']} min)",
            expanded=False
        ):
            if override['override_reason']:
                st.caption(f"📝 {override['override_reason']}")
            
            # Fetch override slots
            slots_df = self.service.fetch_override_slots(override['id'])
            
            # Display slots
            st.markdown("**Periods:**")
            
            for _, slot in slots_df.iterrows():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.markdown(f"{slot['icon']} {slot['slot_label']}")
                
                with col2:
                    st.markdown(f"{slot['duration_min']} min")
                
                with col3:
                    times = ""
                    if slot['fixed_start_time']:
                        times = f"{slot['fixed_start_time']}"
                        if slot['fixed_end_time']:
                            times += f" - {slot['fixed_end_time']}"
                    st.markdown(times)
            
            # Delete override button
            if st.button("🗑️ Delete Override", key=f"del_override_{override['id']}"):
                if st.session_state.get(f'confirm_del_override_{override["id"]}'):
                    self.service.delete_override(override['id'])
                    st.success("Deleted!")
                    st.rerun()
                else:
                    st.session_state[f'confirm_del_override_{override["id"]}'] = True
                    st.warning("Click again to confirm deletion")
    
    def _render_add_override_form(self, overrides_df: pd.DataFrame):
        """Form to add new override"""
        st.subheader("➕ Add Weekday Override")
        
        # Filter out days that already have overrides
        existing_days = overrides_df['weekday'].tolist() if not overrides_df.empty else []
        available_days = [day for day in WEEKDAYS if day not in existing_days]
        
        if not available_days:
            st.info("All weekdays have overrides defined")
            return
        
        with st.form("add_override"):
            weekday = st.selectbox("Select Day", available_days)
            
            reason = st.text_area(
                "Reason for Override",
                placeholder="e.g., Saturday short day, Friday extended hours"
            )
            
            st.caption("💡 After creating the override, you'll be able to add periods to it")
            
            submitted = st.form_submit_button("Create Override", type="primary")
            
            if submitted:
                try:
                    override_id = self.service.create_override(
                        self.template_id,
                        weekday,
                        reason,
                        'user'
                    )
                    st.success(f"✅ Created override for {weekday}")
                    st.info("Now add periods to this override using the 'Manage Override Slots' button")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


class PreviewSummary:
    """Preview and validate template - IMPROVED VERSION with validation"""
    
    def __init__(self, service: PeriodsDataService, template_id: int):
        self.service = service
        self.template_id = template_id
    
    def render(self):
        st.header("👁️ Preview & Summary")
        
        # ============================================================================
        # FIX 1: Validate template exists and is not deleted
        # ============================================================================
        template = self.service.get_template_by_id(self.template_id)
        
        if not template:
            st.error("⚠️ Template not found! It may have been deleted.")
            st.info("Please go back to Template Manager and select a valid template.")
            
            if st.button("🔙 Back to Template Manager"):
                st.session_state['active_config_template_id'] = None
                st.rerun()
            return
        
        if template['status'] == 'deleted':
            st.error("⚠️ This template has been DELETED!")
            st.info("You cannot edit a deleted template. Please select a different template.")
            
            if st.button("🔙 Back to Template Manager"):
                st.session_state['active_config_template_id'] = None
                st.rerun()
            return
        
        # ============================================================================
        # Show template info
        # ============================================================================
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.info(f"**Template:** {template['template_name']}")
        
        with col2:
            status_colors = {
                'draft': 'orange',
                'published': 'green',
                'archived': 'gray'
            }
            status = template['status']
            color = status_colors.get(status, 'blue')
            st.markdown(f"**Status:** <span style='color:{color};'>{status.upper()}</span>", unsafe_allow_html=True)
        
        with col3:
            st.caption(f"Code: {template.get('template_code', 'N/A')}")
        
        st.divider()
        
        # Summary metrics
        slots_df = self.service.fetch_template_slots(self.template_id)
        overrides_df = self.service.fetch_overrides(self.template_id)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Slots", len(slots_df))
        
        with col2:
            teaching_slots = len(slots_df[slots_df['is_teaching_slot'] == 1]) if not slots_df.empty else 0
            st.metric("Teaching Slots", teaching_slots)
        
        with col3:
            total_minutes = slots_df['duration_min'].sum() if not slots_df.empty else 0
            st.metric("Total Duration", f"{total_minutes} min")
        
        with col4:
            st.metric("Weekday Overrides", len(overrides_df))
        
        st.divider()
        
        # Slot details
        if not slots_df.empty:
            st.subheader("📋 Default Day Structure")
            
            for _, slot in slots_df.iterrows():
                col1, col2, col3, col4 = st.columns([1, 3, 2, 2])
                
                with col1:
                    st.markdown(f"**P{slot['slot_index']}**")
                
                with col2:
                    icon = slot.get('icon', '📚')
                    st.markdown(f"{icon} {slot['slot_label']}")
                
                with col3:
                    if slot['fixed_start_time'] and slot['fixed_end_time']:
                        st.caption(f"{slot['fixed_start_time']} - {slot['fixed_end_time']}")
                    else:
                        st.caption(f"{slot['duration_min']} min")
                
                with col4:
                    role_colors = {
                        'teaching': 'green',
                        'break': 'orange',
                        'lunch': 'red',
                        'assembly': 'blue',
                        'buffer': 'gray',
                        'other': 'gray'
                    }
                    role = slot.get('role', 'teaching')
                    color = role_colors.get(role, 'gray')
                    st.markdown(f"<span style='color:{color}'>{role.title()}</span>", unsafe_allow_html=True)
        
        st.divider()
        
        # Weekday overrides
        if not overrides_df.empty:
            st.subheader("📅 Weekday Overrides")
            
            for _, override in overrides_df.iterrows():
                with st.expander(f"{override['weekday']} Override", expanded=False):
                    st.caption(f"Reason: {override.get('override_reason', 'N/A')}")
                    
                    override_slots = self.service.fetch_override_slots(override['id'])
                    if not override_slots.empty:
                        for _, slot in override_slots.iterrows():
                            st.markdown(f"- **P{slot['slot_index']}**: {slot['slot_label']} ({slot['duration_min']} min)")
        
        st.divider()
        
        # ============================================================================
        # Validation
        # ============================================================================
        self._render_validation(template, slots_df)
    
    def _render_validation(self, template, slots_df):
        """Validate template and show issues"""
        st.subheader("✅ Validation")
        
        issues = []
        warnings = []
        
        # Check if slots exist
        if slots_df.empty:
            issues.append("⚠️ No periods defined in default day structure")
        
        # Check for teaching slots
        teaching_slots = slots_df[slots_df['is_teaching_slot'] == 1]
        if not slots_df.empty and teaching_slots.empty:
            warnings.append("⚠️ No teaching periods defined - this template has only breaks/other periods")
        
        # Check time continuity
        if not slots_df.empty:
            has_fixed_times = not slots_df['fixed_start_time'].isna().all()
            if has_fixed_times:
                # Verify no gaps
                for i in range(len(slots_df) - 1):
                    current_end = slots_df.iloc[i]['fixed_end_time']
                    next_start = slots_df.iloc[i + 1]['fixed_start_time']
                    
                    if current_end and next_start and current_end != next_start:
                        warnings.append(
                            f"⚠️ Time gap between {slots_df.iloc[i]['slot_label']} "
                            f"({current_end}) and {slots_df.iloc[i + 1]['slot_label']} ({next_start})"
                        )
        
        # Display results
        if issues:
            st.error("Critical Issues:")
            for issue in issues:
                st.markdown(f"- {issue}")
        
        if warnings:
            st.warning("Warnings:")
            for warning in warnings:
                st.markdown(f"- {warning}")
        
        if not issues and not warnings:
            st.success("✅ No validation issues found")
        
        # Publish button
        if template['status'] == 'draft':
            st.info("💡 Template is in **Draft** status. Publish it to make it active for timetable creation.")
            
            if not issues:  # Only allow publishing if no critical issues
                if st.button("✅ Publish Template", type="primary"):
                    self.service.publish_template(self.template_id, 'user')
                    st.success("Template published!")
                    st.rerun()
            else:
                st.error("Cannot publish template with validation issues. Please fix the issues first.")
        elif template['status'] == 'published':
            st.success("✅ This template is published and active")
        elif template['status'] == 'archived':
            st.info("📦 This template is archived")


# ===================================================================
# MAIN APPLICATION
# ===================================================================

def main():
    """Main application entry point"""
    st.set_page_config(
        page_title="Periods Configuration",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🕐 Periods/Timegrid Configuration")
    st.caption("Define period structures per AY/Term with visual timeline")
    
    # Get engine
    from database.connection import get_engine
    engine = get_engine()
    
    # Initialize service
    service = PeriodsDataService(engine)
    
    # Sidebar navigation
    st.sidebar.header("Navigation")
    
    page = st.sidebar.radio(
        "Select Module",
        [
            "Period Types",
            "Template Manager",
            "Day Structure Builder",
            "Weekday Overrides",
            "Preview & Summary"
        ]
    )
    
    st.sidebar.divider()
    
    # Page routing
    if page == "Period Types":
        from periods_config_ui import PeriodKindsManager
        PeriodKindsManager(service).render()
    
    elif page == "Template Manager":
        from periods_config_ui import TemplateSelector
        template_id = TemplateSelector(service, engine).render()
        
        if template_id:
            st.session_state['active_template_id'] = template_id
            st.success(f"✅ Template selected (ID: {template_id})")
            st.info("💡 Now go to 'Day Structure Builder' to edit periods")
    
    elif page == "Day Structure Builder":
        template_id = st.session_state.get('active_template_id')
        
        if not template_id:
            st.warning("⚠️ Please select a template first in 'Template Manager'")
        else:
            DayStructureBuilder(service, template_id).render()
    
    elif page == "Weekday Overrides":
        template_id = st.session_state.get('active_template_id')
        
        if not template_id:
            st.warning("⚠️ Please select a template first in 'Template Manager'")
        else:
            WeekdayOverridesManager(service, template_id).render()
    
    elif page == "Preview & Summary":
        template_id = st.session_state.get('active_template_id')
        
        if not template_id:
            st.warning("⚠️ Please select a template first in 'Template Manager'")
        else:
            PreviewSummary(service, template_id).render()
    
    # Footer
    st.sidebar.divider()
    st.sidebar.caption("Periods Configuration v1.0")
    
    if st.session_state.get('active_template_id'):
        template = service.get_template_by_id(st.session_state['active_template_id'])
        if template:
            st.sidebar.info(f"**Active Template:**\n{template['template_name']}")


if __name__ == "__main__":
    main()
