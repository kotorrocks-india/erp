# screens/subject_cos_rubrics/course_outcomes_tab.py
"""
Course Outcomes Tab

Manages Course Outcomes (COs) for published subject offerings.
Features:
- View existing COs for a subject offering
- Add/Edit/Delete COs
- Map COs to POs, PSOs, and PEOs
- Manage CO weights and Bloom levels
- Export/Import COs
- Toggle between Equal and Weighted distribution
- Copy COs from previous Academic Year
"""

import streamlit as st
import pandas as pd
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import List, Dict, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)

# Helper function
def is_valid(value):
    """Helper to check if a value is not None, not NaN, and not empty string."""
    if value is None:
        return False
    if pd.isna(value):
        return False
    if isinstance(value, str):
        value_stripped = value.strip().upper()
        if value_stripped == '' or value_stripped == 'NONE' or value_stripped == 'NAN':
            return False
    return True

# ===========================================================================
# DATA FETCHING FUNCTIONS
# ===========================================================================

def fetch_previous_offering(engine: Engine, current_offering: Dict) -> Optional[Dict]:
    """
    Finds the most recent published offering of the same subject 
    from a previous academic year.
    """
    query = """
        SELECT id, ay_label, year, term 
        FROM subject_offerings
        WHERE subject_code = :subject_code
        AND degree_code = :degree_code
        AND id != :current_id
        AND status = 'published'
    """
    params = {
        "subject_code": current_offering['subject_code'],
        "degree_code": current_offering['degree_code'],
        "current_id": current_offering['id']
    }

    # Add optional strict matching for program/branch to ensure context is same
    if is_valid(current_offering.get('program_code')):
        query += " AND program_code = :program_code"
        params["program_code"] = current_offering['program_code']
    
    if is_valid(current_offering.get('branch_code')):
        query += " AND branch_code = :branch_code"
        params["branch_code"] = current_offering['branch_code']

    # Order by ID desc to get the latest one created
    query += " ORDER BY id DESC LIMIT 1"

    with engine.begin() as conn:
        row = conn.execute(sa_text(query), params).fetchone()
        if row:
            return dict(row._mapping)
    return None

def fetch_published_offerings_for_cos(engine: Engine, degree_code: str, ay_label: str) -> List[Dict]:
    """Fetch published offerings for CO management."""
    with engine.begin() as conn:
        result = conn.execute(sa_text("""
            SELECT 
                so.id,
                so.subject_code,
                sc.subject_name,
                so.year,
                so.term,
                so.program_code,
                so.branch_code,
                so.division_code,
                so.co_weightage_type
            FROM subject_offerings so
            LEFT JOIN subjects_catalog sc ON 
                so.subject_code = sc.subject_code 
                AND so.degree_code = sc.degree_code
            WHERE so.status = 'published'
            AND so.degree_code = :degree_code
            AND so.ay_label = :ay_label
            ORDER BY so.year, so.term, so.subject_code
        """), {"degree_code": degree_code, "ay_label": ay_label})
        return [dict(row._mapping) for row in result]


def fetch_cos_for_offering(engine: Engine, offering_id: int) -> List[Dict]:
    """Fetch all COs for a specific offering."""
    with engine.begin() as conn:
        result = conn.execute(sa_text("""
            SELECT 
                id, co_code, title, description, bloom_level,
                sequence, weight_in_direct, status, knowledge_type,
                created_at, updated_at
            FROM subject_cos
            WHERE offering_id = :offering_id
            ORDER BY sequence, co_code
        """), {"offering_id": offering_id})
        
        cos = [dict(row._mapping) for row in result]
        
        # Fetch correlations for each CO
        for co in cos:
            # PO correlations
            po_result = conn.execute(sa_text("""
                SELECT po_code, correlation_value
                FROM co_po_correlations
                WHERE co_id = :co_id
            """), {"co_id": co['id']})
            co['po_correlations'] = {row._mapping['po_code']: row._mapping['correlation_value'] 
                                    for row in po_result}
            
            # PSO correlations
            pso_result = conn.execute(sa_text("""
                SELECT pso_code, correlation_value
                FROM co_pso_correlations
                WHERE co_id = :co_id
            """), {"co_id": co['id']})
            co['pso_correlations'] = {row._mapping['pso_code']: row._mapping['correlation_value'] 
                                     for row in pso_result}
            
            # PEO correlations
            peo_result = conn.execute(sa_text("""
                SELECT peo_code, correlation_value
                FROM co_peo_correlations
                WHERE co_id = :co_id
            """), {"co_id": co['id']})
            co['peo_correlations'] = {row._mapping['peo_code']: row._mapping['correlation_value'] 
                                     for row in peo_result}
        
        return cos


