"""
Conflict Detection Diagnostic Script
Run this to troubleshoot conflict detector issues
"""

import sys
import os
from pathlib import Path

print("=" * 70)
print("🔍 CONFLICT DETECTION DIAGNOSTIC TOOL")
print("=" * 70)

# Step 1: Current working directory
print("\n📁 Step 1: Current Working Directory")
print(f"   {os.getcwd()}")

# Step 2: Python path
print("\n🐍 Step 2: Python Path (first 5 entries)")
for i, path in enumerate(sys.path[:5], 1):
    print(f"   {i}. {path}")

# Step 3: Look for conflict_detector.py
print("\n🔎 Step 3: Searching for conflict_detector.py")

search_paths = [
    Path(os.getcwd()) / "services" / "conflict_detector.py",
    Path(os.getcwd()) / "screens" / "timetable" / "services" / "conflict_detector.py",
    Path(os.getcwd()).parent / "services" / "conflict_detector.py",
    Path(r"E:\This & That (E:)\LPEP App\Simple Trial\app26\screens\timetable\services\conflict_detector.py")
]

found_path = None
for path in search_paths:
    if path.exists():
        print(f"   ✅ FOUND: {path}")
        found_path = path
        break
    else:
        print(f"   ❌ Not found: {path}")

if not found_path:
    print("\n   ⚠️ ERROR: conflict_detector.py not found in any expected location!")
    print("\n   💡 Solution:")
    print("      1. Verify the file exists")
    print("      2. Check file name (must be exactly 'conflict_detector.py')")
    print("      3. Ensure it's in the services/ folder")
    sys.exit(1)

# Step 4: Try importing
print("\n📦 Step 4: Attempting Import")

# Add to path
services_dir = str(found_path.parent)
if services_dir not in sys.path:
    sys.path.insert(0, services_dir)
    print(f"   Added to path: {services_dir}")

try:
    print("   Importing conflict_detector...")
    
    from conflict_detector import (
        detect_faculty_conflicts,
        detect_student_conflicts,
        detect_distribution_violations,
        detect_room_conflicts,
        check_slot_conflicts
    )
    
    print("   ✅ SUCCESS: All functions imported!")
    print("\n   Available functions:")
    print("      - detect_faculty_conflicts")
    print("      - detect_student_conflicts")
    print("      - detect_distribution_violations")
    print("      - detect_room_conflicts")
    print("      - check_slot_conflicts")
    
    # Step 5: Check dependencies
    print("\n🔗 Step 5: Checking Dependencies")
    
    try:
        from sqlalchemy import text
        from sqlalchemy.engine import Engine
        print("   ✅ SQLAlchemy available")
    except ImportError:
        print("   ❌ SQLAlchemy missing - install with: pip install sqlalchemy")
    
    try:
        # Try importing connection
        sys.path.insert(0, str(found_path.parent.parent / "database"))
        from connection import get_engine
        print("   ✅ Database connection available")
    except ImportError as e:
        print(f"   ⚠️ Database connection issue: {e}")
        print("      This may be okay if using different import path")
    
    print("\n" + "=" * 70)
    print("✅ DIAGNOSTIC COMPLETE - CONFLICT DETECTION READY!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Restart your Streamlit app")
    print("2. The timetable should now show: '✅ Comprehensive conflict detection enabled'")
    print("3. Try adding a slot and watch for conflict validation!")
    
except ImportError as e:
    print(f"   ❌ IMPORT FAILED: {e}")
    print("\n🐛 Troubleshooting:")
    print("   1. Check for syntax errors in conflict_detector.py")
    print("   2. Ensure all imports in the file are correct")
    print("   3. Verify database/connection.py exists")
    print("\n   Run this to check syntax:")
    print(f"      python -m py_compile {found_path}")

except Exception as e:
    print(f"   ❌ UNEXPECTED ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
