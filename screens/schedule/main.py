# screens/schedule/main.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text

# ==============================================================================
# DATA MANAGER
# ==============================================================================

class ScheduleManager:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _exec(self, sql, params=None):
        with self.engine.begin() as conn:
            return conn.execute(sa_text(sql), params or {})

    # --- Fetchers ---
    def get_faculty_info(self, subject_id: int):
        """Fetches hierarchy info: Branch Head, CIC, SIC, Team."""
        # 1. Subject In-Charge (SIC)
        sic_sql = """
            SELECT f.name, f.email FROM faculty_profiles f
            JOIN subject_offerings so ON so.instructor_email = f.email
            WHERE so.id = :sid
        """
        # Mock logic for demo - In production, replace with real queries
        bh_name = "Dr. Branch Head (Mock)" 
        cic_name = "Prof. Class Coordinator (Mock)"

        with self.engine.connect() as conn:
            sic_res = conn.execute(sa_text(sic_sql), {'sid': subject_id}).fetchone()
            sic_name = sic_res[0] if sic_res else "Unassigned"
            team = ["Prof. A", "Prof. B"] 
            
            return {
                "sic": sic_name,
                "cic": cic_name,
                "bh": bh_name,
                "team": team
            }

    def get_syllabus(self, subject_id: int):
        """Fetches syllabus modules/topics."""
        sql = """
            SELECT stp.sequence, stp.title, stp.hours_allocation
            FROM subject_offerings so
            JOIN syllabus_templates st ON so.syllabus_template_id = st.id
            JOIN syllabus_template_points stp ON st.id = stp.template_id
            WHERE so.id = :sid
            ORDER BY stp.sequence
        """
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(sa_text(sql), conn, params={'sid': subject_id})
        except Exception:
            return pd.DataFrame()

    def get_assignments(self, offering_id: int):
        """Fetches active assignments with marks."""
        try:
            sql = "SELECT id, title, max_marks FROM assignments WHERE offering_id = :oid AND status != 'archived'"
            with self.engine.connect() as conn:
                return pd.read_sql(sa_text(sql), conn, params={'oid': offering_id})
        except Exception:
            return pd.DataFrame(columns=['id', 'title', 'max_marks'])

    def get_sessions(self, subject_id: int, start_date: date, end_date: date):
        sql = """
            SELECT * FROM schedule_sessions 
            WHERE subject_id = :sid 
              AND session_date BETWEEN :start AND :end
            ORDER BY session_date
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(sa_text(sql), conn, params={'sid': subject_id, 'start': start_date, 'end': end_date})
            if not df.empty:
                df['session_date'] = pd.to_datetime(df['session_date']).dt.date
            return df

    def get_used_assignments(self, subject_id: int):
        """Returns set of assignment IDs already used in this subject's schedule."""
        sql = "SELECT assignment_id FROM schedule_sessions WHERE subject_id = :sid AND assignment_id IS NOT NULL"
        with self.engine.connect() as conn:
            res = conn.execute(sa_text(sql), {'sid': subject_id}).fetchall()
            return {r[0] for r in res}

    # --- Actions ---
    def save_sessions(self, subject_id: int, rows: List[dict], context: dict):
        if not rows: return
        dates = {r['session_date'] for r in rows}
        if dates:
            date_list = "', '".join([d.isoformat() for d in dates])
            self._exec(f"DELETE FROM schedule_sessions WHERE subject_id = :sid AND session_date IN ('{date_list}')", {'sid': subject_id})
        
        cols = [
            "subject_id", "session_date", "slot_signature", "kind", 
            "l_units", "t_units", "p_units", "s_units", 
            "lecture_notes", "studio_notes", "assignment_id", "completed",
            "batch_year", "semester", "branch_id", "status"
        ]
        
        val_placeholders = ", ".join([f":{c}" for c in cols])
        insert_sql = f"INSERT INTO schedule_sessions ({', '.join(cols)}) VALUES ({val_placeholders})"
        
        insert_data = []
        for r in rows:
            data = r.copy()
            data['subject_id'] = subject_id
            data.update(context)
            for k in ['l_units','t_units','p_units','s_units']:
                data[k] = int(data.get(k) or 0)
            insert_data.append(data)
            
        with self.engine.begin() as conn:
            conn.execute(sa_text(insert_sql), insert_data)

    def link_assignment(self, session_id: int, assignment_id: int):
        """Links an assignment to a specific session."""
        sql = "UPDATE schedule_sessions SET assignment_id = :aid WHERE id = :sid"
        self._exec(sql, {'aid': assignment_id, 'sid': session_id})
        
    def set_publish_status(self, subject_id: int, start: date, end: date, status: str):
        sql = """
            UPDATE schedule_sessions 
            SET status = :status 
            WHERE subject_id = :sid AND session_date BETWEEN :start AND :end
        """
        self._exec(sql, {'status': status, 'sid': subject_id, 'start': start, 'end': end})


