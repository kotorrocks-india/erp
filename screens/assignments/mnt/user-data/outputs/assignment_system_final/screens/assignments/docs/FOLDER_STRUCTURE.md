# Assignment System - New Modular Structure

## 📁 Folder Organization

```
screens/assignments/                    ← Self-contained assignment module
├── __init__.py                        ← Module entry point
├── assignments_main.py                ← Main coordinator screen
│
├── services/                          ← Business logic layer
│   ├── __init__.py
│   ├── assignment_service.py          ← CRUD operations
│   └── assignment_co_rubric_connector.py  ← CO/Rubric integration
│
├── ui/                                ← UI components
│   ├── __init__.py
│   ├── assignment_list.py             ← List view with filters
│   ├── assignment_editor.py           ← Create/Edit form (7 tabs)
│   └── assignment_marks.py            ← Marks entry & scaling
│
├── schemas/                           ← Database schemas
│   ├── __init__.py
│   └── assignments_schema.py          ← 15 tables + 4 views
│
└── docs/                              ← Documentation
    ├── README.md
    ├── INTEGRATION_GUIDE.md
    ├── SCHEMA_INTEGRATION.md
    ├── QUICK_REFERENCE.md
    ├── DELIVERY_SUMMARY.md
    ├── FILE_PLACEMENT.txt
    ├── INTEGRATION_UPDATE.txt
    ├── PACKAGE_MANIFEST.txt
    └── START_HERE.txt
```

---

## 🎯 Why This Structure is Better

### Before (Scattered):
```
app23/
├── schemas/
│   └── assignments_schema.py         ← Far from related code
├── services/
│   ├── assignment_service.py          ← Mixed with other services
│   └── ...other services...
└── screens/
    ├── assignments1.py                ← Main file
    └── timetable/
        ├── assignment_list.py         ← UI components scattered
        ├── assignment_editor.py
        └── ...timetable files...
```

**Problems:**
- ❌ Assignment files scattered across project
- ❌ Mixed with timetable module
- ❌ Hard to locate related files
- ❌ Unclear dependencies
- ❌ Difficult to maintain

### After (Self-Contained):
```
app23/
└── screens/
    ├── timetable/
    │   └── ...timetable files...      ← Separate module
    │
    └── assignments/                   ← Everything in one place
        ├── services/
        ├── ui/
        ├── schemas/
        └── docs/
```

**Benefits:**
- ✅ All assignment code in one place
- ✅ Clear separation from other modules
- ✅ Easy to locate any file
- ✅ Dependencies obvious
- ✅ Easy to maintain/extend
- ✅ Can be moved/copied as a unit
- ✅ Clear module boundaries

---

## 🔧 Installation to Your Project

### Step 1: Copy the Entire Module

```bash
# Copy the complete assignments folder
cp -r screens/assignments "H:/New Volume (H)/Games/app23/screens/"
```

That's it! Everything is in one place.

### Step 2: Install Schema

```python
from screens.assignments.schemas.assignments_schema import install_assignments_schema
from connection import get_engine

engine = get_engine()
install_assignments_schema(engine)
```

### Step 3: Update Navigation

In your `app_weekly_planner.py`:

```python
# Import from the new location
from screens.assignments import render_assignments_page

# Add to navigation
pages = {
    # ... existing pages ...
    "📝 Assignments": render_assignments_page,
}
```

---

## 📦 What's in Each Folder

### `/services/` - Business Logic

**`assignment_service.py`** (27 KB)
- AssignmentService class
- CRUD operations (create, read, update, delete)
- Publishing workflow
- Archive/restore
- Scaling calculations
- Validation functions

**`assignment_co_rubric_connector.py`** (20 KB)
- AssignmentCORubricConnector class
- CO loading from subject_cos
- Rubric loading from rubric_criteria_catalog
- Scope-aware filtering
- Validation with existing schemas
- Coverage analytics
- Attainment calculations

### `/ui/` - User Interface Components

**`assignment_list.py`** (13 KB)
- List view with filters (bucket, status, visibility)
- Sorting options
- Summary metrics
- Scaling information display
- Action buttons (edit, view, publish, archive)
- Bulk operations
- Export to CSV

**`assignment_editor.py`** (23 KB)
- 7-tab creation/edit form:
  1. Basic Info
  2. CO & Rubrics (auto-loads from DB)
  3. Submission Configuration
  4. Late & Extensions
  5. Groups & Mentoring
  6. Integrity/Plagiarism
  7. Drop/Ignore
- Real-time validation
- CO mapping interface
- Rubric selection interface
- JSON config editors

**`assignment_marks.py`** (14 KB)
- Marks entry (manual & CSV import)
- Scaling calculations display
- Internal/External bucket views
- Statistics (avg, min, max)
- Export functionality

### `/schemas/` - Database Layer

**`assignments_schema.py`** (34 KB)
- 15 database tables:
  1. assignments (main table)
  2. assignment_co_mapping
  3. assignment_rubrics
  4. assignment_evaluators
  5. assignment_groups
  6. assignment_group_members
  7. assignment_mentors
  8. assignment_submissions
  9. assignment_marks
  10. assignment_extensions
  11. assignment_grade_patterns
  12. assignments_audit
  13. assignment_snapshots
  14. assignment_approvals
  15. 4 helper views
- Foreign key relationships
- Indexes for performance
- Audit trails
- Version control

### `/docs/` - Documentation

