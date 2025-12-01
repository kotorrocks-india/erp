# screens/rubrics/rubrics_service.py
"""
Rubrics Service Layer.
Manages Global Criteria Catalog and Subject Configurations.
Updated: Added Robust Import with Dry Run and Degree/Program/Branch Scoping.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import logging
import pandas as pd
from io import BytesIO
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)

# --- Local Model Definitions ---

@dataclass
class RubricConfig:
    offering_id: int
    co_linking_enabled: int
    normalization_enabled: int
    visible_to_students: int
    version: int = 1
    is_locked: int = 0
    status: str = 'draft'
    copied_from_config_id: Optional[int] = None

@dataclass
class AuditEntry:
    actor_id: str
    actor_role: str
    operation: str
    reason: Optional[str] = None
    source: str = 'ui'
    step_up_performed: int = 0


class RubricsService:
    """Complete service for managing rubrics definitions."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def _exec(self, conn, sql: str, params: dict = None):
        return conn.execute(sa_text(sql), params or {})

    def _fetch_one(self, sql: str, params: dict = None):
        with self.engine.begin() as conn:
            result = conn.execute(sa_text(sql), params or {}).fetchone()
            return dict(result._mapping) if result else None

    def _fetch_all(self, sql: str, params: dict = None):
        with self.engine.begin() as conn:
            result = conn.execute(sa_text(sql), params or {}).fetchall()
            return [dict(row._mapping) for row in result]

    # ========================================================================
    # CRITERIA CATALOG OPERATIONS (CRUD)
    # ========================================================================

    def get_criteria_catalog(self, active_only: bool = True) -> List[Dict]:
        """Get criteria catalog."""
        where = "WHERE active = 1" if active_only else ""
        return self._fetch_all(f"""
        SELECT * FROM rubric_criteria_catalog {where}
        ORDER BY degree_code, program_code, branch_code, label
        """)

    def add_catalog_criterion(self, key: str, label: str, description: str = None, 
                              degree_code: str = None, program_code: str = None, branch_code: str = None) -> int:
        """Add criterion to global catalog with full scope."""
        # Clean inputs (empty strings -> None)
        degree_code = degree_code if degree_code and degree_code.strip() else None
        program_code = program_code if program_code and program_code.strip() else None
        branch_code = branch_code if branch_code and branch_code.strip() else None
            
        sql = """
        INSERT INTO rubric_criteria_catalog (key, label, description, degree_code, program_code, branch_code, active)
        VALUES (:key, :label, :description, :degree_code, :program_code, :branch_code, 1)
        """
        with self.engine.begin() as conn:
            result = self._exec(conn, sql, {
                'key': key,
                'label': label,
                'description': description,
                'degree_code': degree_code,
                'program_code': program_code,
                'branch_code': branch_code
            })
            return result.lastrowid

    def update_catalog_criterion(self, id: int, label: str, description: str, 
                                 degree_code: str = None, program_code: str = None, branch_code: str = None) -> bool:
        """Update an existing catalog criterion."""
        degree_code = degree_code if degree_code and degree_code.strip() else None
        program_code = program_code if program_code and program_code.strip() else None
        branch_code = branch_code if branch_code and branch_code.strip() else None
            
        sql = """
        UPDATE rubric_criteria_catalog
        SET label = :label, description = :desc, 
            degree_code = :degree, program_code = :program, branch_code = :branch,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        """
        with self.engine.begin() as conn:
            self._exec(conn, sql, {
                'label': label,
                'desc': description,
                'degree': degree_code,
                'program': program_code,
                'branch': branch_code,
                'id': id
            })
        return True

    def delete_catalog_criterion(self, id: int) -> bool:
        """Delete (hard delete) a catalog criterion."""
        sql = "DELETE FROM rubric_criteria_catalog WHERE id = :id"
        with self.engine.begin() as conn:
            self._exec(conn, sql, {'id': id})
        return True

    # ========================================================================
    # CATALOG IMPORT / EXPORT (ENHANCED)
    # ========================================================================

    def generate_catalog_template(self) -> bytes:
        """Generates a CSV template for Global Categories."""
        df = pd.DataFrame([
            {"label": "Content", "description": "Depth of understanding", "degree_code": "BARCH", "program_code": "", "branch_code": ""},
            {"label": "Expression", "description": "Clarity of communication", "degree_code": "", "program_code": "", "branch_code": ""},
            {"label": "Coding Standards", "description": "PEP8 compliance", "degree_code": "BTECH", "program_code": "CSE", "branch_code": "AI"},
        ])
        output = BytesIO()
        df.to_csv(output, index=False)
        return output.getvalue()

    def export_catalog_csv(self) -> bytes:
        """Exports the current catalog to CSV."""
        catalog = self.get_criteria_catalog(active_only=False)
        if not catalog:
            return b""
        
        df = pd.DataFrame(catalog)
        export_cols = ['label', 'description', 'degree_code', 'program_code', 'branch_code', 'active']
        for col in export_cols:
            if col not in df.columns:
                df[col] = None
        
        output = BytesIO()
        df[export_cols].to_csv(output, index=False)
        return output.getvalue()

    def _generate_key(self, label: str) -> str:
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

    def process_import_catalog(self, df: pd.DataFrame, execute: bool = False) -> List[Dict]:
        """
        Handles both Dry Run (execute=False) and Real Import (execute=True).
        Matches based on Label+Degree+Program+Branch to prevent duplicates.
        """
        report = []
        
        def clean_str(val):
            if pd.isna(val) or str(val).strip() == '': return None
            return str(val).strip()

        if 'label' not in df.columns:
            return [{"Row": 0, "Status": "Error", "Label": "-", "Action": "-", "Description": "Missing 'label' column"}]

        with self.engine.begin() as conn:
            seen_in_file = set()

            for idx, row in df.iterrows():
                row_idx = idx + 2
                
                label = clean_str(row.get('label'))
                if not label:
                    report.append({"Row": row_idx, "Label": "-", "Action": "Skip", "Status": "Invalid: Missing Label"})
                    continue

                description = clean_str(row.get('description'))
                # Handle Scopes
                degree = clean_str(row.get('degree_code'))
                program = clean_str(row.get('program_code'))
                branch = clean_str(row.get('branch_code'))
                active = int(row.get('active', 1))

                scope_key = (label, degree, program, branch)
                
                # Check Database
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
                        logger.error(f"Import error row {row_idx}: {e}")

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

    # ========================================================================
    # RUBRIC CONFIG OPERATIONS (UNCHANGED)
    # ========================================================================

    def create_rubric_config(self, config: RubricConfig, audit_entry: AuditEntry) -> int:
        """Create rubric configuration."""
        existing = self._fetch_one("""
        SELECT id FROM rubric_configs
        WHERE offering_id = :offering_id
        """, {'offering_id': config.offering_id})

        if existing:
            raise ValueError("Rubric config already exists for this subject")

        sql = """
        INSERT INTO rubric_configs (
            offering_id, co_linking_enabled, normalization_enabled, visible_to_students,
            status, is_locked, created_by
        ) VALUES (
            :offering_id, :co_linking_enabled, :normalization_enabled, :visible_to_students,
            :status, :is_locked, :created_by
        )
        """
        params = {
            'offering_id': config.offering_id,
            'co_linking_enabled': config.co_linking_enabled,
            'normalization_enabled': config.normalization_enabled,
            'visible_to_students': config.visible_to_students,
            'status': config.status,
            'is_locked': config.is_locked,
            'created_by': audit_entry.actor_id
        }
        
        with self.engine.begin() as conn:
            result = self._exec(conn, sql, params)
            config_id = result.lastrowid

        self._audit_rubric('RUBRIC_CREATED', config_id, config.offering_id, audit_entry)
        return config_id

    def list_rubrics_for_offering(self, offering_id: int) -> List[Dict]:
        """List all rubrics for an offering."""
        return self._fetch_all("""
        SELECT * FROM rubric_configs
        WHERE offering_id = :offering_id
        """, {'offering_id': offering_id})
    
    def find_previous_configs(self, subject_code: str, current_offering_id: int) -> List[Dict]:
        """Find previous year configs."""
        sql = """
        SELECT rc.id as config_id, so.ay_label, so.year, so.term, rc.updated_at
        FROM rubric_configs rc
        JOIN subject_offerings so ON rc.offering_id = so.id
        WHERE so.subject_code = :subject_code
        AND so.id != :current_id
        ORDER BY so.ay_label DESC
        """
        return self._fetch_all(sql, {"subject_code": subject_code, "current_id": current_offering_id})

    def copy_rubric_config(self, source_config_id: int, target_offering_id: int, audit_entry: AuditEntry) -> int:
        """Copy configuration."""
        source = self._fetch_one("SELECT * FROM rubric_configs WHERE id=:id", {"id": source_config_id})
        if not source: raise ValueError("Source not found")
        
        sql = """
        INSERT INTO rubric_configs (
            offering_id, 
            co_linking_enabled, normalization_enabled, visible_to_students,
            status, is_locked, 
            created_by, copied_from_config_id
        ) VALUES (
            :offering_id, 
            :co_linking_enabled, :normalization_enabled, :visible_to_students,
            'draft', 0, 
            :created_by, :source_id
        )
        """
        params = {
            "offering_id": target_offering_id,
            "co_linking_enabled": source['co_linking_enabled'],
            "normalization_enabled": source['normalization_enabled'],
            "visible_to_students": source['visible_to_students'],
            "created_by": audit_entry.actor_id,
            "source_id": source_config_id
        }
        with self.engine.begin() as conn:
            res = self._exec(conn, sql, params)
            new_id = res.lastrowid
            
        self._audit_rubric('RUBRIC_COPIED', new_id, target_offering_id, audit_entry)
        return new_id

    def _audit_rubric(self, action: str, config_id: int, offering_id: int,
                     audit_entry: AuditEntry, note: str = None,
                     changed_fields: str = None):
        with self.engine.begin() as conn:
            self._exec(conn, """
            INSERT INTO rubrics_audit (
                rubric_config_id, offering_id, action, note, changed_fields,
                actor_id, actor_role, operation, reason, source
            ) VALUES (
                :config_id, :offering_id, :action, :note, :changed_fields,
                :actor_id, :actor_role, :operation, :reason, :source
            )
            """, {
                'config_id': config_id, 'offering_id': offering_id,
                'action': action, 'note': note, 'changed_fields': changed_fields,
                'actor_id': audit_entry.actor_id, 'actor_role': audit_entry.actor_role,
                'operation': audit_entry.operation, 'reason': audit_entry.reason, 'source': audit_entry.source
            })
