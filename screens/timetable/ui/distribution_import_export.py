"""
Distribution Import/Export Service - COMPLETE FIXED VERSION
✅ No dependency on is_elective_parent column
✅ Detects electives by checking if topics exist in elective_topics table
✅ Creates audit trail entries for all imports
✅ Tracks detailed import results
"""

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging

log = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of import operation"""
    success: bool
    records_processed: int
    records_created: int
    records_updated: int
    records_skipped: int
    errors: List[str]
    warnings: List[str]
    dry_run: bool
    created_details: List[Dict] = field(default_factory=list)
    updated_details: List[Dict] = field(default_factory=list)


# ================================================================
# AUDIT TRAIL HELPER - Call this after every INSERT/UPDATE
# ================================================================
def _create_audit_entry(conn, dist_id: int, offering_id: int, ay_label: str, 
                       degree_code: str, division_code: Optional[str], 
                       action: str, actor: str):
    """Create audit trail entry in weekly_subject_distribution_audit"""
    conn.execute(
        text("""
            INSERT INTO weekly_subject_distribution_audit (
                distribution_id, offering_id, ay_label, degree_code,
                division_code, change_reason, changed_by, changed_at
            ) VALUES (
                :dist_id, :oid, :ay, :deg, :div, :reason, :actor, CURRENT_TIMESTAMP
            )
        """),
        {
            'dist_id': dist_id,
            'oid': offering_id,
            'ay': ay_label,
            'deg': degree_code,
            'div': division_code,
            'reason': action,
            'actor': actor
        }
    )


class DistributionImportExportService:
    """Service for importing/exporting distribution configurations"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def generate_template(
        self,
        degree_code: str,
        year: int,
        term: int,
        program_code: Optional[str] = None,
        branch_code: Optional[str] = None,
        ay_label: Optional[str] = None,
        include_elective_topics: bool = True
    ) -> pd.DataFrame:
        """
        Generate template with subjects and elective topics expanded.
        
        If ay_label provided and include_elective_topics=True:
        - Checks elective_topics table for each subject
        - If topics exist, expands into individual topic rows
        """
        
        with self.engine.connect() as conn:
            # Get base subjects from catalog (WITHOUT is_elective_parent)
            subjects = pd.read_sql(
                text("""
                    SELECT DISTINCT
                        subject_code,
                        subject_name,
                        subject_type
                    FROM subjects_catalog
                    WHERE degree_code = :degree
                    AND (:prog IS NULL OR program_code = :prog OR program_code IS NULL)
                    AND (:branch IS NULL OR branch_code = :branch OR branch_code IS NULL)
                    AND active = 1
                    ORDER BY subject_type, subject_code
                """),
                conn,
                params={
                    'degree': degree_code,
                    'prog': program_code,
                    'branch': branch_code
                }
            )
        
        if subjects.empty:
            return self._empty_template()
        
        template_data = []
        
        for _, subj in subjects.iterrows():
            # Check if this subject has elective topics (if AY provided)
            if include_elective_topics and ay_label:
                topics = self._fetch_elective_topics(
                    subj['subject_code'], ay_label, year, term,
                    degree_code, program_code, branch_code
                )
                
                if not topics.empty:
                    # Has topics - add each topic as separate row
                    for _, topic in topics.iterrows():
                        template_data.append({
                            'subject_code': topic['topic_code_ay'],
                            'subject_name': f"{topic['topic_name']} (Topic)",
                            'subject_type': subj['subject_type'],
                            'duration_type': 'full_term',
                            'weekly_frequency': 1,
                            'is_all_day_elective_block': 0,
                            'room_code': '',
                            'module_start_date': '',
                            'module_end_date': '',
                            'division_code': '',
                            'notes': f'Elective topic for {subj["subject_code"]}'
                        })
                    continue  # Skip adding parent subject
                elif self._is_likely_elective(subj['subject_type']):
                    # Looks like elective but no topics yet - warn
                    template_data.append({
                        'subject_code': subj['subject_code'],
                        'subject_name': f"{subj['subject_name']} (⚠️ NO TOPICS)",
                        'subject_type': subj['subject_type'],
                        'duration_type': 'full_term',
                        'weekly_frequency': 1,
                        'is_all_day_elective_block': 0,
                        'room_code': '',
                        'module_start_date': '',
                        'module_end_date': '',
                        'division_code': '',
                        'notes': '⚠️ Create elective topics first in Electives module'
                    })
                    continue
            
            # Regular subject (or no AY context)
            template_data.append({
                'subject_code': subj['subject_code'],
                'subject_name': subj['subject_name'],
                'subject_type': subj['subject_type'],
                'duration_type': 'full_term',
                'weekly_frequency': 1,
                'is_all_day_elective_block': 0,
                'room_code': '',
                'module_start_date': '',
                'module_end_date': '',
                'division_code': '',
                'notes': ''
            })
        
        return pd.DataFrame(template_data)
    
    def _is_likely_elective(self, subject_type: str) -> bool:
        """Check if subject type suggests it's an elective"""
        if not subject_type:
            return False
        return subject_type.lower() in [
            'elective', 'open elective', 'program elective', 
            'college project', 'electives'
        ]
    
    def _fetch_elective_topics(self, subject_code: str, ay_label: str, year: int, term: int,
                               degree_code: str, program_code: Optional[str], 
                               branch_code: Optional[str]) -> pd.DataFrame:
        """Fetch elective topics for a subject"""
        with self.engine.connect() as conn:
            try:
                return pd.read_sql(
                    text("""
                        SELECT 
                            topic_code_ay,
                            topic_name,
                            topic_no
                        FROM elective_topics
                        WHERE subject_code = :subj
                        AND ay_label = :ay
                        AND year = :yr
                        AND term = :term
                        AND degree_code = :deg
                        AND (:prog IS NULL OR program_code = :prog OR program_code IS NULL)
                        AND (:branch IS NULL OR branch_code = :branch OR branch_code IS NULL)
                        AND status IN ('draft', 'published')
                        ORDER BY topic_no
                    """),
                    conn,
                    params={
                        'subj': subject_code,
                        'ay': ay_label,
                        'yr': year,
                        'term': term,
                        'deg': degree_code,
                        'prog': program_code,
                        'branch': branch_code
                    }
                )
            except Exception:
                # elective_topics table might not exist
                return pd.DataFrame()
    
    def _empty_template(self) -> pd.DataFrame:
        """Empty template structure"""
        return pd.DataFrame(columns=[
            'subject_code',
            'subject_name',
            'subject_type',
            'duration_type',
            'weekly_frequency',
            'is_all_day_elective_block',
            'room_code',
            'module_start_date',
            'module_end_date',
            'division_code',
            'notes'
        ])
    
    def export_distributions(
        self,
        ay_label: str,
        degree_code: str,
        year: int,
        term: int,
        program_code: Optional[str] = None,
        branch_code: Optional[str] = None,
        division_code: Optional[str] = None,
        include_topics: bool = True
    ) -> pd.DataFrame:
        """
        Export existing distributions with elective topics expanded.
        
        If include_topics=True:
        - Checks if subject has topics in elective_topics table
        - Expands into individual topic rows if found
        """
        
        with self.engine.connect() as conn:
            query = text("""
                SELECT 
                    d.subject_code,
                    d.subject_type,
                    d.duration_type,
                    d.weekly_frequency,
                    d.is_all_day_elective_block,
                    d.room_code,
                    d.module_start_date,
                    d.module_end_date,
                    d.division_code,
                    d.offering_id,
                    d.year,
                    d.term
                FROM weekly_subject_distribution d
                WHERE d.ay_label = :ay
                AND d.degree_code = :degree
                AND d.year = :year
                AND d.term = :term
                AND (:prog IS NULL OR d.program_code = :prog)
                AND (:branch IS NULL OR d.branch_code = :branch)
                AND (:div IS NULL OR d.division_code = :div)
                ORDER BY d.subject_type, d.subject_code
            """)
            
            distributions = pd.read_sql(
                query,
                conn,
                params={
                    'ay': ay_label,
                    'degree': degree_code,
                    'year': year,
                    'term': term,
                    'prog': program_code,
                    'branch': branch_code,
                    'div': division_code
                }
            )
        
        if distributions.empty:
            return self._empty_template()
        
        # Add subject_name from catalog
        distributions = self._add_subject_names(distributions, degree_code)
        
        if include_topics:
            distributions = self._expand_topics_for_export(distributions, ay_label)
        
        export_cols = [
            'subject_code', 'subject_name', 'subject_type',
            'duration_type', 'weekly_frequency',
            'is_all_day_elective_block', 'room_code',
            'module_start_date', 'module_end_date',
            'division_code', 'notes'
        ]
        
        result = distributions[[col for col in export_cols if col in distributions.columns]].copy()
        result = result.fillna('')
        return result
    
    def _add_subject_names(self, df: pd.DataFrame, degree_code: str) -> pd.DataFrame:
        """Add subject_name from subjects_catalog"""
        with self.engine.connect() as conn:
            names = pd.read_sql(
                text("""
                    SELECT subject_code, subject_name
                    FROM subjects_catalog
                    WHERE degree_code = :deg
                """),
                conn,
                params={'deg': degree_code}
            )
        
        df = df.merge(names, on='subject_code', how='left')
        df['subject_name'] = df['subject_name'].fillna(df['subject_code'])
        return df
    
    def _expand_topics_for_export(self, distributions: pd.DataFrame, ay_label: str) -> pd.DataFrame:
        """Expand subjects that have elective topics"""
        expanded_rows = []
        
        with self.engine.connect() as conn:
            for _, dist in distributions.iterrows():
                # Check if this subject has topics
                topics = pd.read_sql(
                    text("""
                        SELECT 
                            topic_code_ay as subject_code,
                            topic_name as subject_name,
                            offering_id
                        FROM elective_topics
                        WHERE subject_code = :subj_code
                        AND ay_label = :ay
                        AND year = :yr
                        AND term = :term
                        AND (:div IS NULL OR division_code = :div)
                        AND status IN ('draft', 'published')
                        ORDER BY topic_no
                    """),
                    conn,
                    params={
                        'subj_code': dist['subject_code'],
                        'ay': ay_label,
                        'yr': dist.get('year'),
                        'term': dist.get('term'),
                        'div': dist.get('division_code')
                    }
                )
                
                if not topics.empty:
                    # Has topics - add each topic as separate row
                    for _, topic in topics.iterrows():
                        topic_dist = dist.copy()
                        topic_dist['subject_code'] = topic['subject_code']
                        topic_dist['subject_name'] = f"{topic['subject_name']} (Topic)"
                        topic_dist['offering_id'] = topic['offering_id']
                        expanded_rows.append(topic_dist)
                else:
                    # No topics - keep original
                    expanded_rows.append(dist)
        
        return pd.DataFrame(expanded_rows) if expanded_rows else distributions
    
    def import_distributions(
        self,
        df: pd.DataFrame,
        ay_label: str,
        dry_run: bool = True,
        overwrite_existing: bool = False,
        skip_errors: bool = False,
        actor: str = "user"
    ) -> ImportResult:
        """
        Import distributions from CSV WITH AUDIT TRAIL.
        
        IMPORTANT: 
        - subject_name and subject_type in CSV are REFERENCE ONLY (ignored)
        - Only subject_code is used to lookup offerings
        """
        
        errors = []
        warnings = []
        created = 0
        updated = 0
        skipped = 0
        created_details = []
        updated_details = []
        
        if 'subject_code' not in df.columns:
            return ImportResult(
                success=False, records_processed=0, records_created=0,
                records_updated=0, records_skipped=0,
                errors=["Missing required column: subject_code"],
                warnings=[], dry_run=dry_run
            )
        
        # Add optional columns
        if 'duration_type' not in df.columns:
            df['duration_type'] = 'full_term'
        if 'weekly_frequency' not in df.columns:
            df['weekly_frequency'] = 1
        if 'is_all_day_elective_block' not in df.columns:
            df['is_all_day_elective_block'] = 0
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                result = self._process_import_row(row, ay_label, dry_run, overwrite_existing, actor)
                
                if result['status'] == 'created':
                    created += 1
                    created_details.append({
                        'row': idx + 2,
                        'subject_code': row['subject_code'],
                        'ay': ay_label,
                        'degree': row.get('degree_code'),
                        'year': result.get('year'),
                        'term': result.get('term'),
                        'division': row.get('division_code') or 'All'
                    })
                elif result['status'] == 'updated':
                    updated += 1
                    updated_details.append({
                        'row': idx + 2,
                        'subject_code': row['subject_code'],
                        'ay': ay_label,
                        'degree': row.get('degree_code'),
                        'year': result.get('year'),
                        'term': result.get('term'),
                        'division': row.get('division_code') or 'All'
                    })
                elif result['status'] == 'skipped':
                    skipped += 1
                    if result.get('reason'):
                        warnings.append(f"Row {idx+2}: {result['reason']}")
                
                if result.get('warning'):
                    warnings.append(f"Row {idx+2}: {result['warning']}")
                    
            except Exception as e:
                error_msg = f"Row {idx+2} ({row.get('subject_code', 'unknown')}): {str(e)}"
                if skip_errors:
                    warnings.append(f"⚠️ SKIPPED - {error_msg}")
                    skipped += 1
                else:
                    errors.append(error_msg)
        
        success = len(errors) == 0 if not skip_errors else (created > 0 or updated > 0)
        
        return ImportResult(
            success=success,
            records_processed=len(df),
            records_created=created,
            records_updated=updated,
            records_skipped=skipped,
            errors=errors,
            warnings=warnings,
            dry_run=dry_run,
            created_details=created_details,
            updated_details=updated_details
        )
    
    def _process_import_row(self, row: pd.Series, ay_label: str, dry_run: bool, overwrite: bool, actor: str) -> Dict:
        """Process single import row.
        
        New behaviour:
        - year/term are NOT read from the CSV.
        - We always infer year/term from subject_offerings for this AY+degree(+program/+branch).
        """
        # Helper function to safely extract string values and handle nan
        def safe_str(value) -> Optional[str]:
            """Convert value to string, handling None, nan, empty strings"""
            if value is None or pd.isna(value):
                return None
            s = str(value).strip()
            if not s or s.upper() in ('NAN', 'NONE', 'NULL'):
                return None
            return s
        
        # ---- Basic CSV fields ----
        subject_code = safe_str(row.get('subject_code'))
        if not subject_code:
            raise ValueError("subject_code is required")

        degree_code = safe_str(row.get('degree_code'))
        program_code = safe_str(row.get('program_code'))
        branch_code = safe_str(row.get('branch_code'))
        division_code = safe_str(row.get('division_code'))

        if not degree_code:
            raise ValueError("degree_code is required")

        # ---- Lookup offering purely by subject (year/term inferred from DB) ----
        offering_info = self._get_offering_info_by_subject(
            subject_code=subject_code,
            degree_code=degree_code,
            program_code=program_code,
            branch_code=branch_code,
            ay_label=ay_label,
        )

        if not offering_info:
            raise ValueError(
                f"No offering found for subject '{subject_code}' in "
                f"AY {ay_label}, degree {degree_code} "
                f"(program={program_code or 'ANY'}, branch={branch_code or 'ANY'})."
            )

        # Take year/term from the offering row (source of truth)
        year = offering_info['year']
        term = offering_info['term']

        # ---- Check existing distribution for this offering + division ----
        existing = self._get_existing_distribution(offering_info['offering_id'], division_code)

        if existing and not overwrite:
            return {
                'status': 'skipped', 
                'reason': "Already exists (use overwrite)",
                'year': year,
                'term': term
            }

        if dry_run:
            return {
                'status': 'updated' if existing else 'created',
                'offering_id': offering_info['offering_id'],
                'year': year,
                'term': term
            }

        # ---- Prepare and write data ----
        data = self._prepare_distribution_data(
            row,
            offering_id=offering_info['offering_id'],
            ay_label=ay_label,
            degree_code=degree_code,
            program_code=program_code,
            branch_code=branch_code,
            year=year,
            term=term,
            subject_type=offering_info['subject_type'],
            actor=actor,
        )

        if existing:
            self._update_distribution(existing['id'], data, actor)
            return {
                'status': 'updated', 
                'id': existing['id'],
                'year': year,
                'term': term
            }
        else:
            new_id = self._create_distribution(data, actor)
            return {
                'status': 'created', 
                'id': new_id,
                'year': year,
                'term': term
            }

    def _get_offering_info_by_subject(
        self,
        subject_code: str,
        degree_code: str,
        program_code: Optional[str],
        branch_code: Optional[str],
        ay_label: str,
    ) -> Optional[Dict]:
        """
        Find a unique offering for this subject in the given AY+degree(+program/+branch),
        inferring year/term from subject_offerings.

        Returns:
            {
                'offering_id': int,
                'year': int,
                'term': int,
                'subject_type': str,
            }
        or None if no offering exists.

        Raises:
            ValueError if multiple offerings match (ambiguous subject).
        """
        with self.engine.connect() as conn:
            # First diagnostic query: check if subject+degree exists at all
            diagnostic = conn.execute(
                text("""
                    SELECT ay_label, program_code, branch_code, year, term
                    FROM subject_offerings
                    WHERE subject_code = :subj AND degree_code = :deg
                    LIMIT 5
                """),
                {'subj': subject_code, 'deg': degree_code}
            ).fetchall()
            
            rows = conn.execute(
                text("""
                    SELECT
                        o.id,
                        o.year,
                        o.term,
                        COALESCE(sc.subject_type, o.subject_type, 'Core') AS subject_type
                    FROM subject_offerings o
                    LEFT JOIN subjects_catalog sc
                        ON sc.subject_code = o.subject_code
                       AND sc.degree_code = o.degree_code
                    WHERE o.subject_code = :subj
                      AND o.degree_code = :deg
                      AND o.ay_label = :ay
                      AND (:prog IS NULL OR o.program_code = :prog OR o.program_code IS NULL)
                      AND (:branch IS NULL OR o.branch_code = :branch OR o.branch_code IS NULL)
                """),
                {
                    'subj': subject_code,
                    'deg': degree_code,
                    'ay': ay_label,
                    'prog': program_code,
                    'branch': branch_code,
                },
            ).fetchall()

        if not rows:
            if not diagnostic:
                raise ValueError(
                    f"No offering found for '{subject_code}' (no offerings exist in database for this subject+degree). "
                    f"Check: (1) subject_offerings table, (2) subject_code spelling, (3) degree_code spelling"
                )
            else:
                # Show what's available
                available = []
                for d in diagnostic[:3]:
                    available.append(f"ay='{d[0]}', prog='{d[1] or 'NULL'}', branch='{d[2] or 'NULL'}', Y{d[3]}T{d[4]}")
                raise ValueError(
                    f"No offering found for '{subject_code}' matching ay_label='{ay_label}', "
                    f"program='{program_code or 'NULL'}', branch='{branch_code or 'NULL'}'. "
                    f"Available: {', '.join(available)}"
                )

        if len(rows) > 1:
            raise ValueError(
                f"Ambiguous subject '{subject_code}': found {len(rows)} offerings. "
                f"Please specify program/branch in CSV."
            )

        row = rows[0]
        return {
            'offering_id': row[0],
            'year': row[1],
            'term': row[2],
            'subject_type': row[3],
        }
    
    def _get_existing_distribution(self, offering_id: int, division_code: Optional[str]) -> Optional[Dict]:
        """Check if distribution exists - EXACT division match (NULL = NULL, value = value)"""
        with self.engine.connect() as conn:
            if division_code is None:
                # Match only NULL divisions
                result = conn.execute(
                    text("""
                        SELECT id FROM weekly_subject_distribution
                        WHERE offering_id = :oid
                        AND division_code IS NULL
                        LIMIT 1
                    """),
                    {'oid': offering_id}
                ).fetchone()
            else:
                # Match specific division
                result = conn.execute(
                    text("""
                        SELECT id FROM weekly_subject_distribution
                        WHERE offering_id = :oid
                        AND division_code = :div
                        LIMIT 1
                    """),
                    {'oid': offering_id, 'div': division_code}
                ).fetchone()
            
            return {'id': result[0]} if result else None
    
    def _prepare_distribution_data(self, row: pd.Series, offering_id: int, ay_label: str,
                                   degree_code: str, program_code: Optional[str],
                                   branch_code: Optional[str], year: int, term: int,
                                   subject_type: str, actor: str) -> Dict:
        """Prepare data for database"""
        
        def safe_str(value) -> Optional[str]:
            """Convert value to string, handling None, nan, empty strings"""
            if value is None or pd.isna(value):
                return None
            s = str(value).strip()
            if not s or s.upper() in ('NAN', 'NONE', 'NULL'):
                return None
            return s
        
        def parse_date(date_str):
            if not date_str or pd.isna(date_str):
                return None
            s = str(date_str).strip().upper()
            if not s or s in ('NAN', 'NONE', 'NULL'):
                return None
            try:
                return pd.to_datetime(date_str).date().isoformat()
            except:
                return None
        
        return {
            'offering_id': offering_id,
            'ay_label': ay_label,
            'degree_code': degree_code,
            'program_code': program_code,
            'branch_code': branch_code,
            'year': year,
            'term': term,
            'division_code': safe_str(row.get('division_code')),
            'subject_code': safe_str(row.get('subject_code')),
            'subject_type': subject_type,
            'duration_type': safe_str(row.get('duration_type')) or 'full_term',
            'weekly_frequency': int(row.get('weekly_frequency', 1)),
            'is_all_day': 1 if row.get('is_all_day_elective_block', 0) else 0,
            'room_code': safe_str(row.get('room_code')),
            'module_start_date': parse_date(row.get('module_start_date')),
            'module_end_date': parse_date(row.get('module_end_date')),
            'actor': actor
        }
    
    def _create_distribution(self, data: Dict, actor: str) -> int:
        """Create new distribution WITH AUDIT TRAIL"""
        with self.engine.begin() as conn:
            # Insert distribution
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution (
                        offering_id, ay_label, degree_code, program_code, branch_code,
                        year, term, division_code, subject_code, subject_type,
                        duration_type, weekly_frequency,
                        is_all_day_elective_block, room_code,
                        module_start_date, module_end_date,
                        mon_periods, tue_periods, wed_periods,
                        thu_periods, fri_periods, sat_periods
                    ) VALUES (
                        :offering_id, :ay_label, :degree_code, :program_code, :branch_code,
                        :year, :term, :division_code, :subject_code, :subject_type,
                        :duration_type, :weekly_frequency,
                        :is_all_day, :room_code,
                        :module_start_date, :module_end_date,
                        0, 0, 0, 0, 0, 0
                    )
                """),
                data
            )
            
            new_id = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]
            
            # ✅ CREATE AUDIT TRAIL ENTRY
            _create_audit_entry(
                conn, new_id, data['offering_id'], data['ay_label'],
                data['degree_code'], data['division_code'],
                f"IMPORTED: Created via CSV import", actor
            )
            
            return new_id
    
    def _update_distribution(self, dist_id: int, data: Dict, actor: str):
        """Update existing distribution WITH AUDIT TRAIL"""
        with self.engine.begin() as conn:
            # Update distribution
            conn.execute(
                text("""
                    UPDATE weekly_subject_distribution SET
                        duration_type = :duration_type,
                        weekly_frequency = :weekly_frequency,
                        is_all_day_elective_block = :is_all_day,
                        room_code = :room_code,
                        module_start_date = :module_start_date,
                        module_end_date = :module_end_date,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {**data, 'id': dist_id}
            )
            
            # ✅ CREATE AUDIT TRAIL ENTRY
            _create_audit_entry(
                conn, dist_id, data['offering_id'], data['ay_label'],
                data['degree_code'], data['division_code'],
                f"IMPORTED: Updated via CSV import", actor
            )