def fetch_pos_for_degree(engine: Engine, degree_code: str, program_code: Optional[str] = None) -> List[Dict]:
    """Fetch POs for a degree/program."""
    with engine.begin() as conn:
        query = """
            SELECT oi.code, oi.description
            FROM outcomes_items oi
            JOIN outcomes_sets os ON oi.set_id = os.id
            WHERE os.degree_code = :degree_code
            AND os.set_type = 'pos'
            AND os.status = 'published'
            AND os.is_current = 1
        """
        params = {"degree_code": degree_code}
        
        if program_code:
            query += " AND (os.program_code = :program_code OR os.program_code IS NULL)"
            params["program_code"] = program_code
        else:
            query += " AND os.program_code IS NULL"
        
        query += " ORDER BY oi.sort_order, oi.code"
        
        result = conn.execute(sa_text(query), params)
        return [dict(row._mapping) for row in result]


def fetch_psos_for_program(engine: Engine, degree_code: str, program_code: Optional[str], 
                          branch_code: Optional[str] = None) -> List[Dict]:
    """Fetch PSOs for a program/branch."""
    
    with engine.begin() as conn:
        query = """
            SELECT oi.code, oi.description
            FROM outcomes_items oi
            JOIN outcomes_sets os ON oi.set_id = os.id
            WHERE os.degree_code = :degree_code
            AND os.set_type = 'psos'
            AND os.status = 'published'
            AND os.is_current = 1
        """
        params = {"degree_code": degree_code}
        
        if program_code:
            query += " AND os.program_code = :program_code"
            params["program_code"] = program_code
        else:
             query += " AND os.program_code IS NULL"

        if branch_code:
            query += " AND (os.branch_code = :branch_code OR os.branch_code IS NULL)"
            params["branch_code"] = branch_code
        else:
            query += " AND os.branch_code IS NULL"
        
        query += " ORDER BY oi.sort_order, oi.code"
        
        result = conn.execute(sa_text(query), params)
        return [dict(row._mapping) for row in result]


def fetch_peos_for_degree(engine: Engine, degree_code: str, program_code: Optional[str] = None) -> List[Dict]:
    """Fetch PEOs for a degree/program."""
    with engine.begin() as conn:
        query = """
            SELECT oi.code, oi.description
            FROM outcomes_items oi
            JOIN outcomes_sets os ON oi.set_id = os.id
            WHERE os.degree_code = :degree_code
            AND os.set_type = 'peos'
            AND os.status = 'published'
            AND os.is_current = 1
        """
        params = {"degree_code": degree_code}
        
        if program_code:
            query += " AND (os.program_code = :program_code OR os.program_code IS NULL)"
            params["program_code"] = program_code
        else:
            query += " AND os.program_code IS NULL"

        query += " AND os.branch_code IS NULL" # PEOs are not usually at branch level
        
        query += " ORDER BY oi.sort_order, oi.code"
        
        result = conn.execute(sa_text(query), params)
        return [dict(row._mapping) for row in result]


# ===========================================================================
# DATA MODIFICATION FUNCTIONS
# ===========================================================================