- **START_HERE.txt** - Quick overview
- **INTEGRATION_UPDATE.txt** - Schema integration summary
- **README.md** - System architecture
- **SCHEMA_INTEGRATION.md** - CO/Rubric integration guide
- **INTEGRATION_GUIDE.md** - Setup instructions
- **QUICK_REFERENCE.md** - Code examples
- **DELIVERY_SUMMARY.md** - Complete summary
- **FILE_PLACEMENT.txt** - Installation paths
- **PACKAGE_MANIFEST.txt** - File listing

---

## 🔗 Import Patterns

### From Outside the Module

```python
# In app_weekly_planner.py or other external files
from screens.assignments import render_assignments_page

# Use the service
from screens.assignments.services import AssignmentService
from connection import get_engine

service = AssignmentService(get_engine())
```

### Within the Module

```python
# In assignments_main.py
from screens.assignments.services.assignment_service import AssignmentService
from screens.assignments.ui.assignment_list import render_list

# In assignment_editor.py
from screens.assignments.services.assignment_co_rubric_connector import AssignmentCORubricConnector
```

### Installing Schema

```python
# Anywhere in your app
from screens.assignments.schemas import install_assignments_schema
from connection import get_engine

install_assignments_schema(get_engine())
```

---

## 🎨 Module Independence

This structure makes the assignment module:

1. **Self-Contained** - All code in one directory
2. **Portable** - Can copy entire folder to another project
3. **Testable** - Easy to test in isolation
4. **Maintainable** - Clear what belongs to assignments
5. **Extensible** - Easy to add new features
6. **Documentable** - Docs right with the code

---

## 🚀 Adding New Features

### Adding a New UI Component

```python
# Create: screens/assignments/ui/assignment_analytics.py
def render_analytics(service, offering_id):
    """Render analytics dashboard."""
    st.write("Analytics here")

# Update: screens/assignments/ui/__init__.py
from .assignment_analytics import render_analytics
__all__ = [..., 'render_analytics']

# Use in: screens/assignments/assignments_main.py
from screens.assignments.ui.assignment_analytics import render_analytics
```

### Adding a New Service

```python
# Create: screens/assignments/services/assignment_notifications.py
class AssignmentNotifications:
    """Handle assignment notifications."""
    pass

# Update: screens/assignments/services/__init__.py
from .assignment_notifications import AssignmentNotifications
__all__ = [..., 'AssignmentNotifications']

# Use anywhere:
from screens.assignments.services import AssignmentNotifications
```

---

## 📊 Comparison

### File Count by Location

**Old Structure:**
- Root schemas/: 1 file
- Root services/: 2 files
- screens/: 1 file
- screens/timetable/: 3 files
- Documentation: Separate docs/ folder
**Total**: 7 files across 5 locations

**New Structure:**
- screens/assignments/: Everything
  - services/: 2 files
  - ui/: 3 files
  - schemas/: 1 file
  - docs/: 9 files
**Total**: 15 files in 1 location

---

## 🔍 Finding Files

### Old Way:
- "Where's the CO connector?" → Check services/
- "Where's the list view?" → Check screens/timetable/
- "Where's the schema?" → Check schemas/
- "Where's the docs?" → Check docs/ or root/

### New Way:
- "Where's anything assignment-related?" → screens/assignments/
- "Business logic?" → screens/assignments/services/
- "UI?" → screens/assignments/ui/
- "Database?" → screens/assignments/schemas/
- "Docs?" → screens/assignments/docs/

**Everything in one place!**

---

## ⚙️ Configuration

### Module Configuration File (Optional)

You can add `screens/assignments/config.py`:

```python
"""Assignment Module Configuration"""

# Module metadata
MODULE_NAME = "Assignments"
MODULE_VERSION = "1.1.0"
MODULE_ICON = "📝"

# Feature flags
ENABLE_CO_MAPPING = True
ENABLE_RUBRICS = True
ENABLE_GROUP_WORK = True
ENABLE_MENTORING = True
ENABLE_PLAGIARISM = True

# Defaults
DEFAULT_GRACE_MINUTES = 15
DEFAULT_LATE_PENALTY = 10
MAX_FILE_SIZE_MB = 100

# Import for use
from screens.assignments.config import *
```

---

## 🎯 Summary

### Old Structure Issues:
- ❌ Files scattered
- ❌ Mixed with other modules
- ❌ Hard to locate
- ❌ Unclear ownership
- ❌ Difficult to move/copy

### New Structure Benefits:
- ✅ Everything in one folder
- ✅ Clear separation
- ✅ Easy to locate
- ✅ Obvious ownership
- ✅ Simple to move/copy
- ✅ Better for team work
- ✅ Scales well

---

## 📍 Final Structure

```
H:/New Volume (H)/Games/app23/
└── screens/
    ├── periods/
    │   └── ...period files...
    ├── timetable/
    │   └── ...timetable files...
    └── assignments/              ← New self-contained module
        ├── __init__.py
        ├── assignments_main.py
        ├── services/
        │   ├── __init__.py
        │   ├── assignment_service.py
        │   └── assignment_co_rubric_connector.py
        ├── ui/
        │   ├── __init__.py
        │   ├── assignment_list.py
        │   ├── assignment_editor.py
        │   └── assignment_marks.py
        ├── schemas/
        │   ├── __init__.py
        │   └── assignments_schema.py
        └── docs/
            ├── README.md
            ├── INTEGRATION_GUIDE.md
            └── ...other docs...
```

---

**This is a much cleaner, more maintainable structure!** ✨

Version: 1.1.0 (Reorganized Structure)
Last Updated: November 27, 2024
Status: Ready for Deployment ✅
