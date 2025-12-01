# Assignment Management System - Complete Implementation
## Based on Slide 25 YAML Specification

### 📁 Project Structure

```
assignment_system/
├── assignments_schema.py          # Database schema (all 15 tables + views)
├── services/
│   └── assignment_service.py      # Business logic layer
├── screens/
│   ├── assignments1.py            # Main entry point
│   └── timetable/
│       ├── assignment_list.py     # List view with filters & actions
│       ├── assignment_editor.py   # Create/Edit with 7-tab form
│       ├── assignment_marks.py    # Marks entry & scaling
│       ├── assignment_evaluators.py    # (To be created)
│       ├── assignment_submissions.py   # (To be created)
│       └── assignment_analytics.py     # (To be created)
└── README.md                      # This file
```

### 🗄️ Database Schema

The `assignments_schema.py` file creates **15 comprehensive tables**:

1. **assignments** - Core assignment table with JSON configs
2. **assignment_co_mapping** - CO correlation mappings (0-3 scale)
3. **assignment_rubrics** - Rubric attachments (Mode A/B)
4. **assignment_evaluators** - Faculty evaluator assignments
5. **assignment_groups** - Student group definitions
6. **assignment_group_members** - Group membership
7. **assignment_mentors** - Student-mentor assignments
8. **assignment_submissions** - Submission tracking
9. **assignment_marks** - Marks with rubric breakdown
10. **assignment_extensions** - Extension requests
11. **assignment_grade_patterns** - Custom grade bands
12. **assignments_audit** - Complete audit trail
13. **assignment_snapshots** - Version snapshots for rollback
14. **assignment_approvals** - Approval workflow tracking
15. **4 Helper Views** - For statistics, faculty load, progress

### ✨ Key Features Implemented

#### 1. **Comprehensive Configuration System**
   - **7 JSON config fields** for flexibility:
     - `submission_config` - File uploads, MCQ, presentations
     - `late_policy` - Penalties, cutoffs, grace periods
     - `extensions_config` - Request handling
     - `group_config` - Group work settings
     - `mentoring_config` - Mentoring preferences
     - `plagiarism_config` - Integrity checking
     - `drop_config` - Class-wide drops & excuses

#### 2. **CO Mapping & Rubrics**
   - **CO Correlation**: 0-3 scale (None/Low/Med/High)
   - **Validation**: At least one CO must be > 0
   - **Rubric Modes**:
     - **Mode A**: Single rubric (100% weight)
     - **Mode B**: Multiple rubrics with top-level weights (must sum to 100%)
   - **Versioning**: Track rubric versions

#### 3. **Marks Scaling System**
   - **Implicit Weighting**: Based on assignment max marks
   - **Automatic Scaling**: Raw marks × scaling factor = scaled marks
   - **Formula**: 
     ```
     Scaling Factor = Offering Bucket Max / Sum(Assignment Raw Max)
     Scaled Marks = Raw Marks × Scaling Factor
     ```
   - **Real-time Calculation**: Updates as assignments are added/removed

#### 4. **Workflow & Permissions**
   - **Status Flow**: draft → published → archived/deactivated
   - **Visibility States**:
     - Hidden (not visible to students)
     - Visible_Accepting (open for submissions)
     - Closed (submissions closed)
     - Results_Published (results visible)
   - **Approval Requirements**:
     - Publish: Requires PD approval
     - Major edits: Requires PD approval
     - Class-wide drops: Requires PD approval

#### 5. **Versioning & Audit**
   - **Snapshots**: Created on create/publish/edit/rollback
   - **Rollback Capability**: Restore to previous versions
   - **Comprehensive Audit**: Tracks all changes with actor, operation, before/after data
   - **Retention**: Keep last 100 snapshots per assignment

### 🎯 UI Components

#### **Main Screen** (`assignments1.py`)
- Context-aware (degree/program/branch/AY/year/term/subject)
- Subject offering selector
- 6 main tabs for different functions
- Integration with existing project structure

#### **List View** (`assignment_list.py`)
- **Filters**: Bucket, Status, Visibility, Date range
- **Sorting**: By number, due date, max marks
- **Summary Metrics**: Total, Internal/External split, Published count
- **Scaling Info**: Real-time calculation display
- **Action Buttons**: Edit, View, Publish, Close, Archive, Delete
- **Bulk Actions**: Mass publish, CSV export, reports

