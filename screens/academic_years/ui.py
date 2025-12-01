# screens/academic_years/ui.py
from __future__ import annotations

import traceback
from typing import Optional, Sequence
from sqlalchemy import text as sa_text
import pandas as pd
import streamlit as st
import datetime
from sqlalchemy.engine import Engine
import json

# -------------------------------------------------------------------
# Utility imports (soft-fail with fallbacks)
# -------------------------------------------------------------------
try:
    from screens.academic_years.utils import (
        is_valid_ay_code,
        parse_date_range,
        validate_ay_dates,
        get_next_ay_code,
        get_ay_status_display,
        _get_year_from_ay_code,
        validate_ay_code_structure,
        parse_ay_code,
        format_ay_code,
    )
except Exception:
    # Fallback implementations
    def is_valid_ay_code(code: str) -> bool:
        return bool(code and len(str(code)) >= 4)

    def parse_date_range(start, end):
        return start, end

    def validate_ay_dates(start, end):
        return []

    def get_next_ay_code(latest: Optional[str]) -> str:
        return ""

    def get_ay_status_display(status: str) -> str:
        return status or ""

    def _get_year_from_ay_code(code: str) -> Optional[int]:
        try:
            if not code:
                return None
            parts = str(code).split("-")
            return int(parts[0])
        except Exception:
            return None

    def validate_ay_code_structure(code: str) -> list:
        return []

    def parse_ay_code(code: str) -> dict:
        return {}

    def format_ay_code(start_year: int, is_short_term: bool = False, prefix: bool = True, separator: str = "-") -> str:
        return f"{start_year}-{start_year + 1 % 100:02d}"


# -------------------------------------------------------------------
# DB imports (soft-fail with trivial fallbacks)
# -------------------------------------------------------------------
try:
    from screens.academic_years.db import (
        get_all_ays,
        get_ay_by_code,
        insert_ay,
        update_ay_dates,
        update_ay_status,
        delete_ay,
        check_overlap,
        get_latest_ay_code,
        get_all_degrees,
        get_degree_duration,
        get_degree_terms_per_year,
        get_programs_for_degree,
        get_branches_for_degree_program,
        get_batch_term_dates,
        _db_get_batches_for_degree,
        _db_check_batch_has_students,
        get_semester_mapping_for_year,
    )
except Exception:
    def get_all_ays(conn): return []
    def get_ay_by_code(conn, code): return None
    def insert_ay(conn, code, start_date, end_date, actor=None): return True
    def update_ay_dates(conn, code, start_date, end_date, actor=None): return True
    def update_ay_status(conn, code, status, actor=None, reason=None): return True
    def delete_ay(conn, code, actor=None): return True
    def check_overlap(conn, start_date, end_date, exclude_code=None): return None
    def get_latest_ay_code(conn): return None
    def get_all_degrees(conn): return []
    def get_degree_duration(conn, code): return 4
    def get_degree_terms_per_year(conn, code): return 0
    def get_programs_for_degree(conn, d): return []
    def get_branches_for_degree_program(conn, d, p): return []
    def get_batch_term_dates(conn, d, b, ay, y=None): return []
    def _db_get_batches_for_degree(conn, degree_code): return []
    def _db_check_batch_has_students(conn, d, b): return False
    def get_semester_mapping_for_year(conn, d, y, p=None, b=None): return {}


# -------------------------------------------------------------------
# Approvals integration (optional)
# -------------------------------------------------------------------
try:
    from core.approval_handler_enhanced import create_approval_request
    _HAS_APPROVALS = True
except Exception:
    _HAS_APPROVALS = False

    def create_approval_request(
        engine,
        object_type: str,
        object_id: str,
        action: str,
        requester_email: str,
        reason: str = "",
        payload: Optional[dict] = None,
    ) -> int:
        return 0


# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------
def _safe_conn(engine: Engine):
    """Context manager wrapper to get a connection."""
    try:
        return engine.connect()
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        st.stop()


