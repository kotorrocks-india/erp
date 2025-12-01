# Assignment System - Quick Reference Guide

## 🚀 Common Operations Cheat Sheet

### Initialize Service
```python
from connection import get_engine
from services.assignment_service import AssignmentService

engine = get_engine()
service = AssignmentService(engine)
```

---

## CREATE Operations

### Create Basic Assignment
```python
assignment_id = service.create_assignment(
    offering_id=123,
    number=1,
    title="Quiz 1",
    bucket="Internal",  # or "External"
    max_marks=10.0,
    due_at=datetime(2024, 12, 31, 23, 59),
    description="Chapter 1-3 quiz",
    actor="faculty_id",
    actor_role="subject_in_charge"
)
```

### Create with Full Configuration
```python
assignment_id = service.create_assignment(
    offering_id=123,
    number=2,
    title="Lab Report 1",
    bucket="Internal",
    max_marks=20.0,
    due_at=datetime(2024, 12, 31, 23, 59),
    description="Detailed lab report on...",
    
    # Optional configurations
    grace_minutes=30,
    visibility_state="Hidden",  # Hidden, Visible_Accepting, Closed, Results_Published
    results_publish_mode="marks_and_rubrics",  # marks_and_rubrics, pass_fail_only, grade_pattern
    
    # JSON configs
    submission_config={
        "types": ["File Upload", "Presentation"],
        "file_upload": {
            "multiple_files": True,
            "max_file_mb": 50,
            "allowed_types": ["pdf", "docx", "pptx"],
            "storage": "local_signed_url"
        }
    },
    
    late_policy={
        "mode": "allow_with_penalty",
        "penalty_percent_per_day": 10,
        "penalty_cap_percent": 50,
        "hard_cutoff_at": None
    },
    
    group_config={
        "enabled": True,
        "grouping_model": "free_form",
        "min_size": 2,
        "max_size": 4
    },
    
    plagiarism_config={
        "enabled": True,
        "warn_threshold_percent": 20,
        "block_threshold_percent": 40,
        "exclude_bibliography_flag": True
    },
    
    actor="faculty_id",
    actor_role="subject_in_charge"
)
```

### Add CO Mapping
```python
# Add multiple COs
service.add_co_mapping(assignment_id, "CO1", 3)  # High correlation
service.add_co_mapping(assignment_id, "CO2", 2)  # Medium correlation
service.add_co_mapping(assignment_id, "CO3", 0)  # No correlation
service.add_co_mapping(assignment_id, "CO4", 1)  # Low correlation
```

### Attach Rubric (Mode A - Single)
```python
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=101,
    rubric_mode='A',
    top_level_weight=100.0,
    rubric_version="v1.0"
)
```

### Attach Multiple Rubrics (Mode B)
```python
# Rubric 1 - 60% weight
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=101,
    rubric_mode='B',
    top_level_weight=60.0,
    rubric_version="v1.0"
)

# Rubric 2 - 40% weight
service.attach_rubric(
    assignment_id=assignment_id,
    rubric_id=102,
    rubric_mode='B',
    top_level_weight=40.0,
    rubric_version="v1.2"
)
# Total must equal 100%
```

### Assign Evaluators
```python
# Subject in-charge
service.assign_evaluator(
    assignment_id=assignment_id,
    faculty_id="FAC001",
    evaluator_role="subject_in_charge",
    can_edit_marks=True,
    can_moderate=True,
    assigned_by="admin"
)

# Additional evaluator
service.assign_evaluator(
    assignment_id=assignment_id,
    faculty_id="FAC002",
    evaluator_role="evaluator",
    can_edit_marks=True,
    can_moderate=False,
    assigned_by="FAC001"
)
```

---

## READ Operations

### Get Single Assignment
```python
assignment = service.get_assignment(assignment_id)
print(assignment['title'])
print(assignment['max_marks'])
print(assignment['submission_config'])  # Returns dict
```

### List All Assignments for Offering
```python
assignments = service.list_assignments(offering_id=123)

for asg in assignments:
    print(f"#{asg['number']}: {asg['title']} - {asg['max_marks']} marks")
```

### List with Filters
```python
# Only published Internal assignments
internal = service.list_assignments(
    offering_id=123,
    bucket="Internal",
    status="published"
)

# Only assignments accepting submissions
accepting = service.list_assignments(
    offering_id=123,
    visibility_state="Visible_Accepting"
)

# Complex filter
filtered = service.list_assignments(
    ay_label="2024-25",
    degree_code="B.Tech",
    year=2,
    term=1,
    subject_code="CS201",
    bucket="External"
)
```

### Get CO Mappings
```python
co_mappings = service.get_co_mappings(assignment_id)

for mapping in co_mappings:
    print(f"{mapping['co_code']}: {mapping['correlation_value']}")
# Output: CO1: 3, CO2: 2, CO4: 1
```

