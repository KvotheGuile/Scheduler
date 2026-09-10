
import json
from classes import ClassInfo, Teacher, Section, Room
from collections import defaultdict
import hashlib

def readJson(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file)

    return data

# ----------------------------------
# MAIN FUNCTIONS
# ----------------------------------

# CLASSES
def getClassesInfo(filename: str) -> list[ClassInfo]:
    data = readJson(filename)
    classes = []
    for class_data in data:
        class_info = ClassInfo(
            id=class_data["id"],
            name=class_data["name"],
            partials=calculatePartials(class_data["partials"]),
            load=class_data["load"],
            sessions_per_week=class_data["sessions_per_week"],
            duration_minutes=class_data["duration_minutes"],
        )
        classes.append(class_info)
    return classes

# TEACHERS
def getTeachers(filename: str) -> list[Teacher]:
    data = readJson(filename)
    teachers = []

    for teacher_data in data:
        teacher = Teacher(
            id=teacher_data["id"],
            name=teacher_data["name"],
            can_teach=teacher_data["can_teach"],
            availability=getAvailability(teacher_data["availability"]),
            max_load_per_partial=teacher_data["max_load_total"],
            max_load_total=teacher_data["max_load_total"] * 3
        )
        teachers.append(teacher)
    return teachers

# SECTIONS
def getSections(filename: str) -> list[Section]:
    data = readJson(filename)
    sections = []

    for section_data in data:
        for group_number in range(1, section_data["cantidad_grupos"] + 1):
            section_name = (
                f"{section_data['major']}-"
                f"{section_data['semester']}-"
                f"{section_data['class_id']}-"
                f"{group_number}"
            )
            section = Section(
                id=section_name,
                major=section_data["major"],
                semester=section_data["semester"],
                class_id=section_data["class_id"],
                group_number=group_number,
                partials=calculatePartials(section_data["partials"])
            )
            sections.append(section)
    return sections

# ROOMS
def getRooms(filename: str) -> list[Room]:
    data = readJson(filename)
    rooms = []
    for room_data in data:
        room = Room(
            id=room_data["id"],
            building=room_data["building"]
        )
        rooms.append(room)
    return rooms


# ----------------------------------
# HELPER FUNCTIONS
# ----------------------------------

# GENERATE SECTION ID
def generateId(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

# MAP PARTIALS
def calculatePartials(partials: list[int]) -> set[int]:
    partial_map = {
        1: {1},
        2: {2},
        3: {3},
        4: {1, 2},
        5: {2, 3},
        6: {1, 2, 3}
    }
    return partial_map.get(partials[0], set())

# GET TEACHER AVAILABILITY
DAY_START_HOUR = 7

def time_range_to_blocks(start_hour, start_min, end_hour, end_min):
    start_block = (start_hour - DAY_START_HOUR) * 2 + (start_min // 30)
    end_block = (end_hour - DAY_START_HOUR) * 2 + (end_min // 30)
    return list(range(start_block, end_block))

def daily_availability(day, start_time, end_time):
    start_hour, start_min = map(int, start_time.split(":"))
    end_hour, end_min = map(int, end_time.split(":"))

    blocks = time_range_to_blocks(start_hour, start_min, end_hour, end_min)
    return [(day, block) for block in blocks]

def getAvailability(availability: list[list]) -> list[tuple]:
    result = []
    day_map = {
        "Lu": 0,
        "Ma": 1,
        "Mi": 2,
        "Ju": 3,
        "Vi": 4,
        "Sa": 5,
        "Do": 6
    }
    for day, start_time, end_time in availability:
        day_number = day_map[day]
        dailyav = daily_availability(
            day_number,
            start_time,
            end_time
        )
        result.extend(dailyav)

    return result