def _df_or_empty(rows, columns) -> pd.DataFrame:
    try:
        return pd.DataFrame(rows, columns=columns)
    except Exception:
        return pd.DataFrame(columns=columns)


def _handle_error(e: Exception, message: str) -> None:
    st.error(f"{message}: {e}")
    st.code(traceback.format_exc())


# -------------------------------------------------------------------
# Academic Year List
# -------------------------------------------------------------------
def render_ay_list(engine: Engine) -> None:
    """Display all academic years with filtering and search."""
    st.subheader("🗓️ Academic Years")

    # Filters
    fc1, fc2 = st.columns([1, 2])
    with fc1:
        status_filter = st.multiselect(
            "Filter by Status",
            options=["planned", "open", "closed"],
            default=[],
            key="aylist_status_filter",
        )
    with fc2:
        query = st.text_input(
            "Search AY code",
            placeholder="e.g., 2025-26",
            key="aylist_search_q",
        )

    # Load data
    with _safe_conn(engine) as conn:
        rows = get_all_ays(conn) or []

    cols = ["code", "start_date", "end_date", "status"]
    has_updated = any("updated_at" in r for r in rows) if rows else False
    if has_updated:
        cols.append("updated_at")

    df = _df_or_empty(rows, columns=cols)

    # Apply filters
    if status_filter:
        df = df[df["status"].isin(status_filter)]
    if query:
        q = str(query).strip().lower()
        df = df[df["code"].str.lower().str.contains(q, na=False)]

    st.caption(f"{len(df)} result(s)")
    if df.empty:
        if not rows:
            st.info("📋 **No academic years found in database.**")
            st.markdown("""
            **To get started:**
            1. Go to the **✏️ AY Editor** tab
            2. Configure your academic year dates
            3. Click **💾 Save Academic Year**
            """)
        else:
            st.info("No academic years match your current filters.")
        return

    # Pagination
    page_size = st.selectbox(
        "Rows per page",
        options=[10, 25, 50, 100, len(df)],
        index=1 if len(df) >= 25 else 0,
        format_func=lambda x: "All" if x == len(df) else str(x),
        key="aylist_page_size",
    )

    if page_size and page_size != len(df):
        pages = (len(df) + page_size - 1) // page_size
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=int(pages),
            value=1,
            step=1,
            key="aylist_page_num",
        )
        start = (int(page) - 1) * page_size
        end = start + page_size
        df_to_show = df.iloc[start:end]
    else:
        df_to_show = df

    st.dataframe(df_to_show, use_container_width=True)


