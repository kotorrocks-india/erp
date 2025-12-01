# services/assignment_co_rubric_connector.py
"""
Assignment-CO-Rubric Integration Connector
Bridges the assignment system with existing CO and rubric schemas.

This module provides functions to:
1. Get available COs for an offering (from subject_cos table)
2. Validate CO mappings against offering's COs
3. Get available rubrics (from rubric_configs/rubric_criteria_catalog)
4. Link assignments to rubrics with proper validation
"""

from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AssignmentCORubricConnector:
    """Connector for CO and Rubric integration."""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def _exec(self, conn, sql: str, params: dict = None):
        """Execute SQL with parameters."""
        return conn.execute(sa_text(sql), params or {})
    
    # ===================================================================
    # COURSE OUTCOMES (COs) INTEGRATION
    # ===================================================================
    
    def get_cos_for_offering(self, offering_id: int) -> List[Dict]:
        """
        Get all COs defined for this offering from subject_cos table.
        
        Returns list of COs with structure:
        {
            'id': int,
            'co_code': str,
            'title': str,
            'description': str,
            'bloom_level': str,
            'weight_in_direct': float,
            'sequence': int,
            'po_correlations': {po_code: correlation_value},
            'pso_correlations': {pso_code: correlation_value},
            'peo_correlations': {peo_code: correlation_value}
        }
        """
        with self.engine.begin() as conn:
            # Get COs
            cos = self._exec(conn, """
            SELECT * FROM subject_cos
            WHERE offering_id = :offering_id
            ORDER BY sequence, co_code
            """, {"offering_id": offering_id}).fetchall()
            
            result = []
            for co in cos:
                co_dict = dict(co._mapping)
                
                # Get PO correlations
                po_corrs = self._exec(conn, """
                SELECT po_code, correlation_value FROM co_po_correlations
                WHERE co_id = :co_id
                """, {"co_id": co_dict['id']}).fetchall()
                co_dict['po_correlations'] = {r[0]: r[1] for r in po_corrs}
                
                # Get PSO correlations
                pso_corrs = self._exec(conn, """
                SELECT pso_code, correlation_value FROM co_pso_correlations
                WHERE co_id = :co_id
                """, {"co_id": co_dict['id']}).fetchall()
                co_dict['pso_correlations'] = {r[0]: r[1] for r in pso_corrs}
                
                # Get PEO correlations
                peo_corrs = self._exec(conn, """
                SELECT peo_code, correlation_value FROM co_peo_correlations
                WHERE co_id = :co_id
                """, {"co_id": co_dict['id']}).fetchall()
                co_dict['peo_correlations'] = {r[0]: r[1] for r in peo_corrs}
                
                result.append(co_dict)
            
            return result
    
    def validate_assignment_co_mapping(
        self,
        offering_id: int,
        co_mappings: Dict[str, int]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that assignment CO mappings reference valid COs for the offering.
        
        Args:
            offering_id: The subject offering ID
            co_mappings: Dict of {co_code: correlation_value}
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # Get valid COs for this offering
        valid_cos = self.get_cos_for_offering(offering_id)
        valid_co_codes = {co['co_code'] for co in valid_cos}
        
        # Check all mapped COs exist
        for co_code in co_mappings.keys():
            if co_code not in valid_co_codes:
                errors.append(f"CO '{co_code}' not defined for this offering")
        
        # Check at least one non-zero mapping
        if not any(v > 0 for v in co_mappings.values()):
            errors.append("At least one CO must have correlation > 0")
        
        # Check correlation values are in valid range (0-3)
        for co_code, value in co_mappings.items():
            if not (0 <= value <= 3):
                errors.append(f"CO '{co_code}' correlation must be 0-3 (got {value})")
        
        return (len(errors) == 0, errors)
    
    def get_assignment_co_coverage(self, offering_id: int) -> Dict:
        """
        Get coverage statistics for how assignments map to COs.
        
        Returns:
        {
            'total_cos': int,
            'covered_cos': int,
            'uncovered_cos': [co_codes],
            'coverage_percent': float,
            'co_assignment_counts': {co_code: assignment_count}
        }
        """
        with self.engine.begin() as conn:
            # Get all COs for offering
            cos = self.get_cos_for_offering(offering_id)
            total_cos = len(cos)
            co_codes = [co['co_code'] for co in cos]
            
            # Count assignments mapping to each CO
            co_counts = {}
            for co_code in co_codes:
                count = self._exec(conn, """
                SELECT COUNT(DISTINCT acm.assignment_id)
                FROM assignment_co_mapping acm
                JOIN assignments a ON acm.assignment_id = a.id
                WHERE a.offering_id = :offering_id
                AND acm.co_code = :co_code
                AND acm.correlation_value > 0
                AND a.status = 'published'
                """, {
                    "offering_id": offering_id,
                    "co_code": co_code
                }).fetchone()[0]
                
                co_counts[co_code] = count
            
            # Determine coverage
            covered_cos = sum(1 for count in co_counts.values() if count > 0)
            uncovered_cos = [co for co, count in co_counts.items() if count == 0]
            coverage_percent = (covered_cos / total_cos * 100) if total_cos > 0 else 0
            
            return {
                'total_cos': total_cos,
                'covered_cos': covered_cos,
                'uncovered_cos': uncovered_cos,
                'coverage_percent': coverage_percent,
                'co_assignment_counts': co_counts
            }
    
    # ===================================================================
    # RUBRICS INTEGRATION
    # ===================================================================
    
    def get_available_rubrics(
        self,
        degree_code: str = None,
        program_code: str = None,
        branch_code: str = None
    ) -> List[Dict]:
        """
        Get available rubrics from rubric_criteria_catalog.
        
        Filters by scope (degree/program/branch) if provided.
        Returns global rubrics if no scope specified.
        """
        with self.engine.begin() as conn:
            query = """
            SELECT * FROM rubric_criteria_catalog
            WHERE active = 1
            """
            params = {}
            
            if degree_code:
                query += " AND (degree_code = :degree_code OR degree_code IS NULL)"
                params['degree_code'] = degree_code
            
            if program_code:
                query += " AND (program_code = :program_code OR program_code IS NULL)"
                params['program_code'] = program_code
            
            if branch_code:
                query += " AND (branch_code = :branch_code OR branch_code IS NULL)"
                params['branch_code'] = branch_code
            
            query += " ORDER BY degree_code, program_code, branch_code, label"
            
            results = self._exec(conn, query, params).fetchall()
            return [dict(r._mapping) for r in results]
    
    def get_rubric_config_for_offering(self, offering_id: int) -> Optional[Dict]:
        """
        Get rubric configuration for an offering from rubric_configs table.
        
        Returns:
        {
            'id': int,
            'offering_id': int,
            'co_linking_enabled': bool,
            'normalization_enabled': bool,
            'visible_to_students': bool,
            'status': str,
            'is_locked': bool
        }
        """
        with self.engine.begin() as conn:
            result = self._exec(conn, """
            SELECT * FROM rubric_configs
            WHERE offering_id = :offering_id
            """, {"offering_id": offering_id}).fetchone()
            
            return dict(result._mapping) if result else None
    
    def validate_assignment_rubric(
        self,
        rubric_id: int,
        degree_code: str = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a rubric is available for use.
        
        Checks:
        1. Rubric exists in catalog
        2. Rubric is active
        3. Rubric scope matches assignment context
        """
        errors = []
        
        with self.engine.begin() as conn:
            rubric = self._exec(conn, """
            SELECT * FROM rubric_criteria_catalog
            WHERE id = :rubric_id
            """, {"rubric_id": rubric_id}).fetchone()
            
            if not rubric:
                errors.append(f"Rubric {rubric_id} not found")
                return (False, errors)
            
            rubric_dict = dict(rubric._mapping)
            
            if not rubric_dict['active']:
                errors.append(f"Rubric {rubric_id} is not active")
            
            # Check scope compatibility
            if degree_code and rubric_dict['degree_code']:
                if rubric_dict['degree_code'] != degree_code:
                    errors.append(
                        f"Rubric scope mismatch: "
                        f"rubric is for {rubric_dict['degree_code']}, "
                        f"assignment is for {degree_code}"
                    )
        
        return (len(errors) == 0, errors)
    
    def validate_rubric_weights(
        self,
        rubrics: List[Dict],
        rubric_mode: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate rubric weight configuration for Mode B.
        
        Args:
            rubrics: List of {rubric_id, top_level_weight_percent}
            rubric_mode: 'A' or 'B'
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        if rubric_mode == 'A':
            if len(rubrics) > 1:
                errors.append("Mode A allows only one rubric")
            elif len(rubrics) == 1 and rubrics[0].get('top_level_weight_percent', 100) != 100:
                errors.append("Mode A rubric must have 100% weight")
        
        elif rubric_mode == 'B':
            if len(rubrics) < 1:
                errors.append("Mode B requires at least one rubric")
            else:
                total_weight = sum(r.get('top_level_weight_percent', 0) for r in rubrics)
                if abs(total_weight - 100.0) > 0.01:
                    errors.append(
                        f"Mode B rubric weights must sum to 100% "
                        f"(currently: {total_weight}%)"
                    )
        
        return (len(errors) == 0, errors)
    
    # ===================================================================
    # INTEGRATED VALIDATION
    # ===================================================================
    
    def validate_assignment_for_publish(
        self,
        assignment_id: int,
        offering_id: int
    ) -> Tuple[bool, List[str]]:
        """
        Complete validation before publishing assignment.
        
        Checks:
        1. CO mappings are valid
        2. At least one CO mapped with value > 0
        3. Rubrics are valid (if attached)
        4. Rubric weights sum correctly (if Mode B)
        """
        errors = []
        
        with self.engine.begin() as conn:
            # Get assignment
            assignment = self._exec(conn, """
            SELECT * FROM assignments WHERE id = :id
            """, {"id": assignment_id}).fetchone()
            
            if not assignment:
                errors.append(f"Assignment {assignment_id} not found")
                return (False, errors)
            
            # Validate CO mappings
            co_mappings = self._exec(conn, """
            SELECT co_code, correlation_value
            FROM assignment_co_mapping
            WHERE assignment_id = :assignment_id
            """, {"assignment_id": assignment_id}).fetchall()
            
            co_map_dict = {r[0]: r[1] for r in co_mappings}
            
            if co_map_dict:
                is_valid, co_errors = self.validate_assignment_co_mapping(
                    offering_id,
                    co_map_dict
                )
                errors.extend(co_errors)
            else:
                errors.append("No CO mappings defined")
            
            # Validate rubrics
            rubrics = self._exec(conn, """
            SELECT * FROM assignment_rubrics
            WHERE assignment_id = :assignment_id
            """, {"assignment_id": assignment_id}).fetchall()
            
            if rubrics:
                rubric_list = [dict(r._mapping) for r in rubrics]
                rubric_mode = rubric_list[0]['rubric_mode']
                
                # Validate each rubric exists
                assignment_dict = dict(assignment._mapping)
                for rubric in rubric_list:
                    is_valid, rub_errors = self.validate_assignment_rubric(
                        rubric['rubric_id'],
                        assignment_dict['degree_code']
                    )
                    errors.extend(rub_errors)
                
                # Validate weights
                is_valid, weight_errors = self.validate_rubric_weights(
                    rubric_list,
                    rubric_mode
                )
                errors.extend(weight_errors)
        
        return (len(errors) == 0, errors)
    
    # ===================================================================
    # REPORTING & ANALYTICS
    # ===================================================================
    
    def get_co_attainment_summary(self, offering_id: int) -> Dict:
        """
        Get CO attainment summary across all assignments.
        
        Returns:
        {
            'co_code': {
                'total_assignments': int,
                'avg_correlation': float,
                'total_marks_allocated': float,
                'scaled_marks_allocated': float
            }
        }
        """
        with self.engine.begin() as conn:
            # Get all assignments for offering
            assignments = self._exec(conn, """
            SELECT id, max_marks, bucket, status
            FROM assignments
            WHERE offering_id = :offering_id
            AND status = 'published'
            """, {"offering_id": offering_id}).fetchall()
            
            # Get offering marks structure
            offering = self._exec(conn, """
            SELECT internal_marks_max, exam_marks_max
            FROM subject_offerings
            WHERE id = :id
            """, {"id": offering_id}).fetchone()
            
            # Calculate per CO
            cos = self.get_cos_for_offering(offering_id)
            summary = {}
            
            for co in cos:
                co_code = co['co_code']
                
                # Get assignments mapping to this CO
                mapped_assignments = self._exec(conn, """
                SELECT a.id, a.max_marks, a.bucket, acm.correlation_value
                FROM assignments a
                JOIN assignment_co_mapping acm ON a.id = acm.assignment_id
                WHERE a.offering_id = :offering_id
                AND acm.co_code = :co_code
                AND acm.correlation_value > 0
                AND a.status = 'published'
                """, {
                    "offering_id": offering_id,
                    "co_code": co_code
                }).fetchall()
                
                if mapped_assignments:
                    total_assignments = len(mapped_assignments)
                    avg_correlation = sum(r[3] for r in mapped_assignments) / total_assignments
                    
                    # Calculate marks allocated
                    internal_marks = sum(r[1] for r in mapped_assignments if r[2] == 'Internal')
                    external_marks = sum(r[1] for r in mapped_assignments if r[2] == 'External')
                    
                    # Calculate scaling factors
                    internal_total = sum(a[1] for a in assignments if a[2] == 'Internal')
                    external_total = sum(a[1] for a in assignments if a[2] == 'External')
                    
                    internal_scale = offering[0] / internal_total if internal_total > 0 else 0
                    external_scale = offering[1] / external_total if external_total > 0 else 0
                    
                    scaled_internal = internal_marks * internal_scale
                    scaled_external = external_marks * external_scale
                    
                    summary[co_code] = {
                        'total_assignments': total_assignments,
                        'avg_correlation': avg_correlation,
                        'raw_marks_allocated': internal_marks + external_marks,
                        'scaled_marks_allocated': scaled_internal + scaled_external,
                        'internal_raw': internal_marks,
                        'external_raw': external_marks,
                        'internal_scaled': scaled_internal,
                        'external_scaled': scaled_external
                    }
                else:
                    summary[co_code] = {
                        'total_assignments': 0,
                        'avg_correlation': 0,
                        'raw_marks_allocated': 0,
                        'scaled_marks_allocated': 0,
                        'internal_raw': 0,
                        'external_raw': 0,
                        'internal_scaled': 0,
                        'external_scaled': 0
                    }
            
            return summary


if __name__ == "__main__":
    # Test connector
    from sqlalchemy import create_engine
    
    print("\n" + "="*60)
    print("TESTING ASSIGNMENT CO/RUBRIC CONNECTOR")
    print("="*60 + "\n")
    
    engine = create_engine("sqlite:///test.db")
    connector = AssignmentCORubricConnector(engine)
    
    print("✅ Connector initialized successfully!")
    print("\n" + "="*60 + "\n")
