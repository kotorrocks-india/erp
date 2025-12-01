"""
Distribution Import/Export UI - COMPLETE FIXED VERSION
✅ Handles CSV column name variations (Subject Code → subject_code)
✅ Shows detailed import results with created/updated records
✅ Enhanced error messages and validation
✅ Better user feedback
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional
import io
from datetime import datetime
import sys
from pathlib import Path

try:
    from distribution_import_export import DistributionImportExportService, ImportResult
except ImportError:
    current_dir = Path(__file__).parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    try:
        from distribution_import_export import DistributionImportExportService, ImportResult
    except ImportError:
        st.error("distribution_import_export.py not found in same directory")
        st.stop()


def normalize_csv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize CSV column names to match database schema.
    Handles: Subject Code → subject_code, WeeklyFreq → weekly_freq, etc.
    """
    # Remove BOM, strip whitespace
    df.columns = df.columns.astype(str).str.replace('\ufeff', '').str.strip()
    
    # Create mapping for common variations
    column_mapping = {
        # Subject Code variations
        'Subject Code': 'subject_code',
        'SubjectCode': 'subject_code',
        'SUBJECT_CODE': 'subject_code',
        'subject code': 'subject_code',
        
        # Type variations
        'Type': 'type',
        'TYPE': 'type',
        'Subject Type': 'type',
        
        # Weekly Freq variations
        'Weekly Freq': 'weekly_freq',
        'WeeklyFreq': 'weekly_freq',
        'WEEKLY_FREQ': 'weekly_freq',
        'Frequency': 'weekly_freq',
        'weekly frequency': 'weekly_freq',
        
        # Duration variations
        'Duration': 'duration',
        'DURATION': 'duration',
        
        # All-Day variations
        'All-Day': 'all_day',
        'AllDay': 'all_day',
        'ALL_DAY': 'all_day',
        'All Day': 'all_day',
        'all day': 'all_day',
        
        # Room variations
        'Room': 'room',
        'ROOM': 'room',
        'room_code': 'room',
        
        # Start Date variations
        'Start Date': 'start_date',
        'StartDate': 'start_date',
        'START_DATE': 'start_date',
        
        # End Date variations
        'End Date': 'end_date',
        'EndDate': 'end_date',
        'END_DATE': 'end_date',
        
        # Last Updated variations
        'Last Updated': 'last_updated',
        'LastUpdated': 'last_updated',
        'LAST_UPDATED': 'last_updated',
    }
    
    # Apply exact mapping first
    df = df.rename(columns=column_mapping)
    
    # Then normalize any remaining columns: lowercase + underscores
    new_columns = {}
    for col in df.columns:
        if col not in ['subject_code', 'type', 'weekly_freq', 'duration', 'all_day', 
                       'room', 'start_date', 'end_date', 'last_updated',
                       'degree_code', 'year', 'term', 'program_code', 'branch_code', 
                       'division_code', 'curriculum_group_code']:
            # Not already normalized, convert it
            normalized = col.lower().replace(' ', '_').replace('-', '_')
            new_columns[col] = normalized
    
    if new_columns:
        df = df.rename(columns=new_columns)
    
    return df


