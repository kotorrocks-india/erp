# ui/__init__.py
"""
UI Package
"""

from .components import UIComponents
from .distribution_tab import DistributionTab
# --- FIX: Updated import to match filename ---
from .timetable_tab_integrated import TimetableTabIntegrated as TimetableTab
from .operations_tab import OperationsTab

__all__ = [
    'UIComponents',
    'DistributionTab',
    'TimetableTab',
    'OperationsTab',
]
