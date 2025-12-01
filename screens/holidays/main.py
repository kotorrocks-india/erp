# screens/holidays/main.py
import logging
import json
from datetime import datetime, date
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
import pandas as pd

logger = logging.getLogger(__name__)

class HolidayManager:
    """
    Manages logic for Holidays & Academic Calendar (Slide 26).
    Handles scope precedence: Branch > Program > Degree > Institution.
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine

    def _exec(self, sql, params=None):
        with self.engine.begin() as conn:
            return conn.execute(sa_text(sql), params or {})

    # ============================================================
    # READ OPERATIONS
    # ============================================================

    def get_holidays(self, ay_code: str = None, start_date: date = None, end_date: date = None):
        """
        Fetch holidays with optional filtering. 
        Returns raw list without resolving hierarchy.
        """
        query = """
            SELECT h.*, 
                   d.title as degree_name, 
                   p.program_name, 
                   b.branch_name
            FROM holidays h
            LEFT JOIN degrees d ON h.degree_code = d.code
            LEFT JOIN programs p ON h.program_code = p.program_code
            LEFT JOIN branches b ON h.branch_code = b.branch_code
            WHERE 1=1
        """
        params = {}
        
        if ay_code:
            # Match specific AY pin OR date range overlap if AY logic requires it
            # For simplicity, we filter by the explicit FK or date range if we knew AY dates
            query += " AND (h.ay_code = :ay_code OR h.ay_code IS NULL)"
            params['ay_code'] = ay_code
            
        if start_date:
            query += " AND h.date >= :start_date"
            params['start_date'] = start_date
            
        if end_date:
            query += " AND h.date <= :end_date"
            params['end_date'] = end_date
            
        query += " ORDER BY h.date, h.scope_level DESC"
        
        with self.engine.connect() as conn:
            return pd.read_sql(sa_text(query), conn, params=params)

    def check_is_holiday(self, check_date: date, degree_code: str, 
                         program_code: str = None, branch_code: str = None) -> dict:
        """
        Determines if a specific date is a holiday for a specific student context.
        Implements the "Order of Precedence": Branch > Program > Degree > Institution.
        
        Returns:
            {
                'is_holiday': bool,
                'is_working_saturday': bool,
                'title': str,
                'scope_applied': str
            }
        """
        # We fetch ALL entries for this date across all relevant scopes
        query = """
            SELECT * FROM holidays 
            WHERE date = :date
            AND (
                scope_level = 'institution'
                OR (scope_level = 'degree' AND degree_code = :degree)
                OR (scope_level = 'program' AND degree_code = :degree AND program_code = :program)
                OR (scope_level = 'branch' AND degree_code = :degree AND program_code = :program AND branch_code = :branch)
            )
            ORDER BY 
                CASE scope_level 
                    WHEN 'branch' THEN 1 
                    WHEN 'program' THEN 2 
                    WHEN 'degree' THEN 3 
                    WHEN 'institution' THEN 4 
                END ASC
            LIMIT 1
        """
        
        with self.engine.connect() as conn:
            result = conn.execute(sa_text(query), {
                'date': check_date,
                'degree': degree_code,
                'program': program_code,
                'branch': branch_code
            }).fetchone()
            
            if not result:
                return {'is_holiday': False, 'is_working_saturday': False, 'title': None, 'scope_applied': None}
            
            row = dict(result._mapping)
            
            # If it's a "Working Saturday" override, it is NOT a holiday effectively
            if row['is_working_saturday']:
                return {
                    'is_holiday': False, 
                    'is_working_saturday': True, 
                    'title': row['title'], # e.g., "Compensatory Working Day"
                    'scope_applied': row['scope_level']
                }
            
            return {
                'is_holiday': True,
                'is_working_saturday': False,
                'title': row['title'],
                'scope_applied': row['scope_level']
            }

    # ============================================================
    # WRITE OPERATIONS
    # ============================================================

    def save_holiday(self, data: dict, actor: str) -> tuple[bool, str]:
        """
        Create or Update a holiday.
        Performs validation against Academic Year dates.
        """
        try:
            # 1. Validation: Date must be valid
            if not data.get('date') or not data.get('title'):
                return False, "Date and Title are required."

            # 2. Validation: If AY is provided, date must be within range
            if data.get('ay_code'):
                with self.engine.connect() as conn:
                    ay = conn.execute(sa_text(
                        "SELECT start_date, end_date FROM academic_years WHERE ay_code = :ay"
                    ), {'ay': data['ay_code']}).fetchone()
                    
                    if ay:
                        h_date = str(data['date'])
                        if not (ay.start_date <= h_date <= ay.end_date):
                            return False, f"Date {h_date} is outside the selected Academic Year range."

            # 3. Validation: Scope Integrity
            scope = data.get('scope_level', 'institution')
            if scope == 'degree' and not data.get('degree_code'):
                return False, "Degree Code required for Degree scope."
            if scope == 'branch' and not data.get('branch_code'):
                return False, "Branch Code required for Branch scope."

            # 4. Upsert Logic
            cols = [
                'date', 'title', 'scope_level', 'degree_code', 'program_code', 'branch_code',
                'ay_code', 'is_working_saturday', 'notes', 'source', 'updated_by'
            ]
            
            if 'id' not in data:
                cols.append('created_by')
                
            # Construct SQL
            if 'id' in data and data['id']:
                # UPDATE
                set_clause = ", ".join([f"{c} = :{c}" for c in cols])
                sql = f"UPDATE holidays SET {set_clause} WHERE id = :id"
                data['updated_by'] = actor
                self._exec(sql, data)
                self._audit_log(data['id'], 'update', actor, f"Updated holiday {data['title']}")
            else:
                # INSERT
                cols_str = ", ".join(cols)
                vals_str = ", ".join([f":{c}" for c in cols])
                sql = f"INSERT INTO holidays ({cols_str}) VALUES ({vals_str})"
                data['created_by'] = actor
                data['updated_by'] = actor
                
                with self.engine.begin() as conn:
                    conn.execute(sa_text(sql), data)
                    # Get ID for audit
                    new_id = conn.execute(sa_text("SELECT last_insert_rowid()")).fetchone()[0]
                
                self._audit_log(new_id, 'create', actor, f"Created holiday {data['title']}")

            return True, "Holiday saved successfully."

        except Exception as e:
            logger.error(f"Save holiday failed: {e}")
            return False, str(e)

    def delete_holiday(self, holiday_id: int, actor: str, reason: str = None) -> bool:
        """
        Delete a holiday with audit log.
        """
        with self.engine.begin() as conn:
            # Fetch for audit
            old = conn.execute(sa_text("SELECT * FROM holidays WHERE id = :id"), {'id': holiday_id}).fetchone()
            if not old:
                return False
            
            # Delete
            conn.execute(sa_text("DELETE FROM holidays WHERE id = :id"), {'id': holiday_id})
            
            # Audit (Manual insertion because we deleted the row)
            audit_sql = """
                INSERT INTO holidays_audit (holiday_id, action, title, reason, actor, occurred_at)
                VALUES (:hid, 'delete', :title, :reason, :actor, CURRENT_TIMESTAMP)
            """
            conn.execute(sa_text(audit_sql), {
                'hid': holiday_id,
                'title': old.title,
                'reason': reason,
                'actor': actor
            })
            return True

    def _audit_log(self, holiday_id, action, actor, note):
        """Helper to write to audit table."""
        try:
            with self.engine.begin() as conn:
                conn.execute(sa_text("""
                    INSERT INTO holidays_audit (holiday_id, action, actor, reason)
                    VALUES (:id, :action, :actor, :note)
                """), {'id': holiday_id, 'action': action, 'actor': actor, 'note': note})
        except Exception as e:
            logger.error(f"Audit failed: {e}")