# -------------------------------------------------------------------
# Academic Year Editor
# -------------------------------------------------------------------
def render_ay_editor(engine: Engine, roles: Sequence[str], email: str) -> None:
    """Create or edit an academic year with enhanced UI."""
    st.subheader("✏️ Create / Edit Academic Year")

    if "admin" not in roles and "superadmin" not in roles:
        st.info("You do not have permission to edit Academic Years.")
        return

    with _safe_conn(engine) as conn:
        rows = get_all_ays(conn) or []
        latest_code = get_latest_ay_code(conn)

    codes = [r["code"] if isinstance(r, dict) else r[0] for r in rows] if rows else []

    selected_code = st.selectbox(
        "Select AY to edit (or blank for new):",
        options=[""] + codes,
        key="ayed_select_code",
    )

    edit_mode = bool(selected_code)

    # Get existing record if editing
    if edit_mode:
        with _safe_conn(engine) as conn:
            record = get_ay_by_code(conn, selected_code) or {}
        
        if isinstance(record, dict):
            default_code = record.get("code", selected_code)
            default_start = record.get("start_date")
            default_end = record.get("end_date")
        else:
            default_code = getattr(record, "code", selected_code)
            default_start = getattr(record, "start_date", None)
            default_end = getattr(record, "end_date", None)
        
        # Parse existing code for defaults
        parsed = parse_ay_code(default_code)
        
        # Convert date strings to date objects if needed
        if default_start:
            try:
                if isinstance(default_start, str):
                    default_start = datetime.datetime.fromisoformat(default_start).date()
            except:
                default_start = None
        
        if default_end:
            try:
                if isinstance(default_end, str):
                    default_end = datetime.datetime.fromisoformat(default_end).date()
            except:
                default_end = None
    else:
        default_code = ""
        default_start, default_end = None, None
        parsed = None

    # ============================================================
    # ACADEMIC YEAR CODE BUILDER
    # ============================================================
    st.markdown("### 🎯 Academic Year Configuration")
    
    # Course type selection
    col_type, col_format = st.columns(2)
    with col_type:
        course_type = st.radio(
            "Course Type",
            options=["Regular Academic Year", "Short-Term Course"],
            index=0 if not parsed or not parsed.get("is_short_term") else 1,
            key="ayed_course_type",
            help="Regular: Spans two calendar years (e.g., 2025-26). Short-Term: Within one year (e.g., ST2025)."
        )
    
    is_short_term = (course_type == "Short-Term Course")
    
    # Format options (only for regular AY)
    if not is_short_term:
        with col_format:
            st.write("")  # Spacing
            include_prefix = st.checkbox(
                "Include 'AY' prefix",
                value=parsed.get("prefix") == "AY" if parsed else False,
                key="ayed_include_prefix"
            )
            separator = st.radio(
                "Separator",
                options=["Dash (-)", "Slash (/)"],
                index=0 if not parsed or parsed.get("separator") == "-" else 1,
                key="ayed_separator",
                horizontal=True
            )
    else:
        include_prefix = True
        separator = "Dash (-)"
    
    st.divider()
    
    # Year selection
    current_year = datetime.datetime.now().year
    
    if is_short_term:
        col_year = st.columns(1)[0]
        with col_year:
            start_year = st.number_input(
                "Year",
                min_value=2020,
                max_value=2040,
                value=parsed.get("start_year") if parsed else current_year,
                step=1,
                key="ayed_start_year",
                help="Short-term courses run within a single calendar year."
            )
            end_year = start_year
    else:
        col_start, col_end = st.columns(2)
        with col_start:
            start_year = st.number_input(
                "Start Year",
                min_value=2020,
                max_value=2040,
                value=parsed.get("start_year") if parsed else current_year,
                step=1,
                key="ayed_start_year",
                help="The first year of the academic year (e.g., 2025 in '2025-26')."
            )
        with col_end:
            end_year = st.number_input(
                "End Year",
                min_value=start_year + 1,
                max_value=start_year + 1,
                value=start_year + 1,
                step=1,
                key="ayed_end_year",
                disabled=True,
                help="Automatically set to start year + 1."
            )
    
    # Generate AY code
    sep_char = "-" if "Dash" in separator else "/"
    ay_code = format_ay_code(
        start_year=start_year,
        is_short_term=is_short_term,
        prefix=include_prefix,
        separator=sep_char
    )
    
    # Display generated code
    st.info(f"**Generated AY Code:** `{ay_code}`")
    
    # Allow manual override
    with st.expander("⚙️ Advanced: Manual Override", expanded=False):
        ay_code_override = st.text_input(
            "Override AY Code (leave blank to use generated)",
            value="",
            key="ayed_code_override",
            help="Only use this if you need a custom format."
        )
        if ay_code_override:
            ay_code = ay_code_override
            st.warning("Using manual override. Validation will still apply.")
    
    st.divider()
    
    # Date selection
    st.markdown("### 📅 Date Range")
    
    # Smart date suggestions
    if is_short_term:
        suggested_start = datetime.date(start_year, 1, 1)
        suggested_end = datetime.date(start_year, 12, 31)
        date_help = f"Both dates must be in {start_year}. Maximum duration: 365 days."
    else:
        suggested_start = datetime.date(start_year, 7, 1)
        suggested_end = datetime.date(end_year, 6, 30)
        date_help = (
            f"Start date should be in {start_year}, end date should be in {end_year}. "
            f"Maximum duration: 365 days."
        )
    
    # Use existing dates if editing, otherwise use suggestions
    if edit_mode and default_start and default_end:
        default_start_date = default_start
        default_end_date = default_end
    else:
        default_start_date = suggested_start
        default_end_date = suggested_end
    
    col_dates1, col_dates2 = st.columns(2)
    with col_dates1:
        start_date = st.date_input(
            "Start Date",
            value=default_start_date,
            key="ayed_start_date",
            help=date_help
        )
    with col_dates2:
        end_date = st.date_input(
            "End Date",
            value=default_end_date,
            key="ayed_end_date",
            help=date_help
        )
    
    # Real-time validation display
    if start_date and end_date:
        duration = (end_date - start_date).days
        
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.metric("Duration", f"{duration} days")
        with col_v2:
            if duration <= 365:
                st.metric("Status", "✅ Valid", delta=None)
            else:
                st.metric("Status", "⚠️ Exceeds 365 days", delta=None)
        with col_v3:
            st.metric(
                "Year Span",
                f"{start_date.year}" if start_date.year == end_date.year 
                else f"{start_date.year}-{end_date.year}"
            )
    
    st.divider()
    
    # Action buttons
    col_save, col_delete = st.columns(2)
    
    with col_save:
        if st.button("💾 Save Academic Year", key="ayed_save", type="primary"):
            with st.spinner("Saving Academic Year..."):
                # Comprehensive validation
                errors = []
                
                # Structure validation
                st.write("🔍 Validating AY code structure...")
                structure_errors = validate_ay_code_structure(ay_code)
                if structure_errors:
                    st.warning(f"Structure errors found: {len(structure_errors)}")
                else:
                    st.success("✅ Structure validation passed")
                errors.extend(structure_errors)
                
                # Date validation
                st.write("🔍 Validating dates...")
                date_errors = validate_ay_dates(start_date, end_date, ay_code)
                if date_errors:
                    st.warning(f"Date errors found: {len(date_errors)}")
                else:
                    st.success("✅ Date validation passed")
                errors.extend(date_errors)
                
                # Display all errors
                if errors:
                    st.error("❌ **Validation Failed:**")
                    for err in errors:
                        st.error(f"• {err}")
                    return
                
                # Check for overlaps and save
                try:
                    with engine.begin() as conn:
                        st.write("🔍 Checking for date overlaps...")
                        conflict = check_overlap(
                            conn,
                            start_date.isoformat(),
                            end_date.isoformat(),
                            exclude_code=ay_code if edit_mode else None,
                        )
                        if conflict:
                            st.error(f"❌ Date range overlaps with existing AY: **{conflict}**")
                            return
                        else:
                            st.success("✅ No date conflicts")
                        
                        # Actually save
                        st.write("💾 Writing to database...")
                        if edit_mode:
                            st.info("Mode: UPDATE existing AY")
                            update_ay_dates(
                                conn,
                                ay_code,
                                start_date.isoformat(),
                                end_date.isoformat(),
                                actor=email,
                            )
                            st.success(f"✅ Updated AY **{ay_code}** successfully!")
                        else:
                            st.info("Mode: CREATE new AY")
                            insert_ay(
                                conn,
                                ay_code,
                                start_date.isoformat(),
                                end_date.isoformat(),
                                actor=email,
                            )
                            st.success(f"✅ Created AY **{ay_code}** successfully!")
                        
                        # Verify before transaction closes
                        st.write("🔍 Verifying save...")
                        verify = conn.execute(
                            sa_text("SELECT ay_code FROM academic_years WHERE ay_code = :c"),
                            {"c": ay_code}
                        ).fetchone()
                        
                        if verify:
                            st.success(f"✅ Verified: AY '{ay_code}' exists in database")
                        else:
                            st.error(f"❌ CRITICAL: AY '{ay_code}' was not found after save!")
                            return
                    
                    # Transaction committed successfully
                    st.success("✅ Transaction committed successfully")
                    st.info("🔄 Refreshing page...")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ **Save failed with exception:**")
                    st.error(f"**Error type:** {type(e).__name__}")
                    st.error(f"**Error message:** {str(e)}")
                    st.code(traceback.format_exc())

    with col_delete:
        if edit_mode:
            delete_reason = st.text_input(
                "Reason for deletion (required)",
                key="ayed_delete_reason",
            )

            if st.button("🗑️ Delete", key="ayed_delete", type="secondary"):
                if _HAS_APPROVALS:
                    if not delete_reason.strip():
                        st.warning("⚠️ Please provide a reason for deletion.")
                        return
                    try:
                        payload = {
                            "ay_code": ay_code,
                            "reason": delete_reason.strip(),
                            "requested_by": email,
                        }
                        approval_id = create_approval_request(
                            engine=engine,
                            object_type="academic_year",
                            object_id=ay_code,
                            action="delete",
                            requester_email=email,
                            reason=delete_reason.strip(),
                            payload=payload,
                        )
                        st.success(
                            f"✅ Delete request for AY **{ay_code}** submitted "
                            f"(Request ID: {approval_id})."
                        )
                        st.info("📋 The academic year will be deleted once approved.")
                    except Exception as e:
                        _handle_error(e, "Failed to submit delete request")
                else:
                    try:
                        with engine.begin() as conn:
                            delete_ay(conn, ay_code, actor=email)
                        st.success(f"✅ Deleted AY **{ay_code}**.")
                        st.rerun()
                    except Exception as e:
                        _handle_error(e, "Failed to delete AY")


