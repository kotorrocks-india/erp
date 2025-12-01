# screens/rubrics/rubrics_criteria_catalog.py
import streamlit as st
import pandas as pd
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import List, Dict, Optional
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

class RubricCriteriaService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def fetch_offering_context(self, offering_id: int) -> Dict:
        """Fetch context (Degree, Program, Branch) for the current offering."""
        with self.engine.begin() as conn:
            result = conn.execute(sa_text("""
                SELECT degree_code, program_code, branch_code 
                FROM subject_offerings 
                WHERE id = :id
            """), {"id": offering_id}).fetchone()
            return dict(result._mapping) if result else {}

    def fetch_all_criteria(self, degree_code: Optional[str] = None) -> List[Dict]:
        """Fetch all criteria, optionally filtered by degree."""
        query = """
            SELECT id, label, description, degree_code, program_code, branch_code, active
            FROM rubric_criteria_catalog
            WHERE 1=1
        """
        params = {}
        if degree_code and degree_code != "All":
            query += " AND (degree_code = :degree_code OR degree_code IS NULL)"
            params['degree_code'] = degree_code
        
        query += " ORDER BY degree_code, label"
        
        with self.engine.begin() as conn:
            result = conn.execute(sa_text(query), params)
            return [dict(row._mapping) for row in result]

    def _generate_key(self, label: str) -> str:
        """Generate a slug key from label."""
        return str(label).lower().strip().replace(" ", "_").replace("/", "_")

    def _get_existing_record_id(self, conn, label: str, degree: str, program: str, branch: str) -> Optional[int]:
        """Check if a record exists with the exact same scope."""
        query = """
            SELECT id FROM rubric_criteria_catalog
            WHERE label = :label
              AND (degree_code = :degree OR (:degree IS NULL AND degree_code IS NULL))
              AND (program_code = :program OR (:program IS NULL AND program_code IS NULL))
              AND (branch_code = :branch OR (:branch IS NULL AND branch_code IS NULL))
        """
        params = {
            'label': label,
            'degree': degree,
            'program': program,
            'branch': branch
        }
        result = conn.execute(sa_text(query), params).fetchone()
        return result[0] if result else None

    def process_import(self, df: pd.DataFrame, execute: bool = False) -> List[Dict]:
        """
        Handles both Dry Run (execute=False) and Real Import (execute=True).
        Returns a report of actions.
        """
        report = []
        
        def clean_str(val):
            if pd.isna(val) or str(val).strip() == '': return None
            return str(val).strip()

        with self.engine.begin() as conn:
            seen_in_file = set()

            for idx, row in df.iterrows():
                row_idx = idx + 2
                
                label = clean_str(row.get('label'))
                if not label:
                    report.append({"Row": row_idx, "Label": "-", "Action": "Skip", "Status": "Invalid: Missing Label"})
                    continue

                description = clean_str(row.get('description'))
                degree = clean_str(row.get('degree_code'))
                program = clean_str(row.get('program_code'))
                branch = clean_str(row.get('branch_code'))
                active = int(row.get('active', 1))

                scope_key = (label, degree, program, branch)
                existing_id = self._get_existing_record_id(conn, label, degree, program, branch)
                
                action = "Create"
                status = "New Record"
                
                if existing_id:
                    action = "Update"
                    status = f"Update ID: {existing_id}"
                
                if scope_key in seen_in_file:
                    status += " (Duplicate in file)"
                seen_in_file.add(scope_key)

                if execute:
                    try:
                        key = self._generate_key(label)
                        if existing_id:
                            conn.execute(sa_text("""
                                UPDATE rubric_criteria_catalog
                                SET description = :desc, active = :active, updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                            """), {"desc": description, "active": active, "id": existing_id})
                        else:
                            conn.execute(sa_text("""
                                INSERT INTO rubric_criteria_catalog 
                                (key, label, description, degree_code, program_code, branch_code, active, created_at, updated_at)
                                VALUES (:key, :label, :desc, :degree, :prog, :branch, :active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """), {
                                "key": key, "label": label, "desc": description,
                                "degree": degree, "prog": program, "branch": branch, "active": active
                            })
                        status = "Success"
                    except Exception as e:
                        status = f"Error: {str(e)}"

                report.append({
                    "Row": row_idx,
                    "Label": label,
                    "Degree": degree or "All",
                    "Prog/Branch": f"{program or ''}/{branch or ''}".strip('/'),
                    "Description": description[:30] + "..." if description else "(Empty)",
                    "Action": action,
                    "Status": status
                })
                
        return report

    def generate_template(self) -> bytes:
        df = pd.DataFrame([{
            'label': 'Content', 'description': 'Accuracy and depth', 'degree_code': 'BARCH',
            'program_code': '', 'branch_code': '', 'active': 1
        }, {
            'label': 'Presentation', 'description': 'Visual appeal', 'degree_code': '',
            'program_code': '', 'branch_code': '', 'active': 1
        }])
        output = BytesIO()
        df.to_csv(output, index=False)
        return output.getvalue()


