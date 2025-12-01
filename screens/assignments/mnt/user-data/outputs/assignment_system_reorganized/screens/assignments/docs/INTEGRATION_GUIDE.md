# Integration Guide - Adding Assignment System to Your LPEP Project

## 📍 Current Project Structure (Your H:/New Volume (H)/Games/app23)

```
app23/
├── app_weekly_planner.py           # Main entry point
├── connection.py                   # Database connection
├── context.py                      # Context management
├── config.py                       # Configuration
├── screens/
│   ├── __init__.py
│   ├── periods_page.py            # Existing screen
│   ├── (other screens...)
│   └── timetable/
│       ├── __init__.py
│       ├── operations_tab.py      # Existing
│       ├── distribution_tab.py    # Existing
│       ├── timetable_grid_tab.py  # Existing
│       └── (other tabs...)
├── services/
│   ├── __init__.py
│   ├── faculty_service.py         # Existing
│   ├── operations_service.py      # Existing
│   ├── timetable_service.py       # Existing
│   └── (other services...)
└── schemas/
    ├── __init__.py
    ├── degrees_schema.py          # Existing
    ├── subject_offerings_schema.py # Existing
    ├── weekly_subject_distribution_schema.py # Existing
    └── (other schemas...)
```

## 🔧 Integration Steps

### Step 1: Copy Assignment Files

```bash
# Copy schema file
cp assignment_system/assignments_schema.py app23/schemas/

# Copy service file
cp assignment_system/services/assignment_service.py app23/services/

# Copy main screen
cp assignment_system/screens/assignments1.py app23/screens/

# Copy timetable modules
cp assignment_system/screens/timetable/assignment_list.py app23/screens/timetable/
cp assignment_system/screens/timetable/assignment_editor.py app23/screens/timetable/
cp assignment_system/screens/timetable/assignment_marks.py app23/screens/timetable/
```

### Step 2: Register Schema

Add to your schema registry (likely in a master schema installer):

```python
# In your main schema installation file
from schemas.assignments_schema import install_assignments_schema

def install_all_schemas(engine):
    """Install all schemas."""
    # ... existing schema installations ...
    
    # Add assignment schema
    install_assignments_schema(engine)
    
    print("✅ All schemas installed")
```

Or if using your registry system:

```python
# The schema is already decorated with @register
# Just import it and it will auto-register
from schemas import assignments_schema  # This will auto-register
```

### Step 3: Add to Main Navigation

In `app_weekly_planner.py`, add assignment screen to navigation:

```python
import streamlit as st
from screens import assignments1

# Your existing pages dictionary
pages = {
    "Weekly Planner": weekly_planner_page,
    "Periods Config": periods_config_page,
    "Timetable Grid": timetable_grid_page,
    "Distribution": distribution_page,
    # Add this:
    "📝 Assignments": assignments1.render_assignments_page,
}

# Your existing navigation code
selection = st.sidebar.selectbox("Navigate", list(pages.keys()))
pages[selection]()
```

### Step 4: Update __init__.py Files

```python
# app23/services/__init__.py
from .assignment_service import AssignmentService

# app23/screens/timetable/__init__.py
from . import assignment_list
from . import assignment_editor
from . import assignment_marks
```

## 🔗 Database Dependencies

The assignment schema depends on these existing tables:

1. **subject_offerings** (id) - REQUIRED
   - Already exists in your project ✅
   - Foreign key: `assignments.offering_id → subject_offerings.id`

2. **academic_years** (ay_code) - REQUIRED
   - Should exist in your project
   - Foreign key: `subject_offerings.ay_label → academic_years.ay_code`

3. **degrees** (code) - REQUIRED
   - Already exists (degrees_schema.py) ✅
   - Foreign key: `subject_offerings.degree_code → degrees.code`

4. **faculty** (id) - OPTIONAL
   - Used for evaluator assignments
   - Join: `assignment_evaluators.faculty_id → faculty.id`

5. **students** (roll_no) - OPTIONAL
   - Used for marks, submissions, groups
   - Will need to be created or integrated

## 🎯 Context Integration

Your project already has context management (`context.py`). The assignment screen uses it:

```python
from context import get_context

ctx = get_context()
# Expects: degree_code, program_code, branch_code, ay_label, year, term, division_code

# Assignment screen automatically uses these filters
offerings = get_offerings_for_context(engine, ctx)
```

**No changes needed** - the assignment system will work with your existing context.

## 📊 Data Flow

```
User selects context in main page
    ↓
Context stored in session_state
    ↓
Assignment screen reads context
    ↓
Filters subject_offerings by context
    ↓
User selects subject offering
    ↓
Shows assignments for that offering
    ↓
All operations scoped to that offering
```

## 🔍 Verification Steps

### 1. Schema Installation
```python
from sqlalchemy import create_engine
from schemas.assignments_schema import install_assignments_schema

engine = create_engine("sqlite:///your_database.db")

try:
    install_assignments_schema(engine)
    print("✅ Schema installed successfully")
except Exception as e:
    print(f"❌ Schema installation failed: {e}")
```

### 2. Service Test
```python
from services.assignment_service import AssignmentService

engine = get_engine()
service = AssignmentService(engine)

# Try listing (should return empty list if no assignments)
assignments = service.list_assignments()
print(f"✅ Service working - found {len(assignments)} assignments")
```