def update_offering_weightage_type(engine: Engine, offering_id: int, weightage_type: str):
    """Updates the CO weightage type and recalculates if 'equal'."""
    try:
        with engine.begin() as conn:
            # 1. Update the setting on the offering
            conn.execute(sa_text("""
                UPDATE subject_offerings 
                SET co_weightage_type = :w_type, updated_at = CURRENT_TIMESTAMP 
                WHERE id = :id
            """), {"w_type": weightage_type, "id": offering_id})
            
            # 2. If 'equal', immediately recalculate weights for all COs
            if weightage_type == 'equal':
                count_res = conn.execute(sa_text("SELECT COUNT(*) FROM subject_cos WHERE offering_id = :oid"), {"oid": offering_id}).fetchone()
                count = count_res[0]
                
                if count > 0:
                    equal_weight = 1.0 / count
                    conn.execute(sa_text("""
                        UPDATE subject_cos 
                        SET weight_in_direct = :ew 
                        WHERE offering_id = :oid
                    """), {"ew": equal_weight, "oid": offering_id})
        return True
    except Exception as e:
        logger.error(f"Error updating weightage type: {e}")
        return False


def save_co(engine: Engine, offering_id: int, co_data: Dict, co_id: Optional[int] = None) -> bool:
    """Save a CO (create or update)."""
    try:
        with engine.begin() as conn:
            if co_id:
                # Update existing CO
                conn.execute(sa_text("""
                    UPDATE subject_cos
                    SET co_code = :co_code,
                        title = :title,
                        description = :description,
                        bloom_level = :bloom_level,
                        sequence = :sequence,
                        weight_in_direct = :weight_in_direct,
                        status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :co_id
                """), {
                    "co_id": co_id,
                    "co_code": co_data['co_code'],
                    "title": co_data['title'],
                    "description": co_data['description'],
                    "bloom_level": co_data['bloom_level'],
                    "sequence": co_data['sequence'],
                    "weight_in_direct": co_data['weight_in_direct'],
                    "status": co_data['status']
                })
            else:
                # Insert new CO
                result = conn.execute(sa_text("""
                    INSERT INTO subject_cos (
                        offering_id, co_code, title, description, bloom_level,
                        sequence, weight_in_direct, status,
                        created_at, updated_at
                    ) VALUES (
                        :offering_id, :co_code, :title, :description, :bloom_level,
                        :sequence, :weight_in_direct, :status,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """), {
                    "offering_id": offering_id,
                    "co_code": co_data['co_code'],
                    "title": co_data['title'],
                    "description": co_data['description'],
                    "bloom_level": co_data['bloom_level'],
                    "sequence": co_data['sequence'],
                    "weight_in_direct": co_data['weight_in_direct'],
                    "status": co_data['status']
                })
                co_id = result.lastrowid
            
            # Save correlations
            if co_id:
                # Delete existing correlations
                conn.execute(sa_text("DELETE FROM co_po_correlations WHERE co_id = :co_id"), {"co_id": co_id})
                conn.execute(sa_text("DELETE FROM co_pso_correlations WHERE co_id = :co_id"), {"co_id": co_id})
                conn.execute(sa_text("DELETE FROM co_peo_correlations WHERE co_id = :co_id"), {"co_id": co_id})
                
                # Insert PO correlations
                for po_code, value in co_data.get('po_correlations', {}).items():
                    if value and value > 0:
                        conn.execute(sa_text("""
                            INSERT INTO co_po_correlations (co_id, po_code, correlation_value)
                            VALUES (:co_id, :po_code, :value)
                        """), {"co_id": co_id, "po_code": po_code, "value": value})
                
                # Insert PSO correlations
                for pso_code, value in co_data.get('pso_correlations', {}).items():
                    if value and value > 0:
                        conn.execute(sa_text("""
                            INSERT INTO co_pso_correlations (co_id, pso_code, correlation_value)
                            VALUES (:co_id, :pso_code, :value)
                        """), {"co_id": co_id, "pso_code": pso_code, "value": value})
                
                # Insert PEO correlations
                for peo_code, value in co_data.get('peo_correlations', {}).items():
                    if value and value > 0:
                        conn.execute(sa_text("""
                            INSERT INTO co_peo_correlations (co_id, peo_code, correlation_value)
                            VALUES (:co_id, :peo_code, :value)
                        """), {"co_id": co_id, "peo_code": peo_code, "value": value})
        
        return True
    except Exception as e:
        logger.error(f"Error saving CO: {e}", exc_info=True)
        return False


