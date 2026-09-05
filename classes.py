
from dataclasses import dataclass

@dataclass
class Section:
    id: str
    mayor: str
    semester: int
    class_id: str
    group_number: int
    partials: set[int]   

@dataclass
class ClassInfo:
    id: str
    name: str
    hours_per_week: int
    partials: set[int]      # e.g. {1}, {2,3}, {1,2,3}
    load: float             # load contributed per partial this class is taught

@dataclass
class Teacher:
    id: str
    name: str
    can_teach: list[str]
    max_load_per_partial: float
    max_load_total: float
    availability: list[tuple]  
