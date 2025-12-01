# app/core/student_status_engine.py
"""
Student Status Rules Engine

Automatically computes student status based on:
- Fee payment status
- Academic performance (attendance, marks, backlogs)
- Historical performance (previous semesters/AYs)
- Configured institutional rules

This runs as:
1. Scheduled job (nightly) to update all students
2. On-demand when marks/attendance are published
3. Manual trigger from admin interface
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.engine import Engine, Connection
from sqlalchemy import text as sa_text
from datetime import datetime
import json
import logging

log = logging.getLogger(__name__)


class StudentStatusEngine:
    """Compute student status based on institutional rules."""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def compute_student_status(
        self, 
        student_profile_id: int, 
        ay_code: str, 
        semester_number: int,
        commit: bool = True
    ) -> Dict[str, Any]:
        """
        Compute status for a single student in a specific AY/semester.
        
        Returns:
            {
                'status': 'Good'|'Hold'|'Detained',
                'reason': 'explanation',
                'internal_eligible': True|False,
                'external_eligible': True|False,
                'rules_matched': [rule_ids],
                'winning_rule': rule_id
            }
        """
        with self.engine.begin() as conn:
            # 1. Gather student data
            student_data = self._gather_student_data(conn, student_profile_id, ay_code, semester_number)
            
            if not student_data:
                return {'status': 'Good', 'reason': 'No data available', 'internal_eligible': True, 'external_eligible': True}
            
            # 2. Get active rules
            rules = self._get_active_rules(conn, student_data.get('degree_code'))
            
            # 3. Evaluate rules
            matched_rules = self._evaluate_rules(conn, rules, student_data, student_profile_id)
            
            # 4. Select winning rule (highest priority)
            winning_rule = self._select_winning_rule(matched_rules)
            
            # 5. Determine eligibility
            internal_eligible, external_eligible = self._determine_eligibility(winning_rule, student_data)
            
            # 6. Build result
            result = {
                'status': winning_rule['target_status'] if winning_rule else 'Good',
                'reason': winning_rule['description'] if winning_rule else 'All criteria met',
                'internal_eligible': internal_eligible,
                'external_eligible': external_eligible,
                'rules_matched': [r['id'] for r in matched_rules],
                'winning_rule': winning_rule['id'] if winning_rule else None
            }
            
            # 7. Log computation
            self._log_computation(conn, student_profile_id, ay_code, semester_number, student_data, result)
            
            # 8. Update student_profiles.status if commit=True
            if commit:
                self._update_student_status(conn, student_profile_id, result['status'], result['reason'])
            
            return result
    
    def _gather_student_data(
        self, 
        conn: Connection, 
        student_profile_id: int, 
        ay_code: str, 
        semester_number: int
    ) -> Dict[str, Any]:
        """Gather all relevant data for status computation."""
        
        # Get current semester performance
        perf = conn.execute(sa_text("""
            SELECT 
                attendance_percentage, internal_percentage, external_percentage,
                sgpa, cgpa, active_backlogs, detained, eligible_for_externals,
                degree_code, batch, current_year, computed_status
            FROM student_semester_performance
            WHERE student_profile_id = :sid AND ay_code = :ay AND semester_number = :sem
        """), {"sid": student_profile_id, "ay": ay_code, "sem": semester_number}).fetchone()
        
        if not perf:
            return {}
        
        # Get fee status for current semester
        fee = conn.execute(sa_text("""
            SELECT status FROM student_fee_payments
            WHERE student_profile_id = :sid AND ay_code = :ay AND semester_number = :sem
            ORDER BY created_at DESC LIMIT 1
        """), {"sid": student_profile_id, "ay": ay_code, "sem": semester_number}).fetchone()
        
        # Get previous semester performance (for lookback rules)
        prev_perf = conn.execute(sa_text("""
            SELECT sgpa, attendance_percentage, active_backlogs
            FROM student_semester_performance
            WHERE student_profile_id = :sid AND ay_code = :ay AND semester_number = :prev_sem
        """), {"sid": student_profile_id, "ay": ay_code, "prev_sem": semester_number - 1}).fetchone()
        
        return {
            'attendance_percentage': perf[0] or 0,
            'internal_percentage': perf[1] or 0,
            'external_percentage': perf[2] or 0,
            'sgpa': perf[3] or 0,
            'cgpa': perf[4] or 0,
            'active_backlogs': perf[5] or 0,
            'detained': perf[6] or 0,
            'eligible_for_externals': perf[7] or 1,
            'degree_code': perf[8],
            'batch': perf[9],
            'current_year': perf[10],
            'current_status': perf[11],
            'fee_status': fee[0] if fee else 'pending',
            'prev_sgpa': prev_perf[0] if prev_perf else None,
            'prev_attendance': prev_perf[1] if prev_perf else None,
            'prev_backlogs': prev_perf[2] if prev_perf else None,
        }
    
    def _get_active_rules(self, conn: Connection, degree_code: str = None) -> List[Dict[str, Any]]:
        """Get all active rules, optionally filtered by degree."""
        query = """
            SELECT id, rule_code, rule_name, rule_category, rule_type,
                   condition_field, operator, threshold_value,
                   lookback_semesters, lookback_scope,
                   target_status, target_eligibility, priority, description
            FROM student_status_rules
            WHERE active = 1
        """
        params = {}
        
        if degree_code:
            query += " AND (degree_code IS NULL OR degree_code = :degree)"
            params['degree'] = degree_code
        
        query += " ORDER BY priority ASC"
        
        rows = conn.execute(sa_text(query), params).fetchall()
        
        return [dict(zip([
            'id', 'rule_code', 'rule_name', 'rule_category', 'rule_type',
            'condition_field', 'operator', 'threshold_value',
            'lookback_semesters', 'lookback_scope',
            'target_status', 'target_eligibility', 'priority', 'description'
        ], row)) for row in rows]
    
    def _evaluate_rules(
        self, 
        conn: Connection, 
        rules: List[Dict[str, Any]], 
        student_data: Dict[str, Any],
        student_profile_id: int
    ) -> List[Dict[str, Any]]:
        """Evaluate all rules against student data. Returns list of matched rules."""
        matched = []
        
        for rule in rules:
            # Get the value to test
            if rule['lookback_semesters'] > 0:
                # Use previous semester data
                field = f"prev_{rule['condition_field']}"
                value = student_data.get(field)
            else:
                # Use current semester data
                value = student_data.get(rule['condition_field'])
            
            if value is None:
                continue
            
            # Evaluate condition
            threshold = rule['threshold_value']
            operator = rule['operator']
            
            # Convert types appropriately
            if rule['rule_type'] == 'threshold':
                try:
                    value = float(value)
                    threshold = float(threshold)
                except:
                    continue
            
            # Apply operator
            match = False
            if operator == '<':
                match = value < threshold
            elif operator == '>':
                match = value > threshold
            elif operator == '<=':
                match = value <= threshold
            elif operator == '>=':
                match = value >= threshold
            elif operator == '==':
                match = str(value) == str(threshold)
            elif operator == '!=':
                match = str(value) != str(threshold)
            
            if match:
                matched.append(rule)
        
        return matched
    
    def _select_winning_rule(self, matched_rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select the winning rule (lowest priority number = highest priority)."""
        if not matched_rules:
            return None
        
        return min(matched_rules, key=lambda r: r['priority'])
    
    def _determine_eligibility(
        self, 
        winning_rule: Optional[Dict[str, Any]], 
        student_data: Dict[str, Any]
    ) -> Tuple[bool, bool]:
        """Determine internal and external exam eligibility."""
        if not winning_rule:
            return True, True
        
        eligibility = winning_rule.get('target_eligibility', 'both')
        
        if eligibility == 'both':
            return True, True
        elif eligibility == 'internal_only':
            return True, False
        elif eligibility == 'external_only':
            return False, True
        elif eligibility == 'none':
            return False, False
        
        return True, True
    
    def _log_computation(
        self,
        conn: Connection,
        student_profile_id: int,
        ay_code: str,
        semester_number: int,
        student_data: Dict[str, Any],
        result: Dict[str, Any]
    ):
        """Log the status computation for audit trail."""
        
        # Get current status to check if it changed
        current = conn.execute(sa_text(
            "SELECT status FROM student_profiles WHERE id = :id"
        ), {"id": student_profile_id}).fetchone()
        
        previous_status = current[0] if current else None
        status_changed = previous_status != result['status']
        
        conn.execute(sa_text("""
            INSERT INTO student_status_computation_log (
                student_profile_id, enrollment_id, ay_code, semester_number,
                attendance_pct, internal_pct, external_pct, active_backlogs, fee_status,
                rules_evaluated, rules_matched, winning_rule_id,
                computed_status, previous_status, status_changed, reason,
                internal_eligible, external_eligible, computed_by
            ) VALUES (
                :sid, :eid, :ay, :sem,
                :att, :int, :ext, :back, :fee,
                :eval, :match, :win,
                :status, :prev, :changed, :reason,
                :int_elig, :ext_elig, :by
            )
        """), {
            "sid": student_profile_id,
            "eid": None,  # TODO: fetch from student_enrollments
            "ay": ay_code,
            "sem": semester_number,
            "att": student_data.get('attendance_percentage'),
            "int": student_data.get('internal_percentage'),
            "ext": student_data.get('external_percentage'),
            "back": student_data.get('active_backlogs'),
            "fee": student_data.get('fee_status'),
            "eval": json.dumps([]),  # All rules evaluated
            "match": json.dumps(result.get('rules_matched', [])),
            "win": result.get('winning_rule'),
            "status": result['status'],
            "prev": previous_status,
            "changed": 1 if status_changed else 0,
            "reason": result['reason'],
            "int_elig": 1 if result['internal_eligible'] else 0,
            "ext_elig": 1 if result['external_eligible'] else 0,
            "by": "system_auto"
        })
    
    def _update_student_status(self, conn: Connection, student_profile_id: int, status: str, reason: str):
        """Update the student's status in student_profiles table."""
        
        # Also log to status audit
        old_status = conn.execute(sa_text(
            "SELECT status FROM student_profiles WHERE id = :id"
        ), {"id": student_profile_id}).fetchone()
        
        conn.execute(sa_text("""
            UPDATE student_profiles SET status = :status, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"status": status, "id": student_profile_id})
        
        if old_status and old_status[0] != status:
            conn.execute(sa_text("""
                INSERT INTO student_status_audit (student_profile_id, from_status, to_status, reason, changed_by)
                VALUES (:sid, :from, :to, :reason, :by)
            """), {
                "sid": student_profile_id,
                "from": old_status[0],
                "to": status,
                "reason": f"Auto-computed: {reason}",
                "by": "system_rules_engine"
            })
    
    def compute_batch_status(self, degree_code: str, batch: str, ay_code: str, semester_number: int) -> Dict[str, int]:
        """Compute status for all students in a batch. Returns summary counts."""
        
        with self.engine.connect() as conn:
            students = conn.execute(sa_text("""
                SELECT DISTINCT p.id
                FROM student_profiles p
                JOIN student_enrollments e ON p.id = e.student_profile_id
                WHERE e.degree_code = :degree AND e.batch = :batch AND e.is_primary = 1
            """), {"degree": degree_code, "batch": batch}).fetchall()
        
        summary = {'Good': 0, 'Hold': 0, 'Detained': 0, 'Total': len(students)}
        
        for student in students:
            result = self.compute_student_status(student[0], ay_code, semester_number, commit=True)
            summary[result['status']] = summary.get(result['status'], 0) + 1
        
        return summary


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE EXAMPLES
# ═══════════════════════════════════════════════════════════════════════════════

def example_compute_single_student(engine: Engine):
    """Example: Compute status for one student."""
    status_engine = StudentStatusEngine(engine)
    
    result = status_engine.compute_student_status(
        student_profile_id=123,
        ay_code="2024-25",
        semester_number=3,
        commit=True  # Actually update the database
    )
    
    print(f"Status: {result['status']}")
    print(f"Reason: {result['reason']}")
    print(f"Can appear for internals: {result['internal_eligible']}")
    print(f"Can appear for externals: {result['external_eligible']}")


def example_compute_entire_batch(engine: Engine):
    """Example: Compute status for all students in a batch."""
    status_engine = StudentStatusEngine(engine)
    
    summary = status_engine.compute_batch_status(
        degree_code="BTech",
        batch="2021",
        ay_code="2024-25",
        semester_number=6
    )
    
    print(f"Total students: {summary['Total']}")
    print(f"Good standing: {summary.get('Good', 0)}")
    print(f"On hold: {summary.get('Hold', 0)}")
    print(f"Detained: {summary.get('Detained', 0)}")
