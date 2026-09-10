
import time
from classes import ClassInfo, Section, Teacher 
from readFile import getClassesInfo, getRooms, getSections, getTeachers
from scheduler import generate_schedule, verify_schedule, verify_group_conflicts, verify_same_hour, pre_solve_sanity_checks, diagnose_infeasibility
from outputSchedule import jsonOutput


DAY_START_HOUR = 7

def time_range_to_blocks(start_hour, start_min, end_hour, end_min):
    """Helper: convert a human time range into a list of block indices."""
    start_block = (start_hour - DAY_START_HOUR) * 2 + (start_min // 30)
    end_block = (end_hour - DAY_START_HOUR) * 2 + (end_min // 30)
    return list(range(start_block, end_block))


# --- Teachers ------------------------------------------------------------
def daily_availability(days, start_h, start_m, end_h, end_m):
    """Same time window on each listed day."""
    blocks = time_range_to_blocks(start_h, start_m, end_h, end_m)
    return [(d, b) for d in days for b in blocks]


if __name__ == "__main__":


    # ---------------
    # Time checks
    # ---------------

    start_time = time.perf_counter()
    pre_check_time = 0
    result_time = 0
    verification_time = 0
    end_time = 0

    # ---------------
    # Reading files & object parsing
    # ---------------
    teachers = getTeachers("input/profesores.json")
    classes = getClassesInfo("input/materias.json")
    sections = getSections("input/carreras.json")
    classrooms = [ (f"{room.building} {room.id}") for room in getRooms("input/aulas.json")]    

    # ---------------
    # Pre-verify Model
    # ---------------

    pre_issues = []
    pre_issues = pre_solve_sanity_checks(sections, classes, teachers, len(classrooms))
    if pre_issues:
        print("Pre Solve check:")
        for i in pre_issues:
            print("- ", i)
        raise ValueError
    else:
        print("Pre-solve check passed")
        diagnose_infeasibility(sections, classes, teachers)
        

    pre_check_time = time.perf_counter()

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
        w_teacher_gaps=9,
        w_teacher_load_imbalance=3,
        w_undesirable_time=20,
        undesirable_start_blocks=set([1 + 2 * (i//2) for i in range(28)]) | set(range(20, 28)),
        max_time_in_seconds=3000.0,
        relative_gap_limit=0.1
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

    print(f"\nPre check run time: {int(pre_check_time - start_time)}s")
    print(f"Scheduler run time: {int(result_time - pre_check_time)}s")
    print(f"Verification run time: {int(verification_time - result_time)}s")
    print(f"Output run time: {int(end_time - verification_time)}s")
    print(f"Total run time: {int(end_time - start_time)}s")
    