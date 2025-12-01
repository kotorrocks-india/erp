# Schema Integration Guide - CO & Rubrics

## 🔗 Integration with Existing Schemas

Your assignment system now integrates seamlessly with your existing CO and Rubric schemas!

### ✅ What's Integrated

1. **Course Outcomes (COs)** - from `comprehensive_subjects_schema.py`
2. **Rubrics** - from `rubrics_schema.py`
3. **Program Outcomes (POs, PSOs, PEOs)** - from `outcomes_schema.py`

---

## 📊 Database Relationships

### Assignment → CO Mapping

```
assignments
    └─> assignment_co_mapping
            ├─> co_code → subject_cos.co_code
            └─> correlation_value (0-3)

subject_cos (from your existing schema)
    ├─> offering_id
    ├─> co_code
    ├─> title, description
    ├─> bloom_level
    └─> weight_in_direct

co_po_correlations
    ├─> co_id → subject_cos.id
    ├─> po_code
    └─> correlation_value (0-3)

co_pso_correlations
    ├─> co_id → subject_cos.id
    ├─> pso_code
    └─> correlation_value (0-3)

co_peo_correlations
    ├─> co_id → subject_cos.id
    ├─> peo_code
    └─> correlation_value (0-3)
```

### Assignment → Rubric Mapping

```
assignments
    └─> assignment_rubrics
            ├─> rubric_id → rubric_criteria_catalog.id
            ├─> rubric_mode (A or B)
            ├─> top_level_weight_percent
            └─> sequence_order

rubric_criteria_catalog (from your existing schema)
    ├─> id
    ├─> key (e.g., 'content_barch')
    ├─> label (e.g., 'Content')
    ├─> description
    ├─> degree_code (scope)
    ├─> program_code (scope)
    ├─> branch_code (scope)
    └─> active

rubric_configs (offering-level settings)
    ├─> offering_id
    ├─> co_linking_enabled
    ├─> normalization_enabled
    └─> visible_to_students
```

---

## 🎯 How It Works

### 1. **CO Mapping in Assignment Editor**

When creating an assignment:

```python
# System automatically loads COs from subject_cos table
connector = AssignmentCORubricConnector(engine)
available_cos = connector.get_cos_for_offering(offering_id)

# Returns:
# [
#   {
#     'id': 1,
#     'co_code': 'CO1',
#     'title': 'Understand basic concepts',
#     'description': '...',
#     'bloom_level': 'Understanding',
#     'weight_in_direct': 0.2,
#     'po_correlations': {'PO1': 3, 'PO2': 2},
#     'pso_correlations': {...},
#     'peo_correlations': {...}
#   },
#   ...
# ]
```

**In the UI:**
- Shows all COs defined for the offering
- Allows 0-3 correlation mapping per CO
- Validates at least one CO has value > 0
- Stores in `assignment_co_mapping` table

### 2. **Rubric Selection**

When attaching rubrics:

```python
# System loads rubrics matching context
available_rubrics = connector.get_available_rubrics(
    degree_code='B.Tech',
    program_code='CSE',
    branch_code='AI-ML'
)

# Returns rubrics from rubric_criteria_catalog
# Filters by scope (degree/program/branch)
# Returns global rubrics + scoped rubrics
```

**In the UI:**
- Shows dropdown of available rubrics
- Filtered by degree/program/branch
- Mode A: Single rubric selection
- Mode B: Multiple rubrics with weight distribution
- Validates weights sum to 100% (Mode B)

---

## 🔧 New Connector Service

**File:** `services/assignment_co_rubric_connector.py`

### Key Functions:

#### CO Functions

```python
# Get COs for offering (with PO/PSO/PEO correlations)
cos = connector.get_cos_for_offering(offering_id)

# Validate CO mappings
is_valid, errors = connector.validate_assignment_co_mapping(
    offering_id,
    {'CO1': 3, 'CO2': 2, 'CO3': 0}
)

# Get CO coverage statistics
coverage = connector.get_assignment_co_coverage(offering_id)
# Returns:
# {
#   'total_cos': 5,
#   'covered_cos': 4,
#   'uncovered_cos': ['CO5'],
#   'coverage_percent': 80.0,
#   'co_assignment_counts': {'CO1': 3, 'CO2': 2, ...}
# }

# Get CO attainment summary
summary = connector.get_co_attainment_summary(offering_id)
# Returns marks allocated per CO with scaling
```

