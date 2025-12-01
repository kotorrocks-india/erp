"""
Assignment Management System
Comprehensive assignment management with CO mapping, rubrics, and marks scaling.
"""

__version__ = "1.1.0"
__author__ = "LPEP Development Team"

# Main entry point
from .assignments_main import render_assignments_page

__all__ = ['render_assignments_page']