### 3. UI Test
- Run your app: `streamlit run app_weekly_planner.py`
- Navigate to "📝 Assignments" in sidebar
- Should see context selector and subject dropdown

## 🎨 Customization Options

### Modify Colors/Theme
In each UI file (assignment_list.py, assignment_editor.py, etc.), you can customize:

```python
# Status badges
status_colors = {
    "draft": "🟡",
    "published": "🟢",
    "archived": "⚪",
    "deactivated": "🔴"
}

# Modify to match your theme
```

### Add Your Logo/Branding
```python
# In assignments1.py, top of render_assignments_page()
st.image("path/to/your/logo.png", width=200)
st.title("📝 Assignment Management")
```

### Modify Permissions
```python
# In assignment_service.py, modify role checks
def can_publish(user_role):
    return user_role in ['principal', 'director', 'your_custom_role']
```

## 🔒 Security Considerations

### User Authentication
You'll need to integrate your auth system:

```python
# Replace 'current_user' placeholders with actual user ID
actor = st.session_state.get('user_id', 'guest')
actor_role = st.session_state.get('user_role', 'viewer')

# Pass to service methods
service.create_assignment(..., actor=actor, actor_role=actor_role)
```

### Role-Based Access
```python
# Add permission checks
from your_auth_module import check_permission

if not check_permission(user_role, 'assignments.create'):
    st.error("You don't have permission to create assignments")
    return
```

## 📦 Required Packages

Add to your requirements.txt if not already present:

```txt
streamlit>=1.28.0
pandas>=2.0.0
sqlalchemy>=2.0.0
```

## 🐛 Troubleshooting

### Issue: Import Errors
**Solution**: Ensure all __init__.py files are present:
```bash
touch app23/services/__init__.py
touch app23/screens/__init__.py
touch app23/screens/timetable/__init__.py
touch app23/schemas/__init__.py
```

### Issue: Context Not Found
**Solution**: Make sure main page sets context before navigating:
```python
# In main page, before showing navigation
if not get_context().get('degree_code'):
    st.warning("Please select context filters first")
    # Show context selectors
    return
```

### Issue: Foreign Key Violations
**Solution**: Verify parent tables exist:
```sql
-- Check required tables
SELECT name FROM sqlite_master WHERE type='table' AND name IN 
    ('subject_offerings', 'academic_years', 'degrees');
```

### Issue: Service Not Found
**Solution**: Check import paths:
```python
# Use absolute imports
from services.assignment_service import AssignmentService

# Not relative imports
from .services.assignment_service import AssignmentService
```

## 🔄 Migration from Hardcoded to Database

If you currently have hardcoded assignments, here's how to migrate:

```python
from services.assignment_service import AssignmentService
from datetime import datetime, timedelta

engine = get_engine()
service = AssignmentService(engine)

# Example: Migrate hardcoded assignments
hardcoded_assignments = [
    {
        "number": 1,
        "title": "Quiz 1",
        "bucket": "Internal",
        "max_marks": 10,
        "due_days": 7,
    },
    # ... more assignments
]

for asg in hardcoded_assignments:
    try:
        assignment_id = service.create_assignment(
            offering_id=your_offering_id,
            number=asg["number"],
            title=asg["title"],
            bucket=asg["bucket"],
            max_marks=asg["max_marks"],
            due_at=datetime.now() + timedelta(days=asg["due_days"]),
            actor="migration_script",
            actor_role="superadmin"
        )
        print(f"✅ Migrated: {asg['title']}")
    except Exception as e:
        print(f"❌ Failed to migrate {asg['title']}: {e}")
```

## 📞 Next Steps After Integration

1. **Test Schema**: Run schema installation script
2. **Test Service**: Create a test assignment programmatically
3. **Test UI**: Open assignment screen in browser
4. **Create Sample Data**: Add a few test assignments
5. **Test Workflow**: Try draft → publish → archive flow
6. **Test Marks Entry**: Enter sample marks and verify scaling
7. **Review Audit**: Check assignments_audit table for logged actions

## 🎯 Quick Start Guide for Users

Once integrated, share this with your users:

### For Faculty (Subject In-Charge):
1. Navigate to "📝 Assignments" from sidebar
2. Select your subject from dropdown
3. Go to "Create/Edit" tab
4. Fill in the 7-tab form:
   - Basic info (title, marks, due date)
   - CO mappings
   - Submission settings
   - Late policy
   - (other tabs as needed)
5. Click "Save as Draft"
6. Review in "Assignments List" tab
7. Click "Publish" when ready (requires PD approval)

### For Students (Future):
1. View assignments in "Visible_Accepting" state
2. Upload submissions
3. Check deadline and late policy
4. Request extensions if needed
5. View results when published

---

## 📚 Additional Resources

- **YAML Spec**: `slide25_AY_Assignments.txt` - Full specification
- **Schema Docs**: `assignments_schema.py` - All table definitions
- **Service API**: `assignment_service.py` - All available methods
- **UI Examples**: `screens/timetable/assignment_*.py` - UI patterns

---

**Integration Checklist**:
- [ ] Copy all files to project
- [ ] Install schema
- [ ] Add to navigation
- [ ] Update __init__.py files
- [ ] Test schema installation
- [ ] Test service layer
- [ ] Test UI in browser
- [ ] Create sample data
- [ ] Integrate authentication
- [ ] Add permission checks
- [ ] Deploy to production

**Estimated Integration Time**: 2-4 hours for basic integration, 1-2 days for full customization
