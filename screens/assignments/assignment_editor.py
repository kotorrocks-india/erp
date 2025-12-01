# screens/timetable/assignment_editor.py
"""
Assignment Editor Component
Multi-tab form for creating and editing assignments.

Tabs:
1. Basic Info - Core assignment details
2. CO & Rubrics - Learning outcome mappings and rubrics
3. Submission - Submission types and file upload settings
4. Late & Extensions - Late policies and extension requests
5. Groups & Mentoring - Group work and mentoring configuration
6. Integrity - Plagiarism detection settings
7. Drop/Ignore - Class-wide drops and student excuses
"""

import streamlit as st
from datetime import datetime, date, time as dt_time, timedelta
from typing import Dict, Optional
import json


def render_editor(service, offering_id: int, offering: Dict):
    """Main editor render function."""
    
    # Check if editing existing assignment
    edit_id = st.session_state.get('edit_assignment_id')
    
    if edit_id:
        st.subheader(f"✏️ Edit Assignment")
        assignment = service.get_assignment(edit_id)
        
        if not assignment:
            st.error(f"Assignment {edit_id} not found")
            if st.button("« Back to List"):
                del st.session_state['edit_assignment_id']
                st.rerun()
            return
        
        render_edit_form(service, offering_id, offering, assignment)
        
        if st.button("« Back to List", key="back_from_edit"):
            del st.session_state['edit_assignment_id']
            st.rerun()
    
    else:
        st.subheader("➕ Create New Assignment")
        render_create_form(service, offering_id, offering)


def render_create_form(service, offering_id: int, offering: Dict):
    """Render creation form with tabs."""
    
    # Get next assignment number
    existing = service.list_assignments(offering_id=offering_id)
    next_number = max([a['number'] for a in existing], default=0) + 1
    
    # Tabs for different sections
    tab_basic, tab_co_rub, tab_submission, tab_late, tab_groups, tab_integrity, tab_drop = st.tabs([
        "📝 Basic",
        "🎯 CO & Rubrics",
        "📤 Submission",
        "⏰ Late & Extensions",
        "👥 Groups & Mentoring",
        "🔍 Integrity",
        "❌ Drop/Ignore"
    ])
    
    with st.form("create_assignment_form", clear_on_submit=False):
        
        # TAB 1: BASIC INFO
        with tab_basic:
            render_basic_fields(next_number, offering)
        
        # TAB 2: CO & RUBRICS
        with tab_co_rub:
            render_co_rubric_fields(offering_id)
        
        # TAB 3: SUBMISSION
        with tab_submission:
            render_submission_fields()
        
        # TAB 4: LATE & EXTENSIONS
        with tab_late:
            render_late_extension_fields()
        
        # TAB 5: GROUPS & MENTORING
        with tab_groups:
            render_groups_mentoring_fields()
        
        # TAB 6: INTEGRITY
        with tab_integrity:
            render_integrity_fields()
        
        # TAB 7: DROP/IGNORE
        with tab_drop:
            render_drop_ignore_fields()
        
        # Submit buttons
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            submit_draft = st.form_submit_button("💾 Save as Draft", use_container_width=True)
        
        with col2:
            submit_publish = st.form_submit_button("📤 Create & Publish", use_container_width=True, type="primary")
        
        with col3:
            if st.form_submit_button("🔄 Reset Form", use_container_width=True):
                st.rerun()
        
        # Handle submission
        if submit_draft or submit_publish:
            handle_create_submission(service, offering_id, offering, submit_publish)