def delete_co(engine: Engine, co_id: int) -> bool:
    """Delete a CO."""
    try:
        with engine.begin() as conn:
            # Delete correlations first
            conn.execute(sa_text("DELETE FROM co_po_correlations WHERE co_id = :co_id"), {"co_id": co_id})
            conn.execute(sa_text("DELETE FROM co_pso_correlations WHERE co_id = :co_id"), {"co_id": co_id})
            conn.execute(sa_text("DELETE FROM co_peo_correlations WHERE co_id = :co_id"), {"co_id": co_id})
            
            # Delete CO
            conn.execute(sa_text("DELETE FROM subject_cos WHERE id = :co_id"), {"co_id": co_id})
        
        return True
    except Exception as e:
        logger.error(f"Error deleting CO: {e}", exc_info=True)
        return False


def copy_cos_from_previous(engine: Engine, target_offering_id: int, source_offering_id: int) -> Tuple[int, int]:
    """
    Copies COs from source offering to target offering.
    Returns (created_count, updated_count).
    """
    source_cos = fetch_cos_for_offering(engine, source_offering_id)
    target_cos = fetch_cos_for_offering(engine, target_offering_id)
    
    existing_map = {co['co_code']: co['id'] for co in target_cos}
    
    created = 0
    updated = 0
    
    for co in source_cos:
        # Prepare data packet (stripping IDs)
        co_data = {
            'co_code': co['co_code'],
            'title': co['title'],
            'description': co['description'],
            'bloom_level': co['bloom_level'],
            'sequence': co['sequence'],
            'weight_in_direct': co['weight_in_direct'],
            'status': 'draft', # Reset status to draft on copy
            'po_correlations': co.get('po_correlations', {}),
            'pso_correlations': co.get('pso_correlations', {}),
            'peo_correlations': co.get('peo_correlations', {})
        }
        
        target_id = existing_map.get(co['co_code'])
        
        if save_co(engine, target_offering_id, co_data, target_id):
            if target_id:
                updated += 1
            else:
                created += 1
                
    return created, updated

# ===========================================================================
# UI RENDERING FUNCTIONS
# ===========================================================================

