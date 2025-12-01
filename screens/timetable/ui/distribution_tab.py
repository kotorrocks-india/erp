"""
Distribution Tab - ENHANCED with Audit Trail & Saved Distributions List
Features:
- Configure Distribution (existing)
- View Saved Distributions (new)
- Audit Trail (new)
- Import/Export
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import List, Optional
import sys
from pathlib import Path


class DistributionTab:
    """Handles the Subject Distribution tab UI with Audit & History"""
    
    def __init__(self, ctx, engine: Engine):
        self.ctx = ctx
        self.engine = engine
        
        if 'last_saved' not in st.session_state:
            st.session_state['last_saved'] = {}
    
    def render(self):
        """Render the distribution tab"""
        st.header("📋 Weekly Subject Distribution")
        st.caption("Define weekly frequency for each subject")
        
        # Display context
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"Editing: {self.ctx.degree} - Y{self.ctx.year} Term {self.ctx.term} (Div {self.ctx.division})")
        with col2:
            if st.button("🔄 Refresh"):
                st.cache_data.clear()
                st.rerun()
        
        st.divider()
        
        # Create tabs
        tabs = st.tabs([
            "🔧 Configure Distribution",
            "📊 Saved Distributions", 
            "📜 Audit Trail",
            "📥📤 Import/Export"
        ])
        
        with tabs[0]:
            self._render_distribution_tab()
        
        with tabs[1]:
            self._render_saved_distributions_tab()
        
        with tabs[2]:
            self._render_audit_trail_tab()
        
        with tabs[3]:
            self._render_import_export_tab()
    
    # ========================================================================
    # TAB 1: CONFIGURE DISTRIBUTION
    # ========================================================================
    
    def _render_distribution_tab(self):
        """Render the main distribution configuration"""
        offerings = self._fetch_offerings()
        
        if offerings.empty:
            st.warning("⚠️ No subject offerings found. Please configure Subject Offerings first.")
            return

        distributions = self._fetch_distributions()
        
        self._render_subject_cards(offerings, distributions)
    
    def _fetch_offerings(self) -> pd.DataFrame:
        """Fetch subject offerings and expand elective topics.

        Credits are read from subjects_catalog (student_credits / teaching_credits),
        weekly distribution only mirrors them – it is not the source of truth.
        """
        with self.engine.connect() as conn:
            offerings = pd.read_sql(
                text("""
                    SELECT 
                        o.id as offering_id,
                        o.subject_code,
                        sc.subject_name,
                        COALESCE(sc.subject_type, 'Core') as subject_type,
                        COALESCE(sc.credits_total, 0) as credits,
                        COALESCE(sc.student_credits, sc.credits_total, 0) as student_credits,
                        COALESCE(sc.teaching_credits, sc.credits_total, 0) as teaching_credits
                    FROM subject_offerings o
                    LEFT JOIN subjects_catalog sc 
                        ON sc.subject_code = o.subject_code 
                        AND sc.degree_code = o.degree_code
                        AND (sc.program_code IS NULL OR sc.program_code = o.program_code)
                        AND (sc.branch_code IS NULL OR sc.branch_code = o.branch_code)
                    WHERE o.ay_label = :ay 
                      AND o.degree_code = :deg 
                      AND o.year = :yr 
                      AND o.term = :term
                      AND (:prog IS NULL OR o.program_code = :prog OR o.program_code IS NULL)
                      AND (:branch IS NULL OR o.branch_code = :branch OR o.branch_code IS NULL)
                    ORDER BY sc.subject_type, o.subject_code
                """),
                conn, 
                params=self.ctx.to_dict()
            )
            
            if offerings.empty:
                return pd.DataFrame()
            
            expanded_rows = []
            
            for _, offering in offerings.iterrows():
                # Check for elective topics
                topics = pd.read_sql(
                    text("""
                        SELECT 
                            t.id as topic_id,
                            t.topic_code_ay,
                            t.topic_name,
                            t.offering_id as topic_offering_id,
                            t.status as topic_status
                        FROM elective_topics t
                        WHERE t.subject_code = :subj_code
                          AND t.ay_label = :ay
                          AND t.year = :yr
                          AND t.term = :term
                          AND (:div IS NULL OR t.division_code = :div OR t.division_code IS NULL)
                          AND t.status IN ('draft', 'published')
                        ORDER BY t.topic_no
                    """),
                    conn, 
                    params={
                        'subj_code': offering['subject_code'],
                        'ay': self.ctx.ay,
                        'yr': self.ctx.year,
                        'term': self.ctx.term,
                        'div': self.ctx.division
                    }
                )
                
                if not topics.empty:
                    # Expand into topics
                    for _, topic in topics.iterrows():
                        expanded_rows.append({
                            'offering_id': topic['topic_offering_id'] if pd.notna(topic['topic_offering_id']) else offering['offering_id'],
                            'subject_code': topic['topic_code_ay'],
                            'subject_name': topic['topic_name'], 
                            'subject_type': offering['subject_type'],
                            'credits': offering['credits'],
                            'student_credits': offering['student_credits'],
                            'teaching_credits': offering['teaching_credits'],
                            'is_elective_topic': True,
                            'needs_topic_creation': False
                        })
                else:
                    # Check if likely elective
                    needs_topics = offering['subject_type'] in ('Elective', 'Open Elective', 'Program Elective', 'College Project')
                    
                    expanded_rows.append({
                        'offering_id': offering['offering_id'],
                        'subject_code': offering['subject_code'],
                        'subject_name': offering['subject_name'],
                        'subject_type': offering['subject_type'],
                        'credits': offering['credits'],
                        'student_credits': offering['student_credits'],
                        'teaching_credits': offering['teaching_credits'],
                        'is_elective_topic': False,
                        'needs_topic_creation': needs_topics
                    })
            
            return pd.DataFrame(expanded_rows) if expanded_rows else pd.DataFrame()
    
    def _fetch_distributions(self) -> pd.DataFrame:
        """Fetch existing distributions for current context.

        Uses NULL-friendly division logic:
        - If ctx.division is None → fetch all divisions for this AY/degree/year/term
        - If ctx.division has a value → fetch only that division
        """
        params = self.ctx.to_dict()
        with self.engine.connect() as conn:
            if self.ctx.division is None:
                return pd.read_sql(
                    text("""
                        SELECT * FROM weekly_subject_distribution
                        WHERE ay_label = :ay 
                          AND degree_code = :deg 
                          AND year = :yr 
                          AND term = :term
                    """),
                    conn,
                    params=params
                )
            else:
                return pd.read_sql(
                    text("""
                        SELECT * FROM weekly_subject_distribution
                        WHERE ay_label = :ay 
                          AND degree_code = :deg 
                          AND year = :yr 
                          AND term = :term
                          AND division_code = :div
                    """),
                    conn,
                    params=params
                )
    
    def _render_subject_cards(self, offerings: pd.DataFrame, distributions: pd.DataFrame):
        """Render each subject as an expandable card"""
        
        if not distributions.empty:
            merged = offerings.merge(
                distributions[[
                    'offering_id', 'student_credits', 'teaching_credits',
                    'duration_type', 'weekly_frequency',
                    'is_all_day_elective_block', 'room_code',
                    'module_start_date', 'module_end_date'
                ]],
                on='offering_id',
                how='left'
            )
        else:
            merged = offerings.copy()
            merged['student_credits'] = merged['credits']
            merged['teaching_credits'] = merged['credits']
            merged['duration_type'] = 'full_term'
            merged['weekly_frequency'] = 1
            merged['is_all_day_elective_block'] = 0
            merged['room_code'] = ''
            merged['module_start_date'] = None
            merged['module_end_date'] = None

        if merged.empty:
            st.info("No subject offerings found for this context.")
            return

        # Attach a row id so Streamlit keys can be unique even if
        # offering_id + subject_code repeats (e.g. due to topics)
        for idx, row in merged.iterrows():
            subject = row.copy()
            subject["_row_id"] = idx
            self._render_subject_card(subject)
        
    def _render_subject_card(self, subject: pd.Series):
        """Render a single subject card"""

        # If this is an elective parent without topics, just show the warning expander
        if subject.get('needs_topic_creation', False):
            with st.expander(
                f"⚠️ **{subject['subject_code']}** - {subject['subject_name']}",
                expanded=False
            ):
                st.warning(
                    f"**Topics Required:** '{subject['subject_name']}' is an Elective Parent, "
                    "but no topics created yet.\n\n"
                    "Please go to the **Electives Module** to create topics."
                )
            return

        # Icon + label suffix
        icon = (
            "🌍"
            if subject.get('is_all_day_elective_block', 0) == 1
            else ("📘" if subject.get('is_elective_topic', False) else "📗")
        )
        label_suffix = (
            " (All-Day)"
            if subject.get('is_all_day_elective_block', 0) == 1
            else (" (Topic)" if subject.get('is_elective_topic', False) else "")
        )

        row_id = subject.get("_row_id", subject.name if hasattr(subject, "name") else "")
        safe_code = str(subject['subject_code']).replace('-', '_').replace(' ', '_')
        key_base = f"{subject['offering_id']}_{safe_code}_{row_id}"

        with st.expander(
            f"{icon} **{subject['subject_code']}** - {subject['subject_name']}{label_suffix}",
            expanded=False
        ):
            col1, col2, col3 = st.columns(3)

            # Safe credits
            stu_raw = subject.get('student_credits', subject.get('credits', 0))
            teach_raw = subject.get('teaching_credits', subject.get('credits', 0))
            if pd.isna(stu_raw):
                stu_raw = subject.get('credits', 0)
            if pd.isna(teach_raw):
                teach_raw = subject.get('credits', 0)

            with col1:
                st.metric("Student Credits", f"{float(stu_raw):.1f}")
            with col2:
                st.metric("Teaching Credits", f"{float(teach_raw):.1f}")
            with col3:
                duration_type = subject.get('duration_type', 'full_term')
                st.metric(
                    "Type",
                    "📅 Module" if duration_type == 'module' else "📆 Full Term"
                )

            st.markdown("---")

            col1, col2 = st.columns(2)

            # Left side: module toggle, weekly frequency, room
            with col1:
                is_module = st.checkbox(
                    "This is a Module (limited weeks)",
                    value=subject.get('duration_type', 'full_term') == 'module',
                    key=f"is_module_{key_base}",
                )

                # NaN-safe weekly frequency
                raw_weekly_freq = subject.get("weekly_frequency", 1)
                if pd.isna(raw_weekly_freq):
                    raw_weekly_freq = 1
                try:
                    weekly_freq_default = int(raw_weekly_freq)
                except (TypeError, ValueError):
                    weekly_freq_default = 1

                weekly_freq = st.number_input(
                    "Weekly Frequency",
                    min_value=1,
                    max_value=7,
                    value=weekly_freq_default,
                    key=f"freq_{key_base}",
                    step=1,
                )

                room = st.text_input(
                    "Preferred Room",
                    value=str(subject.get('room_code', '') or ''),
                    key=f"room_{key_base}",
                )

            # Right side: all-day flag + Dates (Always Visible)
            with col2:
                is_all_day = st.checkbox(
                    "All-Day Module/Block",
                    value=bool(subject.get('is_all_day_elective_block', 0)),
                    key=f"allday_{key_base}",
                )

                # CHANGE: Dates are now shown regardless of is_module status
                # Optional caption to explain usage for Full Term
                if not is_module:
                    st.caption("Specific Dates (Optional for Full Term overrides)")

                c1, c2 = st.columns(2)
                with c1:
                    if pd.notna(subject.get('module_start_date')):
                        start_default = pd.to_datetime(
                            subject.get('module_start_date')
                        )
                    else:
                        start_default = None

                    start_date = st.date_input(
                        "Start Date",
                        value=start_default,
                        key=f"start_{key_base}",
                    )

                with c2:
                    if pd.notna(subject.get('module_end_date')):
                        end_default = pd.to_datetime(
                            subject.get('module_end_date')
                        )
                    else:
                        end_default = None

                    end_date = st.date_input(
                        "End Date",
                        value=end_default,
                        key=f"end_{key_base}",
                    )

            if is_all_day:
                st.info("ℹ️ All-Day modules handled separately in Timetable tab")
            else:
                st.caption(
                    f"ℹ️ Occurs {weekly_freq}x/week. "
                    "Period assignment in Timetable tab."
                )

            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("💾 Save", key=f"save_{key_base}", type='primary'):
                    self._save_distribution(
                        subject,
                        is_module,
                        weekly_freq,
                        is_all_day,
                        room,
                        start_date,
                        end_date,
                    )
                    
    def _save_distribution(self, subject, is_module, weekly_frequency, is_all_day, room, start_date, end_date):
        """Save distribution to database with audit.

        Uses NULL-friendly division logic aligned with import/export service.
        """
        
        if is_module and (start_date is None or end_date is None):
            st.error("Module requires both start and end dates")
            return
        
        if start_date and end_date and start_date >= end_date:
            st.error("Start date must be before end date")
            return          
        try:
            with self.engine.begin() as conn:
                if self.ctx.division is None:
                    existing = conn.execute(
                        text("""
                            SELECT id 
                            FROM weekly_subject_distribution 
                            WHERE offering_id = :oid
                              AND division_code IS NULL
                            LIMIT 1
                        """),
                        {'oid': int(subject['offering_id'])}
                    ).fetchone()
                else:
                    existing = conn.execute(
                        text("""
                            SELECT id 
                            FROM weekly_subject_distribution 
                            WHERE offering_id = :oid
                              AND division_code = :div
                            LIMIT 1
                        """),
                        {
                            'oid': int(subject['offering_id']),
                            'div': self.ctx.division
                        }
                    ).fetchone()
                
                params = {
                    'oid': int(subject['offering_id']),
                    'ay': self.ctx.ay,
                    'deg': self.ctx.degree,
                    'prog': self.ctx.program,
                    'branch': self.ctx.branch,
                    'yr': self.ctx.year,
                    'term': self.ctx.term,
                    'div': self.ctx.division,
                    'subj_code': subject['subject_code'],
                    'subj_type': subject['subject_type'],
                    # mirror credits from catalog / existing row, not source of truth
                    'stu_cred': float(subject.get('student_credits', subject.get('credits', 0))),
                    'teach_cred': float(subject.get('teaching_credits', subject.get('credits', 0))),
                    'duration_type': 'module' if is_module else 'full_term',
                    'weekly_freq': int(weekly_frequency),
                    'is_all_day': 1 if is_all_day else 0,
                    'room': room if room else None,
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None,
                }
                
                if existing:
                    conn.execute(
                        text("""
                            UPDATE weekly_subject_distribution SET
                                student_credits = :stu_cred,
                                teaching_credits = :teach_cred,
                                duration_type = :duration_type,
                                weekly_frequency = :weekly_freq,
                                is_all_day_elective_block = :is_all_day,
                                room_code = :room,
                                module_start_date = :start_date,
                                module_end_date = :end_date,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                        """),
                        {**params, 'id': existing[0]}
                    )
                    action = "Updated"
                    dist_id = existing[0]
                else:
                    conn.execute(
                        text("""
                            INSERT INTO weekly_subject_distribution (
                                offering_id, ay_label, degree_code, program_code, branch_code,
                                year, term, division_code, subject_code, subject_type,
                                student_credits, teaching_credits,
                                duration_type, weekly_frequency,
                                is_all_day_elective_block, room_code,
                                module_start_date, module_end_date,
                                mon_periods, tue_periods, wed_periods, 
                                thu_periods, fri_periods, sat_periods
                            ) VALUES (
                                :oid, :ay, :deg, :prog, :branch,
                                :yr, :term, :div, :subj_code, :subj_type,
                                :stu_cred, :teach_cred,
                                :duration_type, :weekly_freq,
                                :is_all_day, :room,
                                :start_date, :end_date,
                                0, 0, 0, 0, 0, 0
                            )
                        """),
                        params
                    )
                    action = "Created"
                    dist_id = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]
                
                # Audit trail
                conn.execute(
                    text("""
                        INSERT INTO weekly_subject_distribution_audit 
                        (distribution_id, offering_id, ay_label, degree_code, division_code, 
                         change_reason, changed_by, changed_at)
                        VALUES (:did, :oid, :ay, :deg, :div, :reason, :actor, CURRENT_TIMESTAMP)
                    """),
                    {
                        'did': dist_id,
                        'oid': params['oid'],
                        'ay': self.ctx.ay,
                        'deg': self.ctx.degree,
                        'div': self.ctx.division,
                        'reason': f"{action} distribution for {subject['subject_code']} - {weekly_frequency}x/week",
                        'actor': 'user'
                    }
                )
            
            st.success(f"✅ {action} {subject['subject_code']} - {weekly_frequency}x/week")
            st.cache_data.clear()
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Save failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    
    # ========================================================================
    # TAB 2: SAVED DISTRIBUTIONS LIST
    # ========================================================================
    
    def _render_saved_distributions_tab(self):
        """Render list of all saved distributions"""
        st.subheader("📊 Saved Distributions")
        st.caption(f"All configured distributions for {self.ctx.degree} Y{self.ctx.year}T{self.ctx.term} Div {self.ctx.division}")
        
        distributions = self._fetch_distributions()
        
        if distributions.empty:
            st.info("ℹ️ No distributions configured yet. Go to 'Configure Distribution' tab to add subjects.")
            return
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Subjects", len(distributions))
        
        with col2:
            full_term_count = len(distributions[distributions['duration_type'] == 'full_term'])
            st.metric("Full Term", full_term_count)
        
        with col3:
            module_count = len(distributions[distributions['duration_type'] == 'module'])
            st.metric("Modules", module_count)
        
        with col4:
            all_day_count = len(distributions[distributions['is_all_day_elective_block'] == 1])
            st.metric("All-Day Blocks", all_day_count)
        
        st.divider()
        
        # Filters
        col1, col2 = st.columns(2)
        
        with col1:
            filter_type = st.multiselect(
                "Filter by Type",
                options=distributions['subject_type'].unique().tolist(),
                default=distributions['subject_type'].unique().tolist()
            )
        
        with col2:
            filter_duration = st.multiselect(
                "Filter by Duration",
                options=['full_term', 'module'],
                default=['full_term', 'module'],
                format_func=lambda x: "Full Term" if x == 'full_term' else "Module"
            )
        
        # Apply filters
        filtered = distributions[
            (distributions['subject_type'].isin(filter_type)) &
            (distributions['duration_type'].isin(filter_duration))
        ]
        
        if filtered.empty:
            st.warning("No distributions match the selected filters")
            return
        
        # Display table
        display_cols = [
            'subject_code', 'subject_type', 'weekly_frequency', 
            'duration_type', 'is_all_day_elective_block', 'room_code',
            'module_start_date', 'module_end_date', 'updated_at'
        ]
        
        display_df = filtered[display_cols].copy()
        display_df['is_all_day_elective_block'] = display_df['is_all_day_elective_block'].map({0: 'No', 1: 'Yes'})
        display_df['duration_type'] = display_df['duration_type'].map({'full_term': 'Full Term', 'module': 'Module'})
        display_df = display_df.fillna('')
        
        # Rename columns for display
        display_df.columns = [
            'Subject Code', 'Type', 'Weekly Freq', 
            'Duration', 'All-Day', 'Room',
            'Start Date', 'End Date', 'Last Updated'
        ]
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
        
        # Bulk actions
        st.markdown("---")
        st.subheader("📋 Bulk Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📥 Export Current View", use_container_width=True):
                csv = display_df.to_csv(index=False)
                st.download_button(
                    "Download CSV",
                    csv,
                    file_name=f"distributions_{self.ctx.degree}_Y{self.ctx.year}T{self.ctx.term}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col2:
            if st.button("🗑️ Delete All Distributions", type="secondary", use_container_width=True):
                st.session_state['confirm_delete_all'] = True
        
        with col3:
            if st.button("🔄 Reset to Template", use_container_width=True):
                st.info("Use Import/Export tab to generate and import fresh template")
        
        # Delete confirmation
        if st.session_state.get('confirm_delete_all', False):
            st.warning("⚠️ Are you sure you want to delete ALL distributions for this context?")
            col_yes, col_no = st.columns(2)
            
            with col_yes:
                if st.button("✅ Yes, Delete All", type="primary"):
                    self._delete_all_distributions()
                    del st.session_state['confirm_delete_all']
                    st.success("✅ All distributions deleted")
                    st.cache_data.clear()
                    st.rerun()
            
            with col_no:
                if st.button("❌ Cancel"):
                    del st.session_state['confirm_delete_all']
                    st.rerun()
    
    def _delete_all_distributions(self):
        """Delete all distributions for current context.
        
        FIXED: Properly handles divisionless classes
        - If ctx.division is None → delete all divisions for this AY/degree/year/term
        - If ctx.division has a value → delete only that division
        """
        with self.engine.begin() as conn:
            if self.ctx.division is None:
                # Delete all divisions for this AY/degree/year/term
                conn.execute(
                    text("""
                        DELETE FROM weekly_subject_distribution
                        WHERE ay_label = :ay 
                          AND degree_code = :deg 
                          AND year = :yr 
                          AND term = :term
                    """),
                    {
                        'ay': self.ctx.ay,
                        'deg': self.ctx.degree,
                        'yr': self.ctx.year,
                        'term': self.ctx.term
                    }
                )
            else:
                # Delete only specific division
                conn.execute(
                    text("""
                        DELETE FROM weekly_subject_distribution
                        WHERE ay_label = :ay 
                          AND degree_code = :deg 
                          AND year = :yr 
                          AND term = :term
                          AND division_code = :div
                    """),
                    {
                        'ay': self.ctx.ay,
                        'deg': self.ctx.degree,
                        'yr': self.ctx.year,
                        'term': self.ctx.term,
                        'div': self.ctx.division
                    }
                )
            
            # Audit
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution_audit 
                    (distribution_id, offering_id, ay_label, degree_code, division_code, 
                     change_reason, changed_by, changed_at)
                    VALUES (NULL, NULL, :ay, :deg, :div, :reason, :actor, CURRENT_TIMESTAMP)
                """),
                {
                    'ay': self.ctx.ay,
                    'deg': self.ctx.degree,
                    'div': self.ctx.division,
                    'reason': f"BULK DELETE: All distributions for {self.ctx.degree} Y{self.ctx.year}T{self.ctx.term} Div {self.ctx.division}",
                    'actor': 'user'
                }
            )
    
    # ========================================================================
    # TAB 3: AUDIT TRAIL
    # ========================================================================
    
    # ========================================================================
    # TAB 3: AUDIT TRAIL
    # ========================================================================
    
    def _render_audit_trail_tab(self):
        """Render audit trail for distributions"""
        st.subheader("ðŸ“œ Audit Trail")
        st.caption("History of all changes to distributions")
        
        with self.engine.connect() as conn:
            audit_logs = pd.read_sql(
                text("""
                    SELECT 
                        a.id,
                        a.distribution_id,
                        a.offering_id,
                        d.subject_code,
                        a.change_reason,
                        a.changed_by,
                        a.changed_at
                    FROM weekly_subject_distribution_audit a
                    LEFT JOIN weekly_subject_distribution d ON d.id = a.distribution_id
                    WHERE a.ay_label = :ay
                      AND a.degree_code = :deg
                      AND (:div IS NULL OR a.division_code = :div)
                    ORDER BY a.changed_at DESC
                    LIMIT 200
                """),
                conn,
                params=self.ctx.to_dict()
            )
        
        if audit_logs.empty:
            st.info("â„¹ï¸ No audit logs found for this context")
            return
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Changes", len(audit_logs))
        
        with col2:
            unique_subjects = audit_logs['subject_code'].nunique()
            st.metric("Subjects Modified", unique_subjects)
        
        with col3:
            recent_24h = len(audit_logs[pd.to_datetime(audit_logs['changed_at']) > pd.Timestamp.now() - pd.Timedelta(days=1)])
            st.metric("Changes (24h)", recent_24h)
        
        st.divider()
        
        # Filters
        col1, col2 = st.columns(2)
        
        with col1:
            actors = audit_logs['changed_by'].unique().tolist()
            filter_actor = st.multiselect("Filter by User", actors, default=actors)
        
        with col2:
            date_range = st.date_input(
                "Date Range",
                value=(
                    pd.to_datetime(audit_logs['changed_at']).min().date(),
                    pd.to_datetime(audit_logs['changed_at']).max().date()
                )
            )
        
        # Apply filters
        filtered_logs = audit_logs[audit_logs['changed_by'].isin(filter_actor)]
        
        if len(date_range) == 2:
            filtered_logs = filtered_logs[
                (pd.to_datetime(filtered_logs['changed_at']).dt.date >= date_range[0]) &
                (pd.to_datetime(filtered_logs['changed_at']).dt.date <= date_range[1])
            ]
        
        # Display logs
        st.markdown("### Recent Changes")
        
        for _, log in filtered_logs.head(50).iterrows():
            with st.expander(
                f"ðŸ• {log['changed_at']} - {log['subject_code'] or 'BULK OPERATION'} by {log['changed_by']}",
                expanded=False
            ):
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    st.write(f"**Log ID:** {log['id']}")
                    if log['distribution_id']:
                        st.write(f"**Dist ID:** {log['distribution_id']}")
                    if log['offering_id']:
                        st.write(f"**Offering ID:** {log['offering_id']}")
                
                with col2:
                    st.write(f"**Subject:** {log['subject_code'] or 'N/A'}")
                    st.write(f"**Action:** {log['change_reason']}")
                    st.write(f"**By:** {log['changed_by']}")
                    st.write(f"**When:** {log['changed_at']}")
        
        if len(filtered_logs) > 50:
            st.caption(f"Showing 50 of {len(filtered_logs)} logs. Use filters to narrow down.")
        
        # Export audit
        st.divider()
        if st.button("ðŸ“¥ Export Audit Log"):
            csv = filtered_logs.to_csv(index=False)
            st.download_button(
                "Download Audit CSV",
                csv,
                file_name=f"audit_log_{self.ctx.degree}_Y{self.ctx.year}T{self.ctx.term}.csv",
                mime="text/csv"
            )
    
    # ========================================================================
    # TAB 4: IMPORT/EXPORT
    # ========================================================================
    
    def _render_import_export_tab(self):
        """Render import/export interface"""
        try:
            try:
                from distribution_import_export_ui import DistributionImportExportUI
            except ImportError:
                current_dir = Path(__file__).parent
                sys.path.insert(0, str(current_dir))
                
                try:
                    from distribution_import_export_ui import DistributionImportExportUI
                except ImportError:
                    ui_dir = current_dir.parent / "ui"
                    sys.path.insert(0, str(ui_dir))
                    from distribution_import_export_ui import DistributionImportExportUI
            
            import_export_ui = DistributionImportExportUI(self.engine)
            import_export_ui.render(ctx=self.ctx)
            
        except ImportError as e:
            st.error("âš ï¸ Import/Export Feature Not Available")
            st.info(f"Error: {str(e)}\n\nPlace distribution_import_export.py and distribution_import_export_ui.py in the same folder.")
            
            if st.button("ðŸ”„ Retry Loading"):
                st.rerun()