def render_basic_fields(next_number: int, offering: Dict):
    """Render basic info fields."""
    st.write("### Basic Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        number = st.number_input(
            "Assignment Number *",
            min_value=1,
            value=next_number,
            help="Sequential number for this assignment",
            key="basic_number"
        )
        
        title = st.text_input(
            "Title *",
            placeholder="e.g., Quiz 1, Lab Report 2, Mid-Term Exam",
            help="Short descriptive title",
            key="basic_title"
        )
        
        bucket = st.selectbox(
            "Bucket *",
            ["Internal", "External"],
            help="Internal assessments or External exams",
            key="basic_bucket"
        )
    
    with col2:
        max_marks = st.number_input(
            "Max Marks (Raw) *",
            min_value=1.0,
            value=10.0,
            step=0.5,
            help="Maximum marks for this assignment (before scaling)",
            key="basic_max_marks"
        )
        
        due_date = st.date_input(
            "Due Date *",
            min_value=date.today(),
            value=date.today() + timedelta(days=7),
            key="basic_due_date"
        )
        
        due_time = st.time_input(
            "Due Time *",
            value=dt_time(23, 59),
            key="basic_due_time"
        )
    
    description = st.text_area(
        "Description / Instructions",
        height=120,
        placeholder="Enter detailed instructions, requirements, and guidelines for students...",
        help="Rich text description (supports markdown)",
        key="basic_description"
    )
    
    col_grace, col_visibility, col_results = st.columns(3)
    
    with col_grace:
        grace_minutes = st.number_input(
            "Grace Period (minutes)",
            min_value=0,
            value=15,
            help="Additional time after due date before marking as late",
            key="basic_grace"
        )
    
    with col_visibility:
        visibility = st.selectbox(
            "Student Visibility",
            ["Hidden", "Visible_Accepting", "Closed", "Results_Published"],
            help="Control when students can see and submit",
            key="basic_visibility"
        )
    
    with col_results:
        results_mode = st.selectbox(
            "Results Publish Mode",
            ["marks_and_rubrics", "pass_fail_only", "grade_pattern"],
            help="How to display results to students",
            key="basic_results_mode"
        )
    
    # Scaling info banner
    st.info(f"""
    📐 **Marks Scaling Info:**
    - {bucket} bucket max: {offering['internal_marks_max'] if bucket == 'Internal' else offering['exam_marks_max']}
    - Raw marks will be automatically scaled to match the offering's bucket maximum
    """)