### Get Attached Rubrics
```python
rubrics = service.get_attached_rubrics(assignment_id)

for rubric in rubrics:
    print(f"Rubric {rubric['rubric_id']} (Mode {rubric['rubric_mode']}): {rubric['top_level_weight_percent']}%")
```

### Get Evaluators
```python
evaluators = service.get_evaluators(assignment_id)

for evaluator in evaluators:
    print(f"{evaluator['faculty_name']} ({evaluator['evaluator_role']})")
```

### Get Statistics
```python
stats = service.get_assignment_statistics(assignment_id)

print(f"Submissions: {stats['submission_count']}")
print(f"Late: {stats['late_submission_count']}")
print(f"Graded: {stats['graded_count']}")
print(f"Average: {stats['avg_marks']:.2f}")
```

---

## UPDATE Operations

### Update Basic Fields
```python
service.update_assignment(
    assignment_id=assignment_id,
    actor="faculty_id",
    actor_role="subject_in_charge",
    reason="Updating due date",  # Required for published assignments
    
    # Fields to update
    title="Quiz 1 (Revised)",
    max_marks=15.0,
    description="Updated instructions..."
)
```

### Update Visibility
```python
# Open for submissions
service.update_visibility(
    assignment_id=assignment_id,
    new_state="Visible_Accepting",
    actor="faculty_id",
    actor_role="subject_in_charge"
)

# Close submissions
service.update_visibility(
    assignment_id=assignment_id,
    new_state="Closed",
    actor="faculty_id",
    actor_role="subject_in_charge"
)

# Publish results
service.update_visibility(
    assignment_id=assignment_id,
    new_state="Results_Published",
    actor="faculty_id",
    actor_role="subject_in_charge"
)
```

### Update JSON Configs
```python
# Update submission config
service.update_assignment(
    assignment_id=assignment_id,
    actor="faculty_id",
    actor_role="subject_in_charge",
    
    submission_config={
        "types": ["File Upload", "Physical/Studio/Jury"],
        "file_upload": {
            "multiple_files": False,  # Changed
            "max_file_mb": 100,
            "allowed_types": ["pdf"],  # Restricted
            "storage": "local_signed_url"
        }
    }
)

# Update late policy
service.update_assignment(
    assignment_id=assignment_id,
    actor="faculty_id",
    actor_role="subject_in_charge",
    
    late_policy={
        "mode": "no_late",  # Changed - no more late submissions
        "penalty_percent_per_day": 0,
        "penalty_cap_percent": 0,
        "hard_cutoff_at": None
    }
)
```

---

## PUBLISH & ARCHIVE Operations

### Publish Assignment
```python
service.publish_assignment(
    assignment_id=assignment_id,
    approver_id="principal_id",
    approver_role="principal",
    reason="Ready for student access"
)
# Creates snapshot automatically
```

### Archive Assignment
```python
service.archive_assignment(
    assignment_id=assignment_id,
    actor="admin_id",
    actor_role="superadmin",
    reason="Semester ended"
)
```

---

## DELETE Operations

### Delete Assignment (Only Drafts Without Submissions)
```python
try:
    service.delete_assignment(
        assignment_id=assignment_id,
        actor="admin_id",
        actor_role="superadmin"
    )
except ValueError as e:
    print(f"Cannot delete: {e}")
    # Use archive instead if has submissions
```

---

## MARKS & SCALING Operations

### Calculate Scaling Factor
```python
# For Internal bucket
scaling_factor, scaled_marks = service.calculate_scaled_marks(
    offering_id=123,
    bucket="Internal"
)

print(f"Scaling Factor: {scaling_factor:.4f}")
print(f"Found {len(scaled_marks)} marks records")

for mark in scaled_marks:
    print(f"Student {mark['student_roll_no']}: Raw={mark['marks_obtained']}, Scaled={mark['scaled_marks']:.2f}")
```

### Example Scaling Calculation
```python
# Given:
# - Offering Internal Max: 40
# - Assignment 1: 10 marks (published)
# - Assignment 2: 15 marks (published)
# - Assignment 3: 25 marks (published)
# - Total Raw: 10 + 15 + 25 = 50

scaling_factor = 40 / 50  # = 0.8

# If student gets 8/10 on Assignment 1:
raw_marks = 8
scaled_marks = raw_marks * scaling_factor  # 8 * 0.8 = 6.4
```

---

## VERSIONING & AUDIT Operations

### Create Snapshot
```python
from assignments_schema import create_assignment_snapshot

snapshot_id = create_assignment_snapshot(
    engine=engine,
    assignment_id=assignment_id,
    snapshot_type="manual",
    actor="admin_id",
    note="Before major changes"
)
```

### Log Audit Entry
```python
from assignments_schema import log_audit

log_audit(
    engine=engine,
    assignment_id=assignment_id,
    offering_id=offering_id,
    actor_id="faculty_id",
    actor_role="subject_in_charge",
    operation="custom_operation",
    scope="assignment",
    before_data={"old": "value"},
    after_data={"new": "value"},
    reason="Custom operation performed",
    source="ui",
    step_up=False
)
```