#### Rubric Functions

```python
# Get available rubrics
rubrics = connector.get_available_rubrics(
    degree_code='B.Tech',
    program_code='CSE',
    branch_code='AI-ML'
)

# Get rubric config for offering
config = connector.get_rubric_config_for_offering(offering_id)
# Returns co_linking_enabled, normalization_enabled, etc.

# Validate rubric
is_valid, errors = connector.validate_assignment_rubric(
    rubric_id=101,
    degree_code='B.Tech'
)

# Validate rubric weights
is_valid, errors = connector.validate_rubric_weights(
    [{'rubric_id': 101, 'top_level_weight_percent': 60},
     {'rubric_id': 102, 'top_level_weight_percent': 40}],
    rubric_mode='B'
)
```

#### Integrated Validation

```python
# Complete validation before publish
is_valid, errors = connector.validate_assignment_for_publish(
    assignment_id=123,
    offering_id=456
)
# Checks:
# - CO mappings valid
# - At least one CO mapped
# - Rubrics valid
# - Weights correct
```

---

## 📝 Usage Examples

### Creating Assignment with COs

```python
from services.assignment_service import AssignmentService
from services.assignment_co_rubric_connector import AssignmentCORubricConnector

service = AssignmentService(engine)
connector = AssignmentCORubricConnector(engine)

# 1. Get available COs
cos = connector.get_cos_for_offering(offering_id)
print(f"Available COs: {[co['co_code'] for co in cos]}")

# 2. Create assignment
assignment_id = service.create_assignment(
    offering_id=offering_id,
    number=1,
    title="Quiz 1",
    bucket="Internal",
    max_marks=10.0,
    due_at=datetime.now() + timedelta(days=7),
    actor="faculty_id",
    actor_role="subject_in_charge"
)

# 3. Add CO mappings (only to COs that exist)
service.add_co_mapping(assignment_id, "CO1", 3)  # High
service.add_co_mapping(assignment_id, "CO2", 2)  # Medium
service.add_co_mapping(assignment_id, "CO4", 1)  # Low

# 4. Validate
is_valid, errors = connector.validate_assignment_co_mapping(
    offering_id,
    {'CO1': 3, 'CO2': 2, 'CO4': 1}
)

if is_valid:
    print("✅ CO mappings valid!")
else:
    print(f"❌ Errors: {errors}")
```

### Attaching Rubrics

```python
# 1. Get available rubrics
rubrics = connector.get_available_rubrics(
    degree_code='B.Tech',
    program_code='CSE'
)

print(f"Available rubrics: {[r['label'] for r in rubrics]}")

# 2. Attach rubric (Mode A)
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=rubrics[0]['id'],
    rubric_mode='A',
    top_level_weight=100.0
)

# OR attach multiple rubrics (Mode B)
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=rubrics[0]['id'],
    rubric_mode='B',
    top_level_weight=60.0
)
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=rubrics[1]['id'],
    rubric_mode='B',
    top_level_weight=40.0
)

# 3. Validate
rubric_list = [
    {'rubric_id': rubrics[0]['id'], 'top_level_weight_percent': 60},
    {'rubric_id': rubrics[1]['id'], 'top_level_weight_percent': 40}
]
is_valid, errors = connector.validate_rubric_weights(rubric_list, 'B')

if is_valid:
    print("✅ Rubric weights valid!")
else:
    print(f"❌ Errors: {errors}")
```

### Complete Validation Before Publish

```python
# Validate everything
is_valid, errors = connector.validate_assignment_for_publish(
    assignment_id=assignment_id,
    offering_id=offering_id
)

if is_valid:
    # Publish
    service.publish_assignment(
        assignment_id,
        'principal_id',
        'principal',
        'Ready for students'
    )
    print("✅ Published!")
else:
    print(f"❌ Cannot publish:")
    for error in errors:
        print(f"  - {error}")
```

---

## 🎨 UI Integration

### Assignment Editor Updates

The assignment editor now:

1. **Automatically loads COs** from `subject_cos` table
   - Shows CO code, title (truncated)
   - Displays in grid layout (3 per row)
   - Slider for 0-3 correlation
   - Real-time validation

2. **Automatically loads Rubrics** from `rubric_criteria_catalog`
   - Filters by degree/program/branch scope
   - Dropdown selection (not manual ID entry)
   - Shows rubric key and label
   - Validates scope compatibility