#### **Editor** (`assignment_editor.py`)
- **7-Tab Form** matching YAML structure:
  1. **Basic**: Number, title, bucket, marks, due date, visibility
  2. **CO & Rubrics**: CO mappings (0-3 scale), rubric attachments
  3. **Submission**: Types, file upload config
  4. **Late & Extensions**: Penalties, cutoffs, extension policies
  5. **Groups & Mentoring**: Group work, mentor assignments
  6. **Integrity**: Plagiarism thresholds, bibliography exclusion
  7. **Drop/Ignore**: Class-wide drops, per-student excuses

#### **Marks Entry** (`assignment_marks.py`)
- **Bucket-wise View**: Separate tabs for Internal/External
- **Entry Methods**:
  - Manual entry (student-by-student)
  - CSV import (bulk upload)
  - View existing marks
- **Scaling Display**: Shows scaling factor and calculations
- **Statistics**: Average, min, max, graded count
- **Export**: CSV and Excel formats

### 🔄 Integration Points

#### **With Existing Schemas**:
1. **subject_offerings** - Parent offering context
2. **weekly_subject_distribution** - Faculty assignments (for evaluators)
3. **subjects_catalog** - Subject details
4. **academic_years/semesters** - Temporal context
5. **degrees/programs/branches** - Organizational hierarchy
6. **students** (to be integrated) - Student rosters

#### **With Future Modules**:
- **Slide 20 (COs)** - Course outcome definitions
- **Slide 21 (Rubrics)** - Rubric bank
- **Slide 22 (Distribution)** - Weekly presence
- **Slide 23 (Timetable)** - Slot linkages

### 📊 Service Layer (`assignment_service.py`)

Provides clean API for all operations:

```python
service = AssignmentService(engine)

# Create
assignment_id = service.create_assignment(offering_id, number, title, ...)
service.add_co_mapping(assignment_id, "CO1", 3)
service.attach_rubric(assignment_id, rubric_id, mode='A')
service.assign_evaluator(assignment_id, faculty_id, 'evaluator')

# Read
assignment = service.get_assignment(assignment_id)
assignments = service.list_assignments(offering_id=..., bucket='Internal')
co_mappings = service.get_co_mappings(assignment_id)
stats = service.get_assignment_statistics(assignment_id)

# Update
service.update_assignment(assignment_id, actor, role, title="New Title")
service.update_visibility(assignment_id, 'Visible_Accepting', actor, role)

# Publish/Archive
service.publish_assignment(assignment_id, approver, role, reason)
service.archive_assignment(assignment_id, actor, role, reason)

# Delete
service.delete_assignment(assignment_id, actor, role)

# Scaling
factor, scaled_marks = service.calculate_scaled_marks(offering_id, 'Internal')
```

### 🛠️ Installation & Setup

#### 1. **Install Schema**
```python
from sqlalchemy import create_engine
from assignments_schema import install_assignments_schema

engine = create_engine("sqlite:///your_database.db")
install_assignments_schema(engine)
```

#### 2. **Add to Project**
- Copy `assignments_schema.py` to your schemas folder
- Copy `assignment_service.py` to `services/` folder
- Copy `assignments1.py` to `screens/` folder
- Copy `timetable/*.py` files to `screens/timetable/` folder

#### 3. **Register in Main App**
```python
# In your main app navigation
pages = {
    "Assignments": "screens.assignments1",
    # ... other pages
}
```

### 🔐 Permissions Model

Based on YAML specification:

| Operation | Allowed Roles |
|-----------|--------------|
| **View** | superadmin, tech_admin, degree_head, branch_head, principal, director, office_admin, subject_faculty, class_in_charge |
| **Edit** | superadmin, tech_admin, degree_head, branch_head, subject_in_charge |
| **Publish** | principal, director (requires approval) |
| **Delete** | superadmin (hard delete) |
| **Import/Export** | superadmin, tech_admin, degree_head, branch_head, subject_in_charge |

### 🎨 Design Principles