def render_co_form(engine: Engine, offering_id: int, offering_info: Dict, 
                  pos: List[Dict], psos: List[Dict], peos: List[Dict],
                  co_data: Optional[Dict] = None):
    """Render form to add/edit a CO."""
    
    is_equal_weight = offering_info.get('co_weightage_type', 'equal') == 'equal'
    form_title = "Edit Course Outcome" if co_data else "Add Course Outcome"
    
    st.markdown(f"### ✏️ {form_title}")
    
    with st.form(key=f"co_form_{co_data['id'] if co_data else 'new'}"):
        col1, col2 = st.columns(2)
        
        with col1:
            co_code = st.text_input(
                "CO Code*",
                value=co_data['co_code'] if co_data else "",
                placeholder="e.g., CO1"
            )
            
            bloom_level = st.selectbox(
                "Bloom Level*",
                options=["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"],
                index=["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"].index(
                    co_data['bloom_level']) if co_data and co_data['bloom_level'] else 0
            )
        
        with col2:
            sequence = st.number_input(
                "Sequence*",
                min_value=1,
                max_value=100,
                value=int(co_data['sequence']) if co_data and co_data.get('sequence') else 1
            )
            
            if is_equal_weight:
                st.text_input(
                    "Weight in Direct Attainment", 
                    value="Auto (Equal)", 
                    disabled=True,
                    help="Weights are automatically managed because 'Equal Weights' mode is on."
                )
                weight_in_direct = 0.0 # Will be ignored/recalculated
            else:
                weight_in_direct = st.number_input(
                    "Weight in Direct Attainment*",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.01,
                    value=float(co_data['weight_in_direct']) if co_data and co_data.get('weight_in_direct') else 0.0,
                    help="Decimal between 0 and 1. All CO weights should sum to 1.0"
                )
        
        title = st.text_input(
            "CO Title*",
            value=co_data['title'] if co_data else "",
            placeholder="e.g., Analyze the complexity of data structures"
        )

        co_description = st.text_area(
            "CO Description*",
            value=co_data['description'] if co_data else "",
            height=100,
            placeholder="Describe what students should be able to do after completing this course"
        )
        
        status = st.selectbox(
            "Status",
            options=["draft", "published"],
            index=["draft", "published"].index(co_data['status']) if co_data and co_data.get('status') else 0
        )
        
        # Correlations section
        st.markdown("#### 🔗 Correlations")
        st.info("Correlation values: 1 = Low, 2 = Medium, 3 = High, 0 = None")
        
        # PO Correlations
        if pos:
            st.markdown("**Program Outcomes (POs)**")
            po_cols = st.columns(min(len(pos), 5))
            po_correlations = {}
            for idx, po in enumerate(pos):
                with po_cols[idx % len(po_cols)]:
                    current_value = co_data['po_correlations'].get(po['code'], 0) if co_data else 0
                    po_correlations[po['code']] = st.selectbox(
                        po['code'],
                        options=[0, 1, 2, 3],
                        index=[0, 1, 2, 3].index(current_value),
                        key=f"po_{po['code']}_{co_data['id'] if co_data else 'new'}",
                        help=po['description'][:100]
                    )
        else:
            st.warning("No POs found for this degree/program")
            po_correlations = {}
        
        # PSO Correlations
        if psos:
            st.markdown("**Program Specific Outcomes (PSOs)**")
            pso_cols = st.columns(min(len(psos), 5))
            pso_correlations = {}
            for idx, pso in enumerate(psos):
                with pso_cols[idx % len(pso_cols)]:
                    current_value = co_data['pso_correlations'].get(pso['code'], 0) if co_data else 0
                    pso_correlations[pso['code']] = st.selectbox(
                        pso['code'],
                        options=[0, 1, 2, 3],
                        index=[0, 1, 2, 3].index(current_value),
                        key=f"pso_{pso['code']}_{co_data['id'] if co_data else 'new'}",
                        help=pso['description'][:100]
                    )
        else:
            pso_correlations = {} 
        
        # PEO Correlations
        if peos:
            st.markdown("**Program Educational Objectives (PEOs)**")
            peo_cols = st.columns(min(len(peos), 5))
            peo_correlations = {}
            for idx, peo in enumerate(peos):
                with peo_cols[idx % len(peo_cols)]:
                    current_value = co_data['peo_correlations'].get(peo['code'], 0) if co_data else 0
                    peo_correlations[peo['code']] = st.selectbox(
                        peo['code'],
                        options=[0, 1, 2, 3],
                        index=[0, 1, 2, 3].index(current_value),
                        key=f"peo_{peo['code']}_{co_data['id'] if co_data else 'new'}",
                        help=peo['description'][:100]
                    )
        else:
            peo_correlations = {} 
        
        # Submit button
        submitted = st.form_submit_button("💾 Save CO", use_container_width=True)
        
        if submitted:
            if not co_code or not title or not co_description:
                st.error("CO Code, Title, and Description are required")
                return
            
            new_co_data = {
                'co_code': co_code,
                'title': title,
                'description': co_description,
                'bloom_level': bloom_level,
                'sequence': sequence,
                'weight_in_direct': weight_in_direct,
                'status': status,
                'po_correlations': po_correlations,
                'pso_correlations': pso_correlations,
                'peo_correlations': peo_correlations
            }
            
            co_id = co_data['id'] if co_data else None
            success = save_co(engine, offering_id, new_co_data, co_id)
            
            if success:
                if is_equal_weight:
                    update_offering_weightage_type(engine, offering_id, 'equal')
                
                st.success("✅ CO saved successfully!")
                st.session_state.editing_co = None
                st.session_state.show_co_form = False
                st.rerun()
            else:
                st.error("❌ Failed to save CO")
    
    # Actions Outside Form
    c_cancel, c_delete = st.columns([1, 1])
    if c_cancel.button("❌ Cancel"):
        st.session_state.editing_co = None
        st.session_state.show_co_form = False
        st.rerun()
        
    if co_data:
        if c_delete.button("🗑️ Delete CO", type="primary", key=f"del_{co_data['id']}"):
            if delete_co(engine, co_data['id']):
                if is_equal_weight:
                    update_offering_weightage_type(engine, offering_id, 'equal')
                    
                st.success("Deleted")
                st.session_state.editing_co = None
                st.rerun()


