

from classes import ClassInfo, Section, Teacher 
from scheduler import generate_schedule, diagnose_infeasibility

# ---------------------------------------------------------------------------
# Dummy data
# ---------------------------------------------------------------------------

# --- Classes -----------------------------------------------------------
# Mix of 1-partial, 2-partial, and full-semester classes
classes = [
    ClassInfo(id="DATABASES",  hours_per_week=3, partials={1, 2, 3},  load=3.0, name="Databases"),
    ClassInfo(id="ALGORITHMS", hours_per_week=3, partials={1, 2, 3},  load=3.0, name="Data Structures and Algorithsm"),
    ClassInfo(id="ETHICS",     hours_per_week=2, partials={1},        load=2.0, name="Ethics and Engineering"),
    ClassInfo(id="WEBDEV",     hours_per_week=2, partials={2, 3},     load=2.0, name="Web Development Torment"),
    ClassInfo(id="CALC1",      hours_per_week=4, partials={1, 2, 3},  load=4.0, name="Basic Calculus"),
    ClassInfo(id="PE",         hours_per_week=1, partials={2},        load=1.0, name="Pizza Eagles"),
]

# --- Teachers ------------------------------------------------------------
# Availability as (day, period) tuples. Days 0-4 = Mon-Fri, periods 0-3 = time slots.
# Some teachers have limited hours (simulating a second job).
teachers = [
    Teacher(
        id="T1_ana",
        name="Ana",
        can_teach={"DATABASES", "ALGORITHMS", "WEBDEV"},
        availability=[(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)],
        max_load_per_partial=6.0,
        max_load_total=15.0,
    ),
    Teacher(
        id="T2_luis",
        name="Luis",
        can_teach={"ALGORITHMS", "CALC1"},
        # Only free mornings (period 0) -- simulates afternoon outside job
        availability=[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],
        max_load_per_partial=4.0,
        max_load_total=10.0,
    ),
    Teacher(
        id="T3_maria",
        name="Maria",
        can_teach={"ETHICS", "WEBDEV", "PE"},
        availability=[(0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (4, 1)],
        max_load_per_partial=5.0,
        max_load_total=12.0,
    ),
    Teacher(
        id="T4_carlos",
        name="Carlos",
        can_teach={"DATABASES", "CALC1", "PE"},
        availability=[(0, 2), (0, 3), (1, 2), (1, 3), (2, 2), (2, 3), (3, 2), (3, 3), (4, 2), (4, 3)],
        max_load_per_partial=8.0,
        max_load_total=30.0
    ),  
    Teacher(
        id="T5_susana",
        name="Susana",
        can_teach={"CALC1"},
        availability=[(0, 2), (0, 3), (1, 2), (1, 3), (2, 2), (2, 3), (3, 2), (3, 3), (4, 2), (4, 3)],
        max_load_per_partial=7.0,
        max_load_total=16.0,
    )
]

# --- Sections --------------------------------------------------------------
# Derived as if from mayor.json: (mayor, semester, class, group_number)
sections = [
    # Software Engineering, semester 3 -- needs 2 groups of Databases
    Section(id="SE-3-DATABASES-g1", mayor="SE", semester=3, class_id="DATABASES", group_number=1, partials={1, 2, 3}),
    Section(id="SE-3-DATABASES-g2", mayor="SE", semester=3, class_id="DATABASES", group_number=2, partials={1, 2, 3}),
    Section(id="SE-3-ALGORITHMS-g1", mayor="SE", semester=3, class_id="ALGORITHMS", group_number=1, partials={1, 2, 3}),
    Section(id="SE-3-ETHICS-g1", mayor="SE", semester=3, class_id="ETHICS", group_number=1, partials={1}),

    # Software Engineering, semester 1 -- different cohort, shares teacher pool
    Section(id="SE-1-CALC1-g1", mayor="SE", semester=1, class_id="CALC1", group_number=1, partials={1, 2, 3}),
    Section(id="SE-1-WEBDEV-g1", mayor="SE", semester=1, class_id="WEBDEV", group_number=1, partials={2, 3}),
    Section(id="SE-1-PE-g1", mayor="SE", semester=1, class_id="PE", group_number=1, partials={2}),

    # Business Admin, semester 2 -- separate mayor entirely
    Section(id="BA-2-ETHICS-g1", mayor="BA", semester=2, class_id="ETHICS", group_number=1, partials={1}),
    Section(id="BA-2-CALC1-g1", mayor="BA", semester=2, class_id="CALC1", group_number=1, partials={1, 2, 3}),
]


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = generate_schedule(sections, classes, teachers, max_time_in_seconds=1000)

    print("Status:", result["status"])
    print()

    if result["status"] == "INFEASIBLE":
        diagnose_infeasibility(sections, classes, teachers)

    if result["status"] in ("OPTIMAL", "FEASIBLE"):
        print("=== Schedule by section ===")
        for sid, info in result["by_section"].items():
            print(f"{sid:25s} -> teacher {info['teacher']:10s} slots {info['slots']}")

        print()
        print("=== Schedule by teacher ===")
        for tid, entries in result["by_teacher"].items():
            print(f"{tid}:")
            for sid, day, period in sorted(entries, key=lambda x: (x[1], x[2])):
                print(f"    day {day}, period {period} -> {sid}")
    else:
        print("No feasible schedule found with current constraints.")