def render_co_rubric_fields(offering_id: int):
    """Render CO mapping and rubric fields."""
    st.write("### Course Outcomes & Rubrics")
    
    # CO Mapping Section
    st.write("**CO Correlation Mapping**")
    st.info("Map this assignment to Course Outcomes using a 0-3 scale (0=None, 1=Low, 2=Medium, 3=High)")
    
    # Get available COs from subject_cos table
    try:
        from services.assignment_co_rubric_connector import AssignmentCORubricConnector
        from connection import get_engine
        
        connector = AssignmentCORubricConnector(get_engine())
        available_cos = connector.get_cos_for_offering(offering_id)
        
        if not available_cos:
            st.warning("⚠️ No COs defined for this offering. Please configure COs first.")
            st.info("Navigate to the Course Outcomes (CO) page to define COs for this subject.")
            st.session_state['co_mappings'] = {}
            return
        
        st.success(f"✅ Found {len(available_cos)} COs for this offering")
        
        # Display COs with mapping interface
        co_mappings = {}
        
        # Group COs in rows of 3
        for i in range(0, len(available_cos), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                if i + j < len(available_cos):
                    co = available_cos[i + j]
                    with col:
                        st.write(f"**{co['co_code']}**")
                        st.caption(co['title'][:50] + "..." if len(co['title']) > 50 else co['title'])
                        
                        co_value = st.select_slider(
                            f"{co['co_code']} Correlation",
                            options=[0, 1, 2, 3],
                            value=0,
                            format_func=lambda x: ["None", "Low", "Med", "High"][x],
                            key=f"co_value_{co['co_code']}",
                            label_visibility="collapsed"
                        )
                        co_mappings[co['co_code']] = co_value
        
        st.session_state['co_mappings'] = co_mappings
        
        # Check for at least one non-zero
        if not any(v > 0 for v in co_mappings.values()):
            st.warning("⚠️ At least one CO must have correlation > 0 before publishing")
        else:
            mapped_cos = [code for code, val in co_mappings.items() if val > 0]
            st.success(f"✅ Mapped to {len(mapped_cos)} CO(s): {', '.join(mapped_cos)}")
    
    except ImportError as e:
        st.error(f"Failed to load CO connector: {e}")
        st.info("Falling back to manual CO entry")
        
        # Fallback to manual entry
        num_cos = st.number_input("Number of COs to map", min_value=1, max_value=10, value=3, key="co_count")
        
        co_mappings = {}
        cols = st.columns(min(num_cos, 3))
        for i in range(num_cos):
            with cols[i % 3]:
                co_code = st.text_input(f"CO Code", value=f"CO{i+1}", key=f"co_code_{i}")
                co_value = st.select_slider(
                    f"{co_code} Correlation",
                    options=[0, 1, 2, 3],
                    value=0,
                    format_func=lambda x: ["None", "Low", "Med", "High"][x],
                    key=f"co_value_{i}"
                )
                co_mappings[co_code] = co_value
        
        st.session_state['co_mappings'] = co_mappings
        
        if not any(v > 0 for v in co_mappings.values()):
            st.warning("⚠️ At least one CO must have correlation > 0 before publishing")
    
    st.divider()
    
    # Rubrics Section
    st.write("**Rubric Attachment**")
    
    # Get available rubrics from rubric_criteria_catalog
    try:
        from services.assignment_co_rubric_connector import AssignmentCORubricConnector
        from connection import get_engine
        
        connector = AssignmentCORubricConnector(get_engine())
        
        # Get assignment context for filtering
        from context import get_context
        ctx = get_context()
        
        available_rubrics = connector.get_available_rubrics(
            degree_code=ctx.get('degree_code'),
            program_code=ctx.get('program_code'),
            branch_code=ctx.get('branch_code')
        )
        
        if not available_rubrics:
            st.warning("⚠️ No rubrics available. Please create rubrics in the Rubrics page first.")
            st.session_state['rubrics'] = []
            return
        
        st.info(f"📋 {len(available_rubrics)} rubric(s) available for selection")
        
    except Exception as e:
        st.error(f"Failed to load rubrics: {e}")
        available_rubrics = []
    
    rubric_mode = st.radio(
        "Rubric Mode",
        ["A - Single Rubric", "B - Multiple Rubrics with Weights"],
        help="Mode A: One rubric with internal criteria. Mode B: Mix multiple rubrics with top-level weights.",
        key="rubric_mode"
    )
    
    if "Single" in rubric_mode:
        # Mode A
        if available_rubrics:
            rubric_options = {
                f"{r['key']} - {r['label']}": r['id']
                for r in available_rubrics
            }
            
            selected_rubric = st.selectbox(
                "Select Rubric",
                options=list(rubric_options.keys()),
                key="rubric_a_select"
            )
            
            if selected_rubric:
                rubric_id = rubric_options[selected_rubric]
                rubric_version = st.text_input("Version (optional)", key="rubric_a_version")
                
                st.session_state['rubrics'] = [{
                    "mode": "A",
                    "rubric_id": rubric_id,
                    "rubric_version": rubric_version,
                    "weight": 100.0
                }]
        else:
            # Fallback to manual entry
            rubric_id = st.number_input("Rubric ID", min_value=1, key="rubric_a_id")
            rubric_version = st.text_input("Version (optional)", key="rubric_a_version")
            
            st.session_state['rubrics'] = [{
                "mode": "A",
                "rubric_id": rubric_id,
                "rubric_version": rubric_version,
                "weight": 100.0
            }]
    else:
        # Mode B
        num_rubrics = st.number_input("Number of Rubrics", min_value=1, max_value=5, value=2, key="rubric_b_count")
        
        rubrics = []
        total_weight = 0
        
        for i in range(num_rubrics):
            with st.expander(f"Rubric #{i+1}", expanded=True):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    if available_rubrics:
                        rubric_options = {
                            f"{r['key']} - {r['label']}": r['id']
                            for r in available_rubrics
                        }
                        
                        selected = st.selectbox(
                            f"Select Rubric",
                            options=list(rubric_options.keys()),
                            key=f"rubric_b_{i}_select"
                        )
                        rub_id = rubric_options[selected] if selected else 1
                    else:
                        rub_id = st.number_input(f"Rubric ID", min_value=1, key=f"rubric_b_{i}_id")
                
                with col2:
                    rub_ver = st.text_input(f"Version", key=f"rubric_b_{i}_ver")
                
                with col3:
                    rub_weight = st.number_input(f"Weight %", min_value=0.0, max_value=100.0, value=50.0, key=f"rubric_b_{i}_weight")
                
                rubrics.append({
                    "mode": "B",
                    "rubric_id": rub_id,
                    "rubric_version": rub_ver,
                    "weight": rub_weight
                })
                total_weight += rub_weight
        
        st.session_state['rubrics'] = rubrics
        
        if abs(total_weight - 100.0) > 0.01:
            st.error(f"❌ Mode B weights must sum to 100% (currently: {total_weight}%)")
        else:
            st.success(f"✅ Weights sum to {total_weight}%")


def render_submission_fields():
    """Render submission configuration fields."""
    st.write("### Submission Configuration")
    
    submission_types = st.multiselect(
        "Submission Types *",
        ["MCQ", "File Upload", "Presentation", "Physical/Studio/Jury", "Viva/Test", "Custom"],
        default=["File Upload"],
        help="Select all applicable submission methods",
        key="sub_types"
    )
    
    if "File Upload" in submission_types:
        st.write("**File Upload Settings**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            multiple_files = st.checkbox("Allow Multiple Files", value=True, key="sub_multiple")
            max_file_mb = st.number_input("Max File Size (MB)", min_value=1, max_value=2048, value=100, key="sub_max_mb")
        
        with col2:
            allowed_types = st.multiselect(
                "Allowed File Types",
                ["pdf", "pptx", "docx", "xlsx", "jpg", "png", "zip", "txt", "csv"],
                default=["pdf", "pptx", "docx", "xlsx", "jpg", "png", "zip"],
                key="sub_allowed_types"
            )
        
        storage = st.selectbox(
            "Storage Method",
            ["local_signed_url", "cloud_later"],
            help="How files will be stored",
            key="sub_storage"
        )
        
        st.session_state['file_upload_config'] = {
            "multiple_files": multiple_files,
            "max_file_mb": max_file_mb,
            "allowed_types": allowed_types,
            "storage": storage
        }
    
    st.session_state['submission_types'] = submission_types


def render_late_extension_fields():
    """Render late policy and extension fields."""
    st.write("### Late Submission Policy")
    
    late_mode = st.selectbox(
        "Late Policy Mode",
        ["allow_with_penalty", "no_late", "allow_until_cutoff"],
        format_func=lambda x: {
            "allow_with_penalty": "Allow with Penalty",
            "no_late": "No Late Submissions",
            "allow_until_cutoff": "Allow Until Cutoff"
        }[x],
        key="late_mode"
    )
    
    if late_mode == "allow_with_penalty":
        col1, col2 = st.columns(2)
        with col1:
            penalty_per_day = st.number_input(
                "Penalty % per Day",
                min_value=0.0,
                max_value=100.0,
                value=10.0,
                help="Percentage deducted per day late",
                key="late_penalty_day"
            )
        with col2:
            penalty_cap = st.number_input(
                "Penalty Cap %",
                min_value=0.0,
                max_value=100.0,
                value=50.0,
                help="Maximum total penalty",
                key="late_penalty_cap"
            )
    elif late_mode == "allow_until_cutoff":
        cutoff_date = st.date_input("Hard Cutoff Date", key="late_cutoff_date")
        cutoff_time = st.time_input("Hard Cutoff Time", key="late_cutoff_time")
        penalty_per_day = st.number_input("Penalty % per Day", min_value=0.0, max_value=100.0, value=10.0, key="late_penalty_day2")
        penalty_cap = 100.0
    else:
        penalty_per_day = 0
        penalty_cap = 0
    
    st.session_state['late_policy'] = {
        "mode": late_mode,
        "penalty_percent_per_day": penalty_per_day,
        "penalty_cap_percent": penalty_cap,
        "hard_cutoff_at": None  # Set from cutoff_date/time if applicable
    }
    
    st.divider()
    
    # Extensions
    st.write("### Extension Requests")
    
    extensions_allowed = st.checkbox("Allow Extension Requests", value=True, key="ext_allowed")
    
    if extensions_allowed:
        col1, col2 = st.columns(2)
        with col1:
            require_reason = st.checkbox("Require Reason", value=True, key="ext_reason")
        with col2:
            pd_approval = st.checkbox("PD Approval Required (after publish)", value=True, key="ext_pd")
        
        st.session_state['extensions_config'] = {
            "allowed": extensions_allowed,
            "require_reason": require_reason,
            "pd_approval_required_after_publish": pd_approval
        }


def render_groups_mentoring_fields():
    """Render group work and mentoring fields."""
    st.write("### Group Work")
    
    group_enabled = st.checkbox("Enable Group Submissions", value=False, key="group_enabled")
    
    if group_enabled:
        col1, col2, col3 = st.columns(3)
        with col1:
            grouping_model = st.selectbox("Grouping Model", ["free_form"], key="group_model")
        with col2:
            min_size = st.number_input("Min Group Size", min_value=2, value=2, key="group_min")
        with col3:
            max_size = st.number_input("Max Group Size", min_value=2, value=4, key="group_max")
        
        st.session_state['group_config'] = {
            "enabled": group_enabled,
            "grouping_model": grouping_model,
            "min_size": min_size,
            "max_size": max_size
        }
    else:
        st.session_state['group_config'] = {"enabled": False}
    
    st.divider()
    
    # Mentoring
    st.write("### Mentoring")
    
    col1, col2 = st.columns(2)
    with col1:
        mentor_enabled_subject = st.checkbox("Enable Mentoring (Subject Level)", value=True, key="mentor_subject")
        mentor_enabled_assignment = st.checkbox("Enable Mentoring (Assignment Level)", value=True, key="mentor_assignment")
    with col2:
        mentors_from_faculty = st.checkbox("Mentors from Subject Faculty", value=True, key="mentor_faculty")
        multiple_mentors = st.checkbox("Allow Multiple Mentors per Student", value=True, key="mentor_multiple")
    
    st.session_state['mentoring_config'] = {
        "enabled_at_subject": mentor_enabled_subject,
        "enabled_at_assignment": mentor_enabled_assignment,
        "mentors_from_subject_faculty": mentors_from_faculty,
        "multiple_mentors_per_student": multiple_mentors
    }


def render_integrity_fields():
    """Render plagiarism/integrity fields."""
    st.write("### Academic Integrity / Plagiarism Detection")
    
    plag_enabled = st.checkbox("Enable Plagiarism Detection", value=True, key="plag_enabled")
    
    if plag_enabled:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            warn_threshold = st.number_input(
                "Warning Threshold %",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                help="Show warning if similarity exceeds this",
                key="plag_warn"
            )
        
        with col2:
            block_threshold = st.number_input(
                "Block Threshold %",
                min_value=0.0,
                max_value=100.0,
                value=40.0,
                help="Block submission if similarity exceeds this",
                key="plag_block"
            )
        
        with col3:
            exclude_bib = st.checkbox(
                "Exclude Bibliography",
                value=True,
                help="Don't count bibliography/references in similarity",
                key="plag_excl_bib"
            )
        
        st.session_state['plagiarism_config'] = {
            "enabled": plag_enabled,
            "similarity_score": None,
            "warn_threshold_percent": warn_threshold,
            "block_threshold_percent": block_threshold,
            "exclude_bibliography_flag": exclude_bib
        }
    else:
        st.session_state['plagiarism_config'] = {"enabled": False}


def render_drop_ignore_fields():
    """Render drop/ignore policy fields."""
    st.write("### Drop / Ignore Policy")
    
    st.info("""
    - **Class-Wide Drop**: Removes assignment from all students' calculations (requires PD approval)
    - **Per-Student Excuse**: Allows individual students to be excused from this assignment
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        class_drop = st.checkbox("Request Class-Wide Drop", value=False, key="drop_class")
        if class_drop:
            drop_reason = st.text_area("Reason for Class-Wide Drop", key="drop_reason")
        else:
            drop_reason = ""
    
    with col2:
        per_student_excuse = st.checkbox("Allow Per-Student Excuses", value=True, key="drop_student")
    
    st.session_state['drop_config'] = {
        "class_wide_drop_requested": class_drop,
        "class_wide_drop_reason": drop_reason,
        "per_student_excuse_allowed": per_student_excuse
    }


def handle_create_submission(service, offering_id: int, offering: Dict, publish: bool):
    """Handle form submission."""
    
    # Validate required fields
    title = st.session_state.get('basic_title', '').strip()
    if not title:
        st.error("❌ Title is required")
        return
    
    number = st.session_state.get('basic_number')
    if not number:
        st.error("❌ Assignment number is required")
        return
    
    # Build due datetime
    try:
        due_date = st.session_state.get('basic_due_date')
        due_time = st.session_state.get('basic_due_time')
        due_at = datetime.combine(due_date, due_time)
    except Exception as e:
        st.error(f"❌ Invalid due date/time: {e}")
        return
    
    # Validate CO mappings
    co_mappings = st.session_state.get('co_mappings', {})
    if not any(v > 0 for v in co_mappings.values()):
        st.error("❌ At least one CO must have correlation > 0")
        return
    
    # Validate rubrics (Mode B)
    rubrics = st.session_state.get('rubrics', [])
    mode_b_rubrics = [r for r in rubrics if r.get('mode') == 'B']
    if mode_b_rubrics:
        total_weight = sum(r.get('weight', 0) for r in mode_b_rubrics)
        if abs(total_weight - 100.0) > 0.01:
            st.error(f"❌ Mode B rubric weights must sum to 100% (currently: {total_weight}%)")
            return
    
    try:
        # Create assignment
        assignment_id = service.create_assignment(
            offering_id=offering_id,
            number=number,
            title=title,
            bucket=st.session_state.get('basic_bucket'),
            max_marks=st.session_state.get('basic_max_marks'),
            due_at=due_at,
            description=st.session_state.get('basic_description', ''),
            grace_minutes=st.session_state.get('basic_grace', 15),
            visibility_state=st.session_state.get('basic_visibility', 'Hidden'),
            results_publish_mode=st.session_state.get('basic_results_mode', 'marks_and_rubrics'),
            submission_config={
                "types": st.session_state.get('submission_types', []),
                "file_upload": st.session_state.get('file_upload_config', {})
            },
            late_policy=st.session_state.get('late_policy', {}),
            extensions_config=st.session_state.get('extensions_config', {}),
            group_config=st.session_state.get('group_config', {}),
            mentoring_config=st.session_state.get('mentoring_config', {}),
            plagiarism_config=st.session_state.get('plagiarism_config', {}),
            drop_config=st.session_state.get('drop_config', {}),
            status='draft',
            actor='current_user',
            actor_role='subject_in_charge'
        )
        
        # Add CO mappings
        for co_code, value in co_mappings.items():
            if value > 0:
                service.add_co_mapping(assignment_id, co_code, value)
        
        # Attach rubrics
        for idx, rubric in enumerate(rubrics):
            service.attach_rubric(
                assignment_id,
                rubric['rubric_id'],
                rubric_mode=rubric.get('mode', 'A'),
                top_level_weight=rubric.get('weight', 100.0),
                rubric_version=rubric.get('rubric_version')
            )
        
        st.success(f"✅ Created assignment #{number} - {title}")
        
        # Publish if requested
        if publish:
            service.publish_assignment(
                assignment_id,
                'current_user',
                'principal',
                'Initial publish from creation'
            )
            st.success("📤 Published successfully")
        
        st.balloons()
        
        # Clear session state
        for key in list(st.session_state.keys()):
            if key.startswith('basic_') or key.startswith('co_') or key.startswith('sub_') or \
               key.startswith('late_') or key.startswith('ext_') or key.startswith('group_') or \
               key.startswith('mentor_') or key.startswith('plag_') or key.startswith('drop_') or \
               key.startswith('rubric_'):
                del st.session_state[key]
        
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Failed to create assignment: {e}")
        import traceback
        with st.expander("Error Details"):
            st.code(traceback.format_exc())


def render_edit_form(service, offering_id: int, offering: Dict, assignment: Dict):
    """Render edit form for existing assignment."""
    st.info("Edit form - feature in progress. Currently showing assignment details:")
    st.json(assignment)


if __name__ == "__main__":
    st.write("This module should be imported, not run directly.")