def render_co_list(engine: Engine, offering_id: int, cos: List[Dict], weightage_type: str):
    """Render list of COs with actions."""
    
    if not cos:
        st.info("No Course Outcomes defined for this offering yet.")
        # We don't return here so we can show the "Copy" button below the empty list
    
    total_weight = sum(float(co.get('weight_in_direct', 0)) for co in cos)
    is_equal = (weightage_type == 'equal')
    
    # Header with Weight Info
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### 📚 Course Outcomes ({len(cos)} total)")
    with col2:
        if is_equal:
            st.caption(f"⚖️ **Equal Weights** (Each ≈ {100/len(cos) if len(cos)>0 else 0:.1f}%)")
        else:
            color = "green" if abs(total_weight - 1.0) < 0.01 else "red"
            st.markdown(f":{color}[**Total Weight: {total_weight:.2f}**] (Target: 1.0)")
    
    # Display COs
    for co in cos:
        with st.expander(f"**{co['co_code']}**: {co.get('title', 'No Title')}", expanded=False):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                st.markdown(f"**Description:** {co.get('description', 'No Description')}")
                st.markdown(f"**Bloom Level:** {co['bloom_level']}")
                st.markdown(f"**Sequence:** {co.get('sequence', 'N/A')}")
            
            with col2:
                w_disp = "Equal (Auto)" if is_equal else co.get('weight_in_direct', 'N/A')
                st.markdown(f"**Weight:** {w_disp}")
                st.markdown(f"**Status:** {co.get('status', 'N/A')}")
            
            with col3:
                if st.button("✏️ Edit", key=f"edit_co_{co['id']}", use_container_width=True):
                    st.session_state.editing_co = co
                    st.session_state.show_co_form = False 
                    st.rerun()
                
                if st.button("🗑️ Delete", key=f"delete_co_list_{co['id']}", use_container_width=True):
                    if delete_co(engine, co['id']):
                        if is_equal: update_offering_weightage_type(engine, offering_id, 'equal')
                        st.success("✅ CO deleted")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete CO")
            
            # Show correlations
            if co.get('po_correlations'):
                po_text = ", ".join([f"{k}: {v}" for k, v in co['po_correlations'].items() if v > 0])
                st.markdown(f"**POs:** {po_text}")
            
            if co.get('pso_correlations'):
                pso_text = ", ".join([f"{k}: {v}" for k, v in co['pso_correlations'].items() if v > 0])
                st.markdown(f"**PSOs:** {pso_text}")
            
            if co.get('peo_correlations'):
                peo_text = ", ".join([f"{k}: {v}" for k, v in co['peo_correlations'].items() if v > 0])
                st.markdown(f"**PEOs:** {peo_text}")