# -------------------------------------------------------------------
# AY Status Changer
# -------------------------------------------------------------------
def render_ay_status_changer(engine: Engine, roles: Sequence[str], email: str) -> None:
    """Change the status of an academic year."""
    st.subheader("🔄 Change AY Status")

    if "admin" not in roles and "superadmin" not in roles:
        st.info("You do not have permission to change AY status.")
        return

    with _safe_conn(engine) as conn:
        rows = get_all_ays(conn) or []

    codes = [r["code"] if isinstance(r, dict) else r[0] for r in rows] if rows else []
    if not codes:
        st.info("No Academic Years found.")
        return

    c1, c2 = st.columns(2)
    with c1:
        code = st.selectbox("Select AY", options=[""] + codes, key="aystat_code")
    with c2:
        status = st.selectbox(
            "New Status",
            options=["planned", "open", "closed"],
            key="aystat_status",
        )

    reason = st.text_input(
        "Reason for status change (used in approval request)",
        key="aystat_reason",
    )

    if st.button("Update Status", key="aystat_btn"):
        if not code:
            st.warning("Please select an AY.")
            return

        try:
            # For open/closed, go through approvals (if available)
            if _HAS_APPROVALS and status in ("open", "closed"):
                if not reason.strip():
                    st.warning("Please provide a reason for this status change.")
                    return

                # Get current status
                with _safe_conn(engine) as conn:
                    rec = get_ay_by_code(conn, code) or {}

                if isinstance(rec, dict):
                    current_status = rec.get("status")
                else:
                    current_status = getattr(rec, "status", None)

                payload = {
                    "from": current_status,
                    "to": status,
                    "reason": reason.strip(),
                    "requested_by": email,
                }

                approval_id = create_approval_request(
                    engine=engine,
                    object_type="academic_year",
                    object_id=code,
                    action="status_change",
                    requester_email=email,
                    reason=reason.strip(),
                    payload=payload,
                )
                st.success(
                    f"Status change to {status} for {code} submitted for approval "
                    f"(Request ID: {approval_id})."
                )
                st.info("The status will be updated after an approver approves the request.")
            else:
                # Direct update for non-sensitive states
                with engine.begin() as conn:
                    update_ay_status(conn, code, status, actor=email, reason=reason or None)
                st.success(f"Updated status of {code} to {status}.")
                st.rerun()
        except Exception as e:
            _handle_error(e, "Failed to update AY status")