def render_rubric_criteria_catalog_tab(engine: Engine, offering_id: int):
    st.subheader("🗂️ Criteria Catalog")
    st.markdown("Manage master criteria. Use **Dry Run** to check before importing.")
    
    service = RubricCriteriaService(engine)
    context = service.fetch_offering_context(offering_id)
    
    # 1. VIEW EXISTING
    with st.expander("👁️ View Existing Criteria", expanded=False):
        # Filter defaults to current degree
        degrees = [r['degree_code'] for r in service.fetch_all_criteria()]
        unique_degrees = sorted(list(set(filter(None, degrees))))
        
        default_idx = 0
        if context.get('degree_code') in unique_degrees:
            default_idx = unique_degrees.index(context['degree_code']) + 1 # +1 for "All"
            
        sel_degree = st.selectbox("Filter by Degree", ["All"] + unique_degrees, index=default_idx)
        criteria = service.fetch_all_criteria(sel_degree)
        
        if criteria:
            st.dataframe(pd.DataFrame(criteria)[['id', 'label', 'description', 'degree_code', 'program_code']], use_container_width=True, hide_index=True)
        else:
            st.info("No criteria found.")

    # 2. IMPORT SECTION
    st.markdown("#### 📥 Import / Update")
    col_d, col_u = st.columns([1, 2])
    with col_d:
        st.download_button("💾 Download Template", service.generate_template(), "criteria_template.csv", "text/csv")
    
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="cat_upload_main")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.write(f"Loaded {len(df)} rows.")
        
        # DRY RUN BUTTON
        if st.button("🔍 Run Dry Run (Check for Duplicates)", type="primary"):
            report = service.process_import(df, execute=False)
            st.session_state.cat_report = report
            
        if 'cat_report' in st.session_state:
            report_df = pd.DataFrame(st.session_state.cat_report)
            
            # Summary Metrics
            updates = len(report_df[report_df['Action'] == 'Update'])
            creates = len(report_df[report_df['Action'] == 'Create'])
            
            c1, c2 = st.columns(2)
            c1.metric("🆕 New Records", creates)
            c2.metric("♻️ Updates (Duplicate Label+Degree)", updates)
            
            def highlight(val):
                color = 'orange' if val == 'Update' else 'green'
                return f'color: {color}; font-weight: bold'

            st.dataframe(report_df.style.map(highlight, subset=['Action']), use_container_width=True)
            
            # EXECUTE BUTTON
            st.markdown("---")
            col_ex1, col_ex2 = st.columns([1, 4])
            with col_ex1:
                if st.button("🚀 Execute Import"):
                    final_report = service.process_import(df, execute=True)
                    st.success("✅ Import Complete!")
                    del st.session_state.cat_report
                    st.rerun()
            with col_ex2:
                if st.button("❌ Clear"):
                    del st.session_state.cat_report
                    st.rerun()