def render_course_outcomes_tab(engine: Engine, offering_id: Optional[int], offering_info: Optional[Dict]):
    """Main render function for Course Outcomes tab."""
    
    st.markdown("""
    Manage Course Outcomes (COs) for the selected subject offering.
    """)
    
    if not offering_id or not offering_info:
        st.info("Please select a subject offering from the filters at the top of the page to manage COs.")
        return

    # Toggle Switch
    current_mode = offering_info.get('co_weightage_type', 'equal')
    mode_options = ['equal', 'weighted']
    
    c1, c2 = st.columns([1, 3])
    with c1:
        new_mode = st.radio(
            "Weight Distribution Mode",
            options=mode_options,
            index=mode_options.index(current_mode) if current_mode in mode_options else 0,
            format_func=lambda x: "⚖️ Equal Weights" if x == 'equal' else "🎚️ Custom Weighted",
            horizontal=True,
            key=f"co_weight_toggle_{offering_id}"
        )
    
    if new_mode != current_mode:
        update_offering_weightage_type(engine, offering_id, new_mode)
        offering_info['co_weightage_type'] = new_mode 
        st.rerun()

    # Fetch COs for this offering
    cos = fetch_cos_for_offering(engine, offering_id)
    
    # Render List
    render_co_list(engine, offering_id, cos, new_mode)
    
    # --------------------------------------------------------------------------
    # NEW FEATURE: Copy from Previous AY
    # --------------------------------------------------------------------------
    st.markdown("---")
    previous_offering = fetch_previous_offering(engine, offering_info)
    
    if previous_offering:
        col_copy, col_info = st.columns([1, 3])
        with col_copy:
            label = f"📂 Copy COs from {previous_offering['ay_label']}"
            help_text = "Copies all Course Outcomes from the previous academic year. Existing COs with the same code will be updated."
            
            if st.button(label, help=help_text, use_container_width=True):
                with st.spinner(f"Copying COs from {previous_offering['ay_label']}..."):
                    created, updated = copy_cos_from_previous(engine, offering_id, previous_offering['id'])
                    
                    if created > 0 or updated > 0:
                        if new_mode == 'equal':
                             update_offering_weightage_type(engine, offering_id, 'equal')
                        
                        st.success(f"✅ Copied! Created: {created}, Updated: {updated}")
                        st.rerun()
                    else:
                        st.warning("No COs found in the previous offering to copy.")
        
        with col_info:
            st.caption(f"💡 Found previous offering from **{previous_offering['ay_label']}** (Year {previous_offering['year']}, Term {previous_offering['term']}).")
    else:
        # VISIBILITY FIX: Now showing this message instead of hiding the section
        st.info(f"ℹ️ No published previous offering found for {offering_info['subject_code']} to copy from.")

    st.markdown("---")
    
    # Add/Edit CO form
    # Fetch POs, PSOs, PEOs for correlations only when needed
    pos = fetch_pos_for_degree(engine, offering_info.get('degree_code'), offering_info.get('program_code'))
    psos = fetch_psos_for_program(engine, offering_info.get('degree_code'), offering_info.get('program_code'), 
                                   offering_info.get('branch_code'))
    peos = fetch_peos_for_degree(engine, offering_info.get('degree_code'), offering_info.get('program_code'))
    
    editing_co = st.session_state.get('editing_co')
    
    if editing_co:
        render_co_form(engine, offering_id, offering_info, pos, psos, peos, editing_co)
    elif st.session_state.get('show_co_form'):
        render_co_form(engine, offering_id, offering_info, pos, psos, peos)
    else:
        if st.button("➕ Add New CO", type="primary", use_container_width=True):
            st.session_state.show_co_form = True
            st.session_state.editing_co = None 
            st.rerun()
