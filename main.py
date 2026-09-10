
import time
from classes import ClassInfo, Section, Teacher 
from scheduler import generate_schedule, verify_schedule, verify_group_conflicts, verify_same_hour
from outputSchedule import jsonOutput


DAY_START_HOUR = 7

def time_range_to_blocks(start_hour, start_min, end_hour, end_min):
    """Helper: convert a human time range into a list of block indices."""
    start_block = (start_hour - DAY_START_HOUR) * 2 + (start_min // 30)
    end_block = (end_hour - DAY_START_HOUR) * 2 + (end_min // 30)
    return list(range(start_block, end_block))


# --- Classes -----------------------------------------------------------
classes = [
    ClassInfo(id="DATABASES",  duration_minutes=120, sessions_per_week=4, partials={2, 3},    load=3.0, name="Databases Engineering"),
    ClassInfo(id="ALGORITHMS", duration_minutes=120, sessions_per_week=3, partials={1, 2, 3}, load=3.0, name="Algorithms and Data Structures"),
    ClassInfo(id="ETHICS",     duration_minutes= 90, sessions_per_week=2, partials={1},       load=2.0, name="Ethics"),
    ClassInfo(id="WEBDEV",     duration_minutes= 90, sessions_per_week=2, partials={2, 3},    load=2.0, name="Web Development"),
    ClassInfo(id="CALC1",      duration_minutes=120, sessions_per_week=3, partials={1, 2, 3}, load=4.0, name="Calculus I"),
    ClassInfo(id="PE",         duration_minutes= 90, sessions_per_week=1, partials={2},       load=1.0, name="Pheasant Eagle"),
    ClassInfo(id="M0125",      duration_minutes=120, sessions_per_week=3, partials={1, 2}, load=1,   name="Math"),
    ClassInfo(id="B0361",      duration_minutes=120, sessions_per_week=3, partials={1, 2}, load=1,   name="Physics"),
    ClassInfo(id="M0404",      duration_minutes=120, sessions_per_week=5, partials={3},    load=1,   name="Chem")
]

# --- Teachers ------------------------------------------------------------
def daily_availability(days, start_h, start_m, end_h, end_m):
    """Same time window on each listed day."""
    blocks = time_range_to_blocks(start_h, start_m, end_h, end_m)
    return [(d, b) for d in days for b in blocks]


teachers = [
    Teacher(
        id="L0125",
        name="Ana",
        can_teach={"DATABASES", "ALGORITHMS", "WEBDEV", "M0125", "B0361"},
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 11, 0),
        max_load_per_partial=6.0,
        max_load_total=15.0,
    ),
    Teacher(
        id="L0613",
        name="Luis",
        can_teach={"ALGORITHMS", "CALC1", "M0125", "B0361"},
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 21, 0),
        max_load_per_partial=4.0,
        max_load_total=10.0,
    ),
    Teacher(
        id="L0999",
        name="Samatha",
        can_teach={"ALGORITHMS", "CALC1", "M0125", "B0361"},
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 21, 0),
        max_load_per_partial=4.0,
        max_load_total=10.0,
    ),
    Teacher(
        id="L0456",
        name="Leonor",
        can_teach={"ALGORITHMS", "CALC1", "M0404", "M0125", "B0361"},
        availability=daily_availability([0, 1, 2, 3, 4], 7, 0, 21, 0),
        max_load_per_partial=2,
        max_load_total=2,
    ),
]

# --- Sections --------------------------------------------------------------
sections = [
    Section(id="A1", major="SE", semester=3, class_id="M0125", group_number=1, partials={1, 2}),
    Section(id="A2", major="SE", semester=3, class_id="M0125", group_number=2, partials={1, 2}),
    Section(id="B1", major="SE", semester=3, class_id="B0361", group_number=1, partials={1, 2}),
    Section(id="B2", major="SE", semester=3, class_id="B0361", group_number=2, partials={1, 2}),
    Section(id="C1", major="SE", semester=3, class_id="M0404", group_number=1, partials={3}),
    Section(id="C2", major="SE", semester=3, class_id="M0404", group_number=2, partials={3})
]

classrooms = [
    "PEI 301",
    "PEI 302"
]

if __name__ == "__main__":


    start_time = time.perf_counter()
    result_time = 0
    verification_time = 0
    end_time = 0

    # ---------------
    # Running Model 
    # ---------------
    result = generate_schedule(
        sections, 
        classes, 
        teachers,
        classrooms,
        w_group_balance=5,
        w_group_gaps=15,
        w_days_used=0,
        w_teacher_gaps=8,
        w_teacher_load_imbalance=1,
        w_undesirable_time=10,
        undesirable_start_blocks=set([1 + 2 * (i//2) for i in range(28)]) | set(range(20, 28)),
        max_time_in_seconds=60000.0
        )

    result_time = time.perf_counter()

    # ---------------
    # Issues 
    # ---------------
    issues = [] 
    issues.extend(verify_schedule(result, sections, classes))
    issues.extend(verify_group_conflicts(result, sections, classes))
    issues.extend(verify_same_hour(result, sections, classes))

    verification_time = time.perf_counter()

    if issues:
        print("SCHEDULE INVALID:")
        for i in issues:
            print(" -", i)
    else:
        print("Schedule verified clean.")

    
    # ---------------
    # Printed Output
    # ---------------
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

        print()
        jsonOutput(result["schedule"])
    else:
        print("No feasible schedule found with current constraints.")

    end_time = time.perf_counter()

    print(f"\nScheduler run time: {int(result_time - start_time)}s")
    print(f"Verification run time: {int(verification_time - result_time)}s")
    print(f"Output run time: {int(end_time - verification_time)}s")
    print(f"Total run time: {int(end_time - start_time)}s")
    