# ==============================================================================
# UI RENDERERS
# ==============================================================================

def render_info_header(manager: ScheduleManager, subject_id: int):
    info = manager.get_faculty_info(subject_id)
    with st.container():
        st.markdown("### 🏛️ Academic Team")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Branch Head:** {info['bh']}")
        c2.markdown(f"**Class In-Charge:** {info['cic']}")
        c3.markdown(f"**Subject In-Charge:** {info['sic']}")
        st.markdown(f"**Faculty Team:** {', '.join(info['team'])}")
        st.divider()

def render_syllabus_preview(manager: ScheduleManager, subject_id: int):
    st.markdown("### 📘 Syllabus Overview")
    df = manager.get_syllabus(subject_id)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No syllabus defined for this subject yet.")
    st.divider()

def render_assignment_summary(manager: ScheduleManager, subject_id: int, start: date, end: date):
    st.markdown("### 📝 Assignment Summary (Scheduled)")
    sessions = manager.get_sessions(subject_id, start, end)
    assignments = manager.get_assignments(subject_id)
    
    if sessions.empty or assignments.empty:
        st.info("No assignments scheduled in this period.")
        return

    linked_sessions = sessions[sessions['assignment_id'].notnull()].copy()
    if linked_sessions.empty:
        st.info("No assignments linked to sessions.")
        return

    summary = pd.merge(linked_sessions[['session_date', 'assignment_id']], assignments, left_on='assignment_id', right_on='id')
    display_df = summary[['title', 'session_date', 'max_marks']].rename(columns={'title': 'Assignment Name', 'session_date': 'Scheduled Date', 'max_marks': 'Marks'})
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown(f"**Total Marks Scheduled:** {display_df['Marks'].sum()}")

def render_assignment_linker(manager: ScheduleManager, subject_id: int, sessions_df: pd.DataFrame, can_edit: bool):
    """
    Dynamic Linker: Filters out used assignments to ensure uniqueness.
    """
    if not can_edit: return

    st.markdown("#### 🔗 Smart Assignment Linker")
    st.caption("Use this tool to assign tasks. Assignments disappear from the list once linked.")
    
    # 1. Fetch Data
    all_asg = manager.get_assignments(subject_id)
    used_ids = manager.get_used_assignments(subject_id)
    
    # 2. Filter: Only Unused Assignments
    available_asg = all_asg[~all_asg['id'].isin(used_ids)]
    
    if available_asg.empty:
        st.success("✅ All active assignments have been scheduled!")
        return
        
    # 3. Filter: Only Future/Available Sessions
    if sessions_df.empty:
        st.warning("No sessions available to link.")
        return
        
    # Create dropdown options
    asg_opts = {row['id']: f"{row['title']} ({row['max_marks']} pts)" for _, row in available_asg.iterrows()}
    
    # Session options: "Date (Slot) - [Current: None]"
    # We prefer sessions that don't have an assignment yet
    sessions_df['label'] = sessions_df.apply(lambda x: f"{x['session_date']} ({x['slot_signature']})", axis=1)
    session_opts = {row['id']: row['label'] for _, row in sessions_df.iterrows()}
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        sel_asg_id = st.selectbox("Select Assignment", options=list(asg_opts.keys()), format_func=lambda x: asg_opts[x], key="link_asg_sel")
    with c2:
        sel_sess_id = st.selectbox("Select Session", options=list(session_opts.keys()), format_func=lambda x: session_opts[x], key="link_sess_sel")
    with c3:
        st.write("") # Spacer
        st.write("") 
        if st.button("Link Task", type="primary", use_container_width=True):
            manager.link_assignment(sel_sess_id, sel_asg_id)
            st.success("Assignment Linked!")
            st.rerun()