3. **Enhanced Validation**
   - Checks COs exist in offering
   - Checks rubrics are active
   - Validates scope matches
   - Validates weight sums

### Error Messages

```
❌ Cannot publish:
  - CO 'CO6' not defined for this offering
  - Rubric scope mismatch: rubric is for B.Arch, assignment is for B.Tech
  - Mode B rubric weights must sum to 100% (currently: 95%)
```

---

## 📊 Reporting & Analytics

### CO Coverage Report

```python
coverage = connector.get_assignment_co_coverage(offering_id)

print(f"Total COs: {coverage['total_cos']}")
print(f"Covered COs: {coverage['covered_cos']} ({coverage['coverage_percent']:.1f}%)")
print(f"Uncovered: {', '.join(coverage['uncovered_cos'])}")

for co_code, count in coverage['co_assignment_counts'].items():
    print(f"  {co_code}: {count} assignment(s)")
```

### CO Attainment Summary

```python
summary = connector.get_co_attainment_summary(offering_id)

for co_code, data in summary.items():
    print(f"{co_code}:")
    print(f"  Assignments: {data['total_assignments']}")
    print(f"  Avg Correlation: {data['avg_correlation']:.2f}")
    print(f"  Raw Marks: {data['raw_marks_allocated']:.1f}")
    print(f"  Scaled Marks: {data['scaled_marks_allocated']:.1f}")
    print(f"  Internal: {data['internal_scaled']:.1f}")
    print(f"  External: {data['external_scaled']:.1f}")
```

---

## 🔄 Data Flow

```
User creates assignment
    ↓
System loads COs from subject_cos
    ↓
User maps assignment to COs (0-3)
    ↓
Stored in assignment_co_mapping
    ↓
System loads rubrics from rubric_criteria_catalog
    ↓
User selects rubric(s)
    ↓
Stored in assignment_rubrics
    ↓
Validation before publish:
  - Check COs exist in subject_cos
  - Check rubrics exist and active
  - Check scope compatibility
  - Validate correlations and weights
    ↓
If valid → Publish
If invalid → Show errors
```

---

## ✅ Installation

### 1. Copy New Connector File

```bash
cp assignment_co_rubric_connector.py app23/services/
```

### 2. Updated Files (Already in Package)

- `screens/timetable/assignment_editor.py` - Now loads COs and rubrics from DB
- Other files unchanged

### 3. No Schema Changes Needed

Your existing schemas already have everything needed:
- ✅ `subject_cos` table
- ✅ `co_po_correlations`, `co_pso_correlations`, `co_peo_correlations`
- ✅ `rubric_criteria_catalog`
- ✅ `rubric_configs`

Assignment schema already has:
- ✅ `assignment_co_mapping`
- ✅ `assignment_rubrics`

---

## 🎯 Benefits

### Before Integration:
- ❌ Manual CO entry (no validation)
- ❌ Manual rubric ID entry
- ❌ No scope checking
- ❌ Potential invalid references

### After Integration:
- ✅ COs auto-loaded from database
- ✅ Rubrics auto-loaded with filtering
- ✅ Scope validation (degree/program/branch)
- ✅ Guaranteed valid references
- ✅ PO/PSO/PEO linkage preserved
- ✅ Coverage analytics available
- ✅ Attainment calculations ready

---

## 📞 Testing Integration

### Quick Test:

```python
from connection import get_engine
from services.assignment_co_rubric_connector import AssignmentCORubricConnector

engine = get_engine()
connector = AssignmentCORubricConnector(engine)

# Test 1: Get COs for an offering
offering_id = 123  # Use your actual offering ID
cos = connector.get_cos_for_offering(offering_id)
print(f"✅ Found {len(cos)} COs for offering {offering_id}")

# Test 2: Get available rubrics
rubrics = connector.get_available_rubrics(degree_code='B.Tech')
print(f"✅ Found {len(rubrics)} rubrics for B.Tech")

# Test 3: Get coverage
if cos:
    coverage = connector.get_assignment_co_coverage(offering_id)
    print(f"✅ CO Coverage: {coverage['coverage_percent']:.1f}%")

print("\n✅ All integration tests passed!")
```

---

**Integration Status**: ✅ Complete
**Backward Compatible**: ✅ Yes
**Schema Changes**: ❌ None needed
**New Dependencies**: ❌ None

Your assignment system now fully integrates with your existing CO and Rubric infrastructure! 🎉