1. **Modular Architecture**: Each tab is a separate file for maintainability
2. **JSON Flexibility**: Complex configs stored as JSON for easy extension
3. **Implicit Weighting**: No manual percentages - weights derived from max marks
4. **Comprehensive Audit**: Every change tracked with actor, operation, before/after
5. **Version Control**: Snapshot-based rollback capability
6. **Validation-First**: Strict validation before publish to prevent data issues
7. **Context-Aware**: Always respects degree/program/branch/AY/year/term context

### 📈 Scaling Example

**Scenario**: Internal bucket max = 40 marks

| Assignment | Raw Max | Published |
|------------|---------|-----------|
| Quiz 1 | 10 | Yes |
| Quiz 2 | 10 | Yes |
| Lab 1 | 15 | Yes |
| Lab 2 | 15 | Yes |
| **Total** | **50** | - |

**Scaling Factor**: 40 / 50 = **0.8**

If a student gets 8/10 on Quiz 1:
- Raw marks: 8
- Scaled marks: 8 × 0.8 = **6.4**

### ⚠️ Important Notes

1. **CO Validation**: At least one CO must have correlation > 0 to publish
2. **Rubric Mode B**: Weights must sum exactly to 100%
3. **Due Date**: Must be in future when publishing
4. **Delete Restriction**: Cannot delete if submissions/marks exist (archive instead)
5. **Major Edits**: Changes to max_marks, bucket, due_at, late_policy require PD approval
6. **Scaling**: Updates automatically as assignments are added/removed

### 🚀 Next Steps

#### **Immediate (High Priority)**:
1. Create `assignment_evaluators.py` - Faculty evaluator management
2. Create `assignment_submissions.py` - Student submission tracking
3. Integrate with student roster for actual student data
4. Connect with faculty table for evaluator assignments

#### **Short-term**:
5. Create `assignment_analytics.py` - Reports & visualizations
6. Implement approval workflow UI
7. Add notification system
8. Implement plagiarism detection integration

#### **Medium-term**:
9. Build mobile-responsive views
10. Add bulk operations (mass publish, mass marks entry)
11. Create Excel/PDF export templates
12. Implement grade pattern calculator

#### **Long-term**:
13. Integration with LMS/external systems
14. Advanced analytics (predictive, trends)
15. Student self-service portal
16. Automated workflow triggers

### 📝 YAML Coverage Checklist

- ✅ **Basic Structure**: All core fields implemented
- ✅ **CO Mapping**: 0-3 scale with validation
- ✅ **Rubrics**: Mode A/B with weight validation
- ✅ **Submission Config**: All types supported
- ✅ **Late Policy**: All three modes
- ✅ **Extensions**: Request/approval workflow
- ✅ **Group Work**: Configuration ready
- ✅ **Mentoring**: Multi-mentor support
- ✅ **Plagiarism**: Thresholds and exclusions
- ✅ **Drop/Ignore**: Class-wide and per-student
- ✅ **Visibility**: All 4 states
- ✅ **Results Publishing**: 3 modes
- ✅ **Workflow**: Draft/Published/Archived
- ✅ **Permissions**: Role-based access
- ✅ **Approvals**: PD approval workflow
- ✅ **Versioning**: Snapshots and rollback
- ✅ **Audit**: Comprehensive tracking
- ✅ **Scaling**: Implicit weighting
- ✅ **Views**: Statistics and analytics
- 🔲 **Import/Export**: Templates created, bulk ops pending
- 🔲 **Notifications**: Schema ready, integration pending

### 🤝 Contributing

When extending this system:

1. **Follow the modular pattern**: Each feature in its own file
2. **Use the service layer**: Don't write SQL in UI components
3. **Log everything**: Use audit logging for all changes
4. **Validate strictly**: Better to reject invalid data than fix later
5. **Test scaling**: Always verify scaling calculations
6. **Document configs**: JSON fields should be well-documented

### 📞 Support

For questions or issues:
1. Check the YAML specification (slide25_AY_Assignments.txt)
2. Review this README
3. Examine the service layer for usage examples
4. Check existing UI components for patterns

---

**Version**: 1.0.0
**Last Updated**: November 2024
**Based On**: Slide 25 YAML Specification
**Status**: Core features complete, additional modules in progress
