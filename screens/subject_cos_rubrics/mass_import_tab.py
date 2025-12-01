# screens/subject_cos_rubrics/mass_import_tab.py
import streamlit as st
import pandas as pd
from sqlalchemy.engine import Engine
from .mass_import_service import MassImportService
import time

def render_mass_import_tab(engine: Engine):
    st.subheader("📦 Mass Import: Course Outcomes")
    service = MassImportService(engine)

    # Context
    degree_code = "Unknown"
    ay_label = "Unknown"
    
    if "co_main_degree_val" in st.session_state:
        raw_degree = st.session_state.co_main_degree_val
        degree_code = raw_degree.split(" - ")[0] if " - " in raw_degree else raw_degree
        ay_label = st.session_state.get("co_main_ay_val", st.session_state.get("co_main_ay", "Unknown"))
        st.info(f"Targeting: **{degree_code}** | Academic Year: **{ay_label}**")
    else:
        st.warning("Please select a Degree in the filters above to start.")
        return

    st.markdown("Import Course Outcomes for multiple subjects at once.")

    # 1. CONFIG
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### 1. Settings")
        weight_mode = st.radio(
            "Weightage Mode",
            options=["equal", "weighted"],
            format_func=lambda x: "⚖️ Equal (Auto)" if x == 'equal' else "🎚️ Custom",
            horizontal=True
        )
    
    with col2:
        st.markdown("#### 2. Template")
        if degree_code != "Unknown":
            try:
                template_data = service.generate_co_template(degree_code, weight_mode)
                st.download_button(
                    label=f"📥 Download CSV Template",
                    data=template_data,
                    file_name=f"co_template_{degree_code}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Template Error: {e}")

    # 3. UPLOAD & PREVIEW
    st.markdown("---")
    st.markdown("#### 3. Upload & Preview")
    
    file = st.file_uploader("Upload CO CSV", type=["csv"], key="mass_co_up")
    
    if file:
        try:
            # FIX: Robust file reading with encoding fallback
            try:
                df = pd.read_csv(file)
            except UnicodeDecodeError:
                # If UTF-8 fails (e.g., Excel CSV on Windows), try cp1252
                file.seek(0) # Reset file pointer
                df = pd.read_csv(file, encoding='cp1252')
            
            st.write(f"File loaded: {len(df)} rows")
            
            # --- DRY RUN SECTION ---
            if st.button("🔍 Run Dry Run / Preview", type="primary", use_container_width=True):
                with st.spinner("Analyzing data..."):
                    report = service.dry_run_import(df, degree_code, ay_label, weight_mode)
                    st.session_state.mass_import_report = report
            
            if 'mass_import_report' in st.session_state and st.session_state.mass_import_report:
                report_df = pd.DataFrame(st.session_state.mass_import_report)
                
                # Metrics
                total = len(report_df)
                valid = len(report_df[report_df['Status'] == 'Valid'])
                invalid = total - valid
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Rows", total)
                c2.metric("✅ Valid Rows", valid)
                c3.metric("❌ Invalid / Skipped Rows", invalid)
                
                # Show Table with styling
                st.markdown("##### Preview Details")
                
                def highlight_status(val):
                    color = 'red' if val == 'Invalid' else 'green'
                    return f'color: {color}; font-weight: bold'
                
                st.dataframe(
                    report_df.style.map(highlight_status, subset=['Status']),
                    use_container_width=True,
                    column_config={
                        "Errors": st.column_config.TextColumn("Errors", width="large"),
                        "Subject": st.column_config.TextColumn("Subject", width="small"),
                    }
                )
                
                # --- EXECUTE SECTION ---
                st.markdown("---")
                
                # Determine button state
                can_proceed = valid > 0
                btn_label = f"🚀 Execute Import ({valid} Valid Rows)"
                
                if invalid > 0 and can_proceed:
                    st.warning(f"⚠️ **Attention:** You have {invalid} invalid rows. If you proceed, these rows will be **SKIPPED** automatically. Only the {valid} valid rows will be imported.")
                    btn_label = f"🚀 Execute Import (Skip {invalid} Invalid Rows)"
                elif not can_proceed:
                    st.error("❌ No valid rows found. Please fix your CSV.")
                else:
                    st.success("✅ All rows are valid.")

                col_ex1, col_ex2 = st.columns([1, 1])
                with col_ex1:
                    # UPDATED: Button is only disabled if there are NO valid rows at all.
                    if st.button(btn_label, type="primary", use_container_width=True, disabled=not can_proceed):
                        with st.spinner("Importing valid rows to database..."):
                            res = service.mass_import_cos(
                                df, degree_code, ay_label, 
                                st.session_state.get("user_email", "system"),
                                weight_mode
                            )
                        
                        if res['success'] > 0:
                            st.success(f"✅ Import Process Complete! Successfully imported {res['success']} COs.")
                            
                            if res['failed'] > 0:
                                st.warning(f"⚠️ Skipped {res['failed']} invalid rows/failures.")
                            
                            if weight_mode == 'equal':
                                st.info("ℹ️ Weights auto-balanced.")
                            
                            # Cleanup and reload
                            del st.session_state.mass_import_report
                            time.sleep(1.5)
                            st.rerun()
                        else:
                            st.error(f"❌ Import failed. No records were saved. (Errors: {len(res['errors'])})")
                            with st.expander("View Execution Errors"):
                                for e in res['errors']:
                                    st.write(e)
                                    
                with col_ex2:
                    if st.button("❌ Clear Preview"):
                        del st.session_state.mass_import_report
                        st.rerun()

        except Exception as e:
            st.error(f"Error reading file: {e}")
