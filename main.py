

from classes import ClassInfo, Section, Teacher 
from scheduler import generate_schedule, verify_schedule
# ---------------------------------------------------------------------------
# Dummy data (30-minute block grid: block 0 = 7:00am ... block 27 = 8:30pm)
# ---------------------------------------------------------------------------

DAY_START_HOUR = 7

def time_range_to_blocks(start_hour, start_min, end_hour, end_min):
    """Helper: convert a human time range into a list of block indices."""
    start_block = (start_hour - DAY_START_HOUR) * 2 + (start_min // 30)
    end_block = (end_hour - DAY_START_HOUR) * 2 + (end_min // 30)
    return list(range(start_block, end_block))


# --- Classes -----------------------------------------------------------
# Mix of 90-min and 120-min durations, various sessions/week, various partial spans
classes = [
    ClassInfo(id="DATABASES",  duration_minutes=120, sessions_per_week=4, partials={2, 3}, load=3.0,  name="Databases Engineering"),
    ClassInfo(id="ALGORITHMS", duration_minutes=120, sessions_per_week=3, partials={1, 2, 3}, load=3.0,  name="Algorithms and Data Structures"),
    ClassInfo(id="ETHICS",     duration_minutes=90,  sessions_per_week=2, partials={1},        load=2.0, name="Ethics"),
    ClassInfo(id="WEBDEV",     duration_minutes=90,  sessions_per_week=2, partials={2, 3},     load=2.0, name="Web Development"),
    ClassInfo(id="CALC1",      duration_minutes=120, sessions_per_week=3, partials={1, 2, 3}, load=4.0,  name="Calculus I"),
    ClassInfo(id="PE",         duration_minutes=90,  sessions_per_week=1, partials={2},        load=1.0, name="Pheasant Eagle"),
]

# --- Teachers ------------------------------------------------------------
# Availability expressed as (day, block) tuples, days 0-4 = Mon-Fri.
# Built via time_range_to_blocks(start_h, start_m, end_h, end_m) per day.

def daily_availability(days, start_h, start_m, end_h, end_m):
    """Same time window on each listed day."""
    blocks = time_range_to_blocks(start_h, start_m, end_h, end_m)
    return [(d, b) for d in days for b in blocks]


teachers = [
    Teacher(
        id="T1_ana",
        name="Ana",
        can_teach={"DATABASES", "ALGORITHMS", "WEBDEV"},
        # Free 8am-2pm, Mon-Thu
        availability=daily_availability([0, 1, 2, 3], 8, 0, 14, 0),
        max_load_per_partial=6.0,
        max_load_total=15.0,
    ),
    Teacher(
        id="T2_luis",
        name="Luis",
        can_teach={"ALGORITHMS", "CALC1"},
        # Only free mornings 7-11am, all weekdays -- simulates afternoon outside job
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 11, 0),
        max_load_per_partial=4.0,
        max_load_total=10.0,
    ),
    Teacher(
        id="T3_maria",
        name="Maria",
        can_teach={"ETHICS", "WEBDEV", "PE"},
        # Free 9am-1pm and 5-7pm, Mon/Wed/Fri
        availability=(
            daily_availability([0, 2, 4], 9, 0, 13, 0)
            + daily_availability([0, 2, 4], 17, 0, 19, 0)
        ),
        max_load_per_partial=5.0,
        max_load_total=12.0,
    ),
    Teacher(
        id="T4_carlos",
        name="Carlos",
        can_teach={"DATABASES", "CALC1", "PE"},
        # Free all day, all weekdays -- most flexible teacher
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 20, 0),
        max_load_per_partial=8.0,
        max_load_total=30.0,
    ),
    Teacher(
        id="T5_samantha",
        name="Samantha",
        can_teach={"DATABASES", "CALC1", "PE", "WEBDEV"},
        # Free all day, all weekdays -- most flexible teacher
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 11, 0),
        max_load_per_partial=12.0,
        max_load_total=30.0,
    ),
]

# --- Sections --------------------------------------------------------------
sections = [
    # Software Engineering, semester 3 -- needs 2 groups of Databases
    Section(id="SE-3-DATABASES-g1", major="SE", semester=3, class_id="DATABASES", group_number=1, partials={1, 2, 3}),
    Section(id="SE-3-DATABASES-g2", major="SE", semester=3, class_id="DATABASES", group_number=2, partials={1, 2, 3}),
    Section(id="SE-3-ALGORITHMS-g1", major="SE", semester=3, class_id="ALGORITHMS", group_number=1, partials={1, 2, 3}),
    Section(id="SE-3-ETHICS-g1", major="SE", semester=3, class_id="ETHICS", group_number=1, partials={1}),

    # Software Engineering, semester 1 -- different cohort
    Section(id="SE-1-CALC1-g1", major="SE", semester=1, class_id="CALC1", group_number=1, partials={1, 2, 3}),
    Section(id="SE-1-WEBDEV-g1", major="SE", semester=1, class_id="WEBDEV", group_number=1, partials={2, 3}),
    Section(id="SE-1-PE-g1", major="SE", semester=1, class_id="PE", group_number=1, partials={2}),

    # Business Admin, semester 2 -- separate major
    Section(id="BA-2-ETHICS-g1", major="BA", semester=2, class_id="ETHICS", group_number=1, partials={1}),
    Section(id="BA-2-CALC1-g1", major="BA", semester=2, class_id="CALC1", group_number=1, partials={1, 2, 3}),
]


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    result = generate_schedule(sections, classes, teachers)
    conflicts = verify_schedule(result, sections, classes)

    if conflicts:
        print("SCHEDULE INVALID:")
        for c in conflicts:
            print(" -", c)
    else:
        print("Schedule verified clean.")

    print("\nStatus:", result["status"])
    print()

    if result["status"] in ("OPTIMAL", "FEASIBLE"):
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

        print("=== Schedule by section ===")
        for sid, info in result["by_section"].items():
            print(f"{sid} -> teacher {info['teacher']}")
            for sess in info["sessions"]:
                print(f"    {day_names[sess['day']]} {sess['start_time']}-{sess['end_time']}")

        print()
        print("=== Schedule by teacher ===")
        for tid, entries in result["by_teacher"].items():
            print(f"{tid}:")
            for e in sorted(entries, key=lambda x: (x["day"], x["start_time"])):
                print(f"    {day_names[e['day']]} {e['start_time']}-{e['end_time']} -> {e['section']}")
    else:
        print("No feasible schedule found with current constraints.")