def render_schedule_editor(manager: ScheduleManager, subject_id: int, 
                           start_date: date, end_date: date, context: dict,
                           user_role: str):
    st.markdown("### 📅 Session Plan")

    is_sic = user_role in ['sic', 'superadmin']
    can_edit_structure = user_role in ['cic', 'superadmin'] or is_sic
    can_edit_content = is_sic

    df = manager.get_sessions(subject_id, start_date, end_date)
    
    # --- 1. Render Smart Linker (Dynamic Options) ---
    render_assignment_linker(manager, subject_id, df, can_edit_content)
    
    st.divider()

    # --- 2. Main Grid (Overview & Edits) ---
    all_asg = manager.get_assignments(subject_id)
    asg_opts = {row['id']: f"{row['title']} ({row['max_marks']} pts)" for _, row in all_asg.iterrows()}
    asg_opts[None] = "None"
    asg_rev = {v: k for k, v in asg_opts.items()}
    asg_marks_map = {row['id']: row['max_marks'] for _, row in all_asg.iterrows()}
    
    ui_df = df.copy() if not df.empty else pd.DataFrame(columns=[
        'session_date', 'slot_signature', 'kind', 'l_units', 't_units', 'p_units', 's_units', 
        'lecture_notes', 'assignment_id', 'completed', 'status'
    ])
    
    ui_df = ui_df.rename(columns={
        "session_date": "Date", "slot_signature": "Slot", "kind": "Type",
        "l_units": "L", "t_units": "T", "p_units": "P", "s_units": "S",
        "lecture_notes": "Notes", "completed": "Done"
    })
    
    # Map Assignment ID to Title for Grid View
    ui_df['Assignment'] = ui_df['assignment_id'].map(asg_opts)
    # Add Read-Only Marks Column
    ui_df['Marks'] = ui_df['assignment_id'].map(asg_marks_map).fillna(0)

    col_config = {
        "Date": st.column_config.DateColumn("Date", required=True, disabled=not can_edit_structure),
        "Slot": st.column_config.SelectboxColumn("Slot", options=["Morning", "Afternoon"], disabled=not can_edit_structure),
        "Type": st.column_config.SelectboxColumn("Type", options=["lecture","studio","practical","mixed"], disabled=not can_edit_structure),
        "L": st.column_config.NumberColumn("L", min_value=0),
        "T": st.column_config.NumberColumn("T", min_value=0),
        "P": st.column_config.NumberColumn("P", min_value=0),
        "S": st.column_config.NumberColumn("S", min_value=0),
        "Notes": st.column_config.TextColumn("Notes", disabled=not can_edit_content),
        # Assignment column is visible but editing is best done via Linker for "Dynamic" feel.
        # We leave it enabled for unlinking/correcting.
        "Assignment": st.column_config.SelectboxColumn("Assignment", options=list(asg_opts.values()), disabled=not can_edit_content),
        "Marks": st.column_config.NumberColumn("Marks (Max)", disabled=True), # Read Only
        "Done": st.column_config.CheckboxColumn("Done")
    }
    
    edited_df = st.data_editor(
        ui_df,
        column_config=col_config,
        use_container_width=True,
        num_rows="dynamic" if can_edit_structure else "fixed",
        hide_index=True,
        key="main_grid"
    )

    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("💾 Save Grid Changes", type="primary", use_container_width=True):
            rows_to_save = []
            for _, r in edited_df.iterrows():
                a_id = asg_rev.get(r["Assignment"])
                if a_id == "None": a_id = None
                
                rows_to_save.append({
                    "session_date": r["Date"],
                    "slot_signature": r["Slot"],
                    "kind": r["Type"],
                    "l_units": r["L"], "t_units": r["T"], "p_units": r["P"], "s_units": r["S"],
                    "lecture_notes": r["Notes"],
                    "assignment_id": a_id,
                    "completed": "yes" if r["Done"] else "no",
                    "status": r.get("status", "draft")
                })
            manager.save_sessions(subject_id, rows_to_save, context)
            st.success("Saved successfully!")
            st.rerun()

    if not df.empty:
        is_published = (df['status'] == 'published').all()
        with c2:
            if is_published:
                if st.button("Revert to Draft"):
                    manager.set_publish_status(subject_id, start_date, end_date, "draft")
                    st.rerun()
            else:
                if st.button("🚀 Publish Schedule"):
                    manager.set_publish_status(subject_id, start_date, end_date, "published")
                    st.success("Schedule Published!")
                    st.rerun()

# ==============================================================================
# MAIN
# ==============================================================================

def render(user: Dict[str, Any]):
    if 'db_engine' not in st.session_state: return
    manager = ScheduleManager(st.session_state.db_engine)
    
    subject_id = 1 
    start_date = date.today()
    end_date = start_date + timedelta(days=30)
    context = {"batch_year": 2025, "semester": 1, "branch_id": 1}
    user_role = user.get('role', 'sic') 

    st.title("Subject Schedule")
    
    render_info_header(manager, subject_id)
    
    with st.expander("View Syllabus", expanded=False):
        render_syllabus_preview(manager, subject_id)
    
    render_schedule_editor(manager, subject_id, start_date, end_date, context, user_role)
    render_assignment_summary(manager, subject_id, start_date, end_date)