---

## QUERY PATTERNS

### Get All Assignments for a Term
```python
assignments = service.list_assignments(
    ay_label="2024-25",
    degree_code="B.Tech",
    year=2,
    term=1
)
```

### Get Overdue Assignments
```python
from datetime import datetime

all_assignments = service.list_assignments(offering_id=123)
overdue = [
    a for a in all_assignments 
    if datetime.fromisoformat(a['due_at']) < datetime.now()
    and a['visibility_state'] in ['Visible_Accepting', 'Closed']
]
```

### Get Assignments by Faculty
```python
# Get all assignments where faculty is evaluator
from sqlalchemy import text as sa_text

with engine.begin() as conn:
    results = conn.execute(sa_text("""
        SELECT a.* FROM assignments a
        JOIN assignment_evaluators ae ON a.id = ae.assignment_id
        WHERE ae.faculty_id = :faculty_id
    """), {"faculty_id": "FAC001"}).fetchall()
    
    faculty_assignments = [dict(r._mapping) for r in results]
```

---

## ERROR HANDLING

### Common Validation Errors
```python
try:
    assignment_id = service.create_assignment(...)
except ValueError as e:
    if "Assignment number" in str(e):
        print("Duplicate assignment number")
    elif "Due date" in str(e):
        print("Due date must be in future")
    elif "CO mapping" in str(e):
        print("At least one CO must be > 0")
```

### Publishing Validation
```python
try:
    service.publish_assignment(
        assignment_id=assignment_id,
        approver_id="principal_id",
        approver_role="principal",
        reason="Ready"
    )
except ValueError as e:
    print(f"Cannot publish: {e}")
    # Common reasons:
    # - Due date in past
    # - No CO mappings with value > 0
    # - Mode B rubric weights don't sum to 100%
```

---

## BULK OPERATIONS

### Create Multiple Assignments
```python
assignments_data = [
    {"number": 1, "title": "Quiz 1", "max_marks": 10, "bucket": "Internal"},
    {"number": 2, "title": "Quiz 2", "max_marks": 10, "bucket": "Internal"},
    {"number": 3, "title": "Lab 1", "max_marks": 20, "bucket": "Internal"},
]

for data in assignments_data:
    try:
        assignment_id = service.create_assignment(
            offering_id=123,
            number=data["number"],
            title=data["title"],
            bucket=data["bucket"],
            max_marks=data["max_marks"],
            due_at=datetime.now() + timedelta(days=7),
            actor="admin",
            actor_role="superadmin"
        )
        print(f"✅ Created: {data['title']}")
    except Exception as e:
        print(f"❌ Failed: {data['title']} - {e}")
```

### Bulk Update Visibility
```python
assignments = service.list_assignments(offering_id=123, status="published")

for asg in assignments:
    service.update_visibility(
        assignment_id=asg['id'],
        new_state="Closed",
        actor="admin",
        actor_role="superadmin"
    )
    print(f"✅ Closed: {asg['title']}")
```

---

## TIPS & BEST PRACTICES

1. **Always validate before publish**: Check CO mappings and rubric weights
2. **Use snapshots**: Create snapshot before major changes
3. **Log everything**: Use audit logging for traceability
4. **Handle JSON carefully**: Validate JSON configs before updating
5. **Check permissions**: Verify user role before operations
6. **Test scaling**: Always verify scaling calculations match expectations
7. **Archive, don't delete**: Use archive for assignments with submissions
8. **Batch operations**: Use transactions for bulk operations

---

## COMMON WORKFLOWS

### Complete Assignment Creation Workflow
```python
# 1. Create assignment
assignment_id = service.create_assignment(...)

# 2. Add CO mappings
service.add_co_mapping(assignment_id, "CO1", 3)
service.add_co_mapping(assignment_id, "CO2", 2)

# 3. Attach rubric
service.attach_rubric(assignment_id, rubric_id=101, rubric_mode='A')

# 4. Assign evaluators
service.assign_evaluator(assignment_id, "FAC001", "subject_in_charge")

# 5. Review and publish
service.publish_assignment(assignment_id, "principal_id", "principal", "Ready")

# 6. Open for submissions
service.update_visibility(assignment_id, "Visible_Accepting", "faculty", "subject_in_charge")
```

### Complete Grading Workflow
```python
# 1. Close submissions
service.update_visibility(assignment_id, "Closed", "faculty", "subject_in_charge")

# 2. Enter marks (done via UI or import)

# 3. Calculate scaling
scaling_factor, scaled_marks = service.calculate_scaled_marks(offering_id, "Internal")

# 4. Review marks

# 5. Publish results
service.update_visibility(assignment_id, "Results_Published", "faculty", "subject_in_charge")
```

---

**Quick Reference Version**: 1.0
**Last Updated**: November 2024
