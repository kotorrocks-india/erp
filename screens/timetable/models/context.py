"""
Context Model - Filter context for the application
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Context:
    """Filter context for the application"""
    ay: str
    degree: str
    program: Optional[str]
    branch: Optional[str]
    year: int
    term: int
    division: Optional[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for SQL params"""
        return {
            'ay': self.ay,
            'deg': self.degree,
            'prog': self.program,
            'branch': self.branch,
            'yr': self.year,
            'term': self.term,
            'div': self.division
        }
    
    def __str__(self) -> str:
        """Human-readable representation"""
        parts = [
            f"{self.degree}",
            f"Y{self.year}T{self.term}",
        ]
        if self.program:
            parts.insert(1, f"{self.program}")
        if self.branch:
            parts.insert(2 if self.program else 1, f"{self.branch}")
        if self.division:
            parts.append(f"Div {self.division}")
        return " / ".join(parts)
    
    @property
    def has_division(self) -> bool:
        """Check if division is specified"""
        return self.division is not None and self.division != ""
