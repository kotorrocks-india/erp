# screens/subject_cos_rubrics/mass_import_service.py
"""
Service for Mass Importing Course Outcomes (COs).
UPDATED: Added Dry Run/Preview capability and refactored parsing logic.
"""

import pandas as pd
import logging
from io import BytesIO
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import List, Dict, Set, Tuple, Any

from screens.subject_cos_rubrics.course_outcomes_tab import save_co, fetch_cos_for_offering

logger = logging.getLogger(__name__)

class MassImportService:
    
    def __init__(self, engine: Engine):
        self.engine = engine

    def _get_offering_map(self, degree_code: str, ay_label: str) -> Dict[str, int]:
        """Returns {subject_code: offering_id} for published offerings."""
        with self.engine.begin() as conn:
            query = """
                SELECT subject_code, id 
                FROM subject_offerings
                WHERE degree_code = :degree_code 
                AND ay_label = :ay_label
                AND status = 'published'
            """
            rows = conn.execute(sa_text(query), {"degree_code": degree_code, "ay_label": ay_label}).fetchall()
            return {row[0].upper(): row[1] for row in rows}

    def _fetch_all_outcome_codes(self, degree_code: str) -> Dict[str, List[str]]:
        """Fetches all active PO, PSO, and PEO codes for the degree."""
        outcomes = {'pos': [], 'psos': [], 'peos': []}
        with self.engine.begin() as conn:
            query = """
                SELECT os.set_type, oi.code
                FROM outcomes_items oi
                JOIN outcomes_sets os ON oi.set_id = os.id
                WHERE os.degree_code = :degree_code
                AND os.status = 'published'
                AND os.is_current = 1
                ORDER BY oi.sort_order, oi.code
            """
            rows = conn.execute(sa_text(query), {"degree_code": degree_code}).fetchall()
            for set_type, code in rows:
                if set_type in outcomes:
                    outcomes[set_type].append(code)
        return outcomes

    def generate_co_template(self, degree_code: str, weight_mode: str = 'weighted') -> bytes:
        """Generates CO import template with dynamic columns."""
        outcomes = self._fetch_all_outcome_codes(degree_code)
        
        columns = ["subject_code", "co_code", "title", "description", "bloom_level"]
        if weight_mode == 'weighted':
            columns.append("weight_in_direct")
            
        columns.extend(outcomes['pos'])
        columns.extend(outcomes['psos'])
        columns.extend(outcomes['peos'])
        
        sample_row = {
            "subject_code": "C901", "co_code": "CO1", "title": "Sample CO",
            "description": "...", "bloom_level": "Apply"
        }
        if weight_mode == 'weighted':
            sample_row["weight_in_direct"] = 0.2
        if outcomes['pos']: sample_row[outcomes['pos'][0]] = 3
        
        df = pd.DataFrame([sample_row], columns=columns)
        output = BytesIO()
        df.to_csv(output, index=False)
        return output.getvalue()

    # ========================================================
    # PARSING HELPER (Used by both Dry Run and Import)
    # ========================================================
    def _parse_row(self, row: pd.Series, df_columns: List[str], 
                   valid_po_set: Set[str], valid_pso_set: Set[str], valid_peo_set: Set[str],
                   weight_mode: str) -> Tuple[Dict, List[str]]:
        """
        Parses a single row and returns (co_data_dict, error_list).
        Does NOT check database existence (done separately).
        """
        errors = []
        
        # 1. Parse Correlations
        po_corrs = {}
        pso_corrs = {}
        peo_corrs = {}

        for col in df_columns:
            col_name = str(col).strip()
            # Skip non-correlation columns or empty values
            if pd.isna(row[col]) or str(row[col]).strip() == '': 
                continue
                
            try:
                val = int(float(row[col]))
            except ValueError: 
                continue # Ignore non-numeric values in correlation columns
            
            if val not in [0, 1, 2, 3]: 
                continue # Ignore invalid ranges

            if col_name in valid_po_set: po_corrs[col_name] = val
            elif col_name in valid_pso_set: pso_corrs[col_name] = val
            elif col_name in valid_peo_set: peo_corrs[col_name] = val
        
        # 2. Parse Weight
        weight = 0.0
        if weight_mode == 'weighted' and 'weight_in_direct' in row:
             try: weight = float(row['weight_in_direct'])
             except: weight = 0.0
        
        # 3. Parse Sequence
        try: seq = int(row.get('sequence', 1))
        except: seq = 1

        # 4. Build Data Object
        co_data = {
            'co_code': str(row['co_code']).strip(),
            'title': str(row.get('title', row['co_code'])).strip(),
            'description': str(row['description']).strip(),
            'bloom_level': str(row.get('bloom_level', 'Remember')).strip(),
            'sequence': seq,
            'weight_in_direct': weight,
            'status': str(row.get('status', 'draft')).strip(),
            'po_correlations': po_corrs,
            'pso_correlations': pso_corrs,
            'peo_correlations': peo_corrs
        }
        
        # Basic validation
        if not co_data['co_code']: errors.append("Missing CO Code")
        if not co_data['description']: errors.append("Missing Description")
        
        return co_data, errors

    # ========================================================
    # DRY RUN / PREVIEW
    # ========================================================
    def dry_run_import(self, df: pd.DataFrame, degree_code: str, ay_label: str, weight_mode: str) -> List[Dict]:
        """
        Simulates the import process and returns a report list.
        Each item in list: {row_id, subject, co, action, status, errors, po_count, ...}
        """
        report = []
        offering_map = self._get_offering_map(degree_code, ay_label)
        valid_outcomes = self._fetch_all_outcome_codes(degree_code)
        
        valid_po_set = set(valid_outcomes['pos'])
        valid_pso_set = set(valid_outcomes['psos'])
        valid_peo_set = set(valid_outcomes['peos'])

        required_cols = ['subject_code', 'co_code', 'description']
        if not all(col in df.columns for col in required_cols):
            return [{"row": 0, "status": "Critical Error", "errors": [f"Missing columns: {required_cols}"]}]

        # Pre-fetch existing COs for all mapped offerings to optimize "Update" check
        existing_cos_map = {} # {offering_id: {co_code}}
        for off_id in offering_map.values():
            cos = fetch_cos_for_offering(self.engine, off_id)
            existing_cos_map[off_id] = {c['co_code'] for c in cos}

        for index, row in df.iterrows():
            row_status = "Valid"
            row_errors = []
            action = "Create"
            
            # 1. Check Subject
            subj_code = str(row['subject_code']).strip().upper()
            offering_id = offering_map.get(subj_code)
            
            if not offering_id:
                row_status = "Invalid"
                row_errors.append(f"Subject '{subj_code}' not found/published")
            
            # 2. Parse Data
            if row_status != "Invalid": # Only parse if subject exists
                co_data, parse_errors = self._parse_row(row, df.columns, valid_po_set, valid_pso_set, valid_peo_set, weight_mode)
                row_errors.extend(parse_errors)
                
                if row_errors:
                    row_status = "Invalid"
                else:
                    # Check for Update vs Create
                    if co_data['co_code'] in existing_cos_map.get(offering_id, set()):
                        action = "Update"
            else:
                co_data = {"po_correlations": {}, "co_code": row.get('co_code', 'Unknown')}

            report.append({
                "Row": index + 1,
                "Subject": subj_code,
                "CO Code": co_data.get('co_code', ''),
                "Action": action if row_status == "Valid" else "-",
                "Status": row_status,
                "PO Count": len(co_data.get('po_correlations', {})),
                "Errors": "; ".join(row_errors) if row_errors else ""
            })
            
        return report

    # ========================================================
    # ACTUAL IMPORT (EXECUTE)
    # ========================================================
    def mass_import_cos(self, df: pd.DataFrame, degree_code: str, ay_label: str, actor: str, weight_mode: str) -> Dict:
        results = {"success": 0, "failed": 0, "errors": [], "skipped": 0}
        offering_map = self._get_offering_map(degree_code, ay_label)
        valid_outcomes = self._fetch_all_outcome_codes(degree_code)
        
        valid_po_set = set(valid_outcomes['pos'])
        valid_pso_set = set(valid_outcomes['psos'])
        valid_peo_set = set(valid_outcomes['peos'])
        
        touched_offerings = set()

        for index, row in df.iterrows():
            try:
                subj_code = str(row['subject_code']).strip().upper()
                if subj_code not in offering_map:
                    results['errors'].append(f"Row {index+1}: Subject '{subj_code}' skipped")
                    results['failed'] += 1
                    continue

                offering_id = offering_map[subj_code]
                touched_offerings.add(offering_id)

                # Use shared parser
                co_data, parse_errors = self._parse_row(row, df.columns, valid_po_set, valid_pso_set, valid_peo_set, weight_mode)
                
                if parse_errors:
                    results['failed'] += 1
                    results['errors'].append(f"Row {index+1}: {'; '.join(parse_errors)}")
                    continue

                # Find existing ID
                existing_cos = fetch_cos_for_offering(self.engine, offering_id)
                existing_co = next((c for c in existing_cos if c['co_code'] == co_data['co_code']), None)
                co_id = existing_co['id'] if existing_co else None

                # Execute Save
                success = save_co(self.engine, offering_id, co_data, co_id)
                
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Row {index+1}: DB Save Failed for {co_data['co_code']}")

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Row {index+1}: Exception: {str(e)}")

        # Post-Processing
        if touched_offerings:
            try:
                if weight_mode == 'equal':
                    self._rebalance_equal_weights(list(touched_offerings))
                    self._set_mode(list(touched_offerings), 'equal')
                elif weight_mode == 'weighted':
                    self._set_mode(list(touched_offerings), 'weighted')
            except Exception as e:
                results['errors'].append(f"Warning during rebalancing: {e}")

        return results

    def _set_mode(self, offering_ids: List[int], mode: str):
        with self.engine.begin() as conn:
            for oid in offering_ids:
                conn.execute(sa_text("UPDATE subject_offerings SET co_weightage_type=:mode WHERE id=:id"), 
                           {"mode": mode, "id": oid})

    def _rebalance_equal_weights(self, offering_ids: List[int]):
        with self.engine.begin() as conn:
            for oid in offering_ids:
                cnt = conn.execute(sa_text("SELECT COUNT(*) FROM subject_cos WHERE offering_id=:oid"), {"oid": oid}).scalar()
                if cnt > 0:
                    val = 1.0 / cnt
                    conn.execute(sa_text("UPDATE subject_cos SET weight_in_direct=:val WHERE offering_id=:oid"), 
                               {"val": val, "oid": oid})
