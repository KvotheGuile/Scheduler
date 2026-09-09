
from dataclasses import dataclass

@dataclass
class Section:
    id: str
    major: str
    semester: int
    class_id: str
    group_number: int
    partials: set[int]   

@dataclass
class ClassInfo:
    id: str
    name: str
    partials: set[int]      # e.g. {1}, {2,3}, {1,2,3}
    load: float            
    sessions_per_week: int 
    duration_minutes: int   # e.g. 120 or 90

@dataclass
class Teacher:
    id: str
    name: str
    can_teach: list[str]
    max_load_per_partial: float
    max_load_total: float
    availability: list[tuple]  