class DistributionImportExportUI:
    """UI for import/export"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.service = DistributionImportExportService(engine)
    
    def render(self, ctx=None):
        """Render interface"""
        st.header("Import/Export Distribution")
        
        tab1, tab2, tab3 = st.tabs([
            "Generate Template",
            "Export",
            "Import"
        ])
        
        with tab1:
            self._render_template_tab(ctx)
        with tab2:
            self._render_export_tab(ctx)
        with tab3:
            self._render_import_tab(ctx)
    
    def _render_template_tab(self, ctx=None):
        """Template generation"""
        st.subheader("Generate Blank Template")
        
        col1, col2 = st.columns(2)
        
        with col1:
            degrees = self._fetch_degrees()
            if degrees.empty:
                st.error("No degrees found")
                return
            
            degree_idx = 0
            if ctx and ctx.degree in degrees['code'].values:
                degree_idx = degrees['code'].tolist().index(ctx.degree)
            
            degree = st.selectbox("Degree", degrees['code'], index=degree_idx, key="tpl_deg")
            
            programs = self._fetch_programs(degree)
            program = None
            if not programs.empty:
                prog_options = [None] + programs['program_code'].tolist()
                program = st.selectbox("Program", prog_options, key="tpl_prog")
        
        with col2:
            year = st.number_input("Year", 1, 5, ctx.year if ctx else 1, key="tpl_yr")
            term = st.number_input("Term", 1, 2, ctx.term if ctx else 1, key="tpl_term")
            
            branch = None
            if program:
                branches = self._fetch_branches(program)
                if not branches.empty:
                    branch_options = [None] + branches['branch_code'].tolist()
                    branch = st.selectbox("Branch", branch_options, key="tpl_branch")
        
        st.info("📋 Subject name and type in template are for reference only. Import uses subject_code to lookup real data.")
        
        if st.button("Generate", type="primary"):
            template = self.service.generate_template(
                degree_code=degree,
                year=year,
                term=term,
                program_code=program,
                branch_code=branch
            )
            
            if template.empty:
                st.warning("No subjects found")
            else:
                st.success(f"Generated {len(template)} rows")
                st.dataframe(template.head(10))
                self._download_csv(template, f"template_{degree}_Y{year}T{term}.csv", "Download Template")
    
    def _render_export_tab(self, ctx=None):
        """Export existing distributions"""
        st.subheader("Export Existing Distributions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            ays = self._fetch_ays()
            if ays.empty:
                st.error("No academic years")
                return
            
            ay_idx = 0
            if ctx and ctx.ay in ays['ay_code'].values:
                ay_idx = ays['ay_code'].tolist().index(ctx.ay)
            
            ay = st.selectbox("Academic Year", ays['ay_code'], index=ay_idx, key="exp_ay")
            
            degrees = self._fetch_degrees()
            degree_idx = 0
            if ctx and ctx.degree in degrees['code'].values:
                degree_idx = degrees['code'].tolist().index(ctx.degree)
            
            degree = st.selectbox("Degree", degrees['code'], index=degree_idx, key="exp_deg")
            
            programs = self._fetch_programs(degree)
            program = None
            if not programs.empty:
                prog_options = [None] + programs['program_code'].tolist()
                program = st.selectbox("Program", prog_options, key="exp_prog")
        
        with col2:
            year = st.number_input("Year", 1, 5, ctx.year if ctx else 1, key="exp_yr")
            term = st.number_input("Term", 1, 2, ctx.term if ctx else 1, key="exp_term")
            
            branch = None
            if program:
                branches = self._fetch_branches(program)
                if not branches.empty:
                    branch_options = [None] + branches['branch_code'].tolist()
                    branch = st.selectbox("Branch", branch_options, key="exp_branch")
            
            divisions = self._fetch_divisions(degree, year)
            division = None
            if divisions:
                div_options = [None] + divisions
                division = st.selectbox("Division", div_options, key="exp_div")
        
        if st.button("Export", type="primary"):
            data = self.service.export_distributions(
                ay_label=ay,
                degree_code=degree,
                year=year,
                term=term,
                program_code=program,
                branch_code=branch,
                division_code=division
            )
            
            if data.empty:
                st.warning("No distributions found")
            else:
                st.success(f"Exported {len(data)} records")
                st.dataframe(data.head(10))
                filename = f"export_{degree}_Y{year}T{term}_{ay}_{datetime.now().strftime('%Y%m%d')}.csv"
                self._download_csv(data, filename, "Download Export")
    
    def _render_import_tab(self, ctx=None):
        """Import distributions"""
        st.subheader("Import Distributions")
        
        st.info("📋 Subject name/type in CSV are ignored. Only subject_code is used for lookup.")
        
        ays = self._fetch_ays()
        if ays.empty:
            st.error("No academic years")
            return
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            ay_idx = 0
            if ctx and ctx.ay in ays['ay_code'].values:
                ay_idx = ays['ay_code'].tolist().index(ctx.ay)
            target_ay = st.selectbox("Target AY", ays['ay_code'], index=ay_idx, key="imp_ay")
        
        with col2:
            degrees = self._fetch_degrees()
            degree_idx = 0
            if ctx and ctx.degree in degrees['code'].values:
                degree_idx = degrees['code'].tolist().index(ctx.degree)
            target_degree = st.selectbox("Target Degree", degrees['code'], index=degree_idx, key="imp_deg")
        
        with col3:
            target_year = st.number_input("Target Year", 1, 5, ctx.year if ctx else 1, key="imp_yr")
        
        with col4:
            target_term = st.number_input("Target Term", 1, 2, ctx.term if ctx else 1, key="imp_term")
        
        col1, col2 = st.columns(2)
        with col1:
            programs = self._fetch_programs(target_degree)
            target_program = None
            if not programs.empty:
                prog_options = [None] + programs['program_code'].tolist()
                target_program = st.selectbox("Target Program", prog_options, key="imp_prog")
        
        with col2:
            target_branch = None
            if target_program:
                branches = self._fetch_branches(target_program)
                if not branches.empty:
                    branch_options = [None] + branches['branch_code'].tolist()
                    target_branch = st.selectbox("Target Branch", branch_options, key="imp_branch")
        
        overwrite = st.checkbox("Overwrite existing", False)
        
        st.divider()
        
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'], key="imp_file")
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)

                # ========================================================
                # COLUMN NORMALIZATION - Handles all variations
                # ========================================================
                st.write("**Original columns:**", list(df.columns))
                
                df = normalize_csv_columns(df)
                
                st.write("**Normalized columns:**", list(df.columns))
                # ========================================================
                
                # Add missing context columns
                if 'degree_code' not in df.columns:
                    df['degree_code'] = target_degree
                if 'year' not in df.columns:
                    df['year'] = target_year
                if 'term' not in df.columns:
                    df['term'] = target_term
                if target_program and 'program_code' not in df.columns:
                    df['program_code'] = target_program
                if target_branch and 'branch_code' not in df.columns:
                    df['branch_code'] = target_branch
                
                st.markdown("### File Preview")
                st.dataframe(df.head(10))
                st.caption(f"{len(df)} rows")
                
                # Validate required column
                if 'subject_code' not in df.columns:
                    st.error(f"❌ Missing required column: subject_code")
                    st.error(f"**Found columns:** {list(df.columns)}")
                    st.info("""
                    **Accepted column names for subject_code:**
                    - subject_code
                    - Subject Code
                    - SubjectCode
                    - SUBJECT_CODE
                    
                    Your CSV should have one of these column headers.
                    """)
                    return
                
                st.success("✅ File valid - subject_code column found")
                st.divider()
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("DRY RUN", type="secondary"):
                        result = self.service.import_distributions(
                            df, target_ay, dry_run=True, overwrite_existing=overwrite
                        )
                        st.session_state['dry_run_result'] = result
                        st.session_state['import_df'] = df
                        st.rerun()
                
                with col2:
                    if st.button("IMPORT", type="primary"):
                        if st.session_state.get('dry_run_result') and st.session_state['dry_run_result'].success:
                            result = self.service.import_distributions(
                                st.session_state['import_df'], target_ay, dry_run=False, overwrite_existing=overwrite
                            )
                            self._show_result(result)
                            # Clear session state after successful import
                            if 'dry_run_result' in st.session_state:
                                del st.session_state['dry_run_result']
                            if 'import_df' in st.session_state:
                                del st.session_state['import_df']
                        else:
                            st.error("⚠️ Run Dry Run first!")
                
                if 'dry_run_result' in st.session_state:
                    self._show_result(st.session_state['dry_run_result'])
                    
            except Exception as e:
                st.error(f"❌ Error reading CSV: {str(e)}")
                import traceback
                with st.expander("Debug Info"):
                    st.code(traceback.format_exc())
    
    def _show_result(self, result: ImportResult):
        """Display import result with detailed breakdown"""
        st.divider()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Processed", result.records_processed)
        with col2:
            st.metric("Created", result.records_created)
        with col3:
            st.metric("Updated", result.records_updated)
        with col4:
            st.metric("Skipped", result.records_skipped)
        
        if result.success:
            if result.dry_run:
                st.success("✅ Validation passed!")
            else:
                st.success(f"✅ Imported {result.records_created + result.records_updated} records")
        else:
            st.error("❌ Import failed")
        
        # Show details of what was imported
        if hasattr(result, 'created_details') and result.created_details and not result.dry_run:
            with st.expander(f"✅ Created Records ({len(result.created_details)})", expanded=True):
                details_df = pd.DataFrame(result.created_details)
                st.dataframe(details_df, use_container_width=True, hide_index=True)
                st.caption("These records were successfully added to the database")
        
        if hasattr(result, 'updated_details') and result.updated_details and not result.dry_run:
            with st.expander(f"🔄 Updated Records ({len(result.updated_details)})", expanded=True):
                details_df = pd.DataFrame(result.updated_details)
                st.dataframe(details_df, use_container_width=True, hide_index=True)
                st.caption("These records were updated in the database")
        
        if result.errors:
            with st.expander(f"❌ Errors ({len(result.errors)})"):
                for err in result.errors:
                    st.error(err)
        
        if result.warnings:
            with st.expander(f"⚠️ Warnings ({len(result.warnings)})"):
                for warn in result.warnings:
                    st.warning(warn)
        
        # Show query to verify
        if not result.dry_run and (result.records_created > 0 or result.records_updated > 0):
            st.info("""
            **📊 To view imported data:**
            1. Go to "Saved Distributions" tab
            2. Check the Audit Trail tab to see import history
            3. Make sure your context (AY/Degree/Year/Term/Division) matches the import
            """)
    
    def _download_csv(self, df: pd.DataFrame, filename: str, label: str):
        """Download button"""
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        
        st.download_button(label, csv_data, filename, "text/csv", use_container_width=True)
    
    def _fetch_ays(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                "SELECT ay_code FROM academic_years ORDER BY ay_code DESC",
                conn
            )
    
    def _fetch_degrees(self) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                "SELECT code FROM degrees WHERE active=1 ORDER BY code",
                conn
            )
    
    def _fetch_programs(self, degree_code: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                text("SELECT program_code FROM programs WHERE degree_code=:d AND active=1"),
                conn, params={'d': degree_code}
            )
    
    def _fetch_branches(self, program_code: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(
                text("""
                    SELECT b.branch_code FROM branches b
                    JOIN programs p ON b.program_id = p.id
                    WHERE p.program_code=:p AND b.active=1
                """),
                conn, params={'p': program_code}
            )
    
    def _fetch_divisions(self, degree_code: str, year: int) -> list:
        with self.engine.connect() as conn:
            try:
                result = pd.read_sql(
                    text("""
                        SELECT DISTINCT division_code FROM division_master
                        WHERE degree_code=:deg AND current_year=:yr AND active=1
                        ORDER BY division_code
                    """),
                    conn, params={'deg': degree_code, 'yr': year}
                )
                return result['division_code'].tolist() if not result.empty else []
            except:
                return []
