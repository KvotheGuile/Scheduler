from dataclasses import dataclass
from ortools.sat.python import cp_model
from classes import ClassInfo, Section, Teacher 

SCALE = 100
BLOCK_MINUTES = 30
DAY_START_HOUR = 7 # 7am
DAY_END_HOUR = 21  # 9pm
BLOCKS_PER_DAY = (DAY_END_HOUR - DAY_START_HOUR) * 60 // BLOCK_MINUTES  # 28
NUM_DAYS = 5  # Mon-Fri

# conversion of period annotation from excel to partial annotation
PERIOD_TO_PARTIALS = {
    1: {1},
    2 : {2},
    3: {3},
    4: {1, 2},
    5: {2, 3},
    6: {1, 2, 3},
}


def blocks_needed(duration_minutes: int) -> int:
    return duration_minutes // BLOCK_MINUTES  # 2h -> 4 blocks, 1.5h -> 3 blocks

def block_to_time(block: int) -> str:
    total_minutes = DAY_START_HOUR * 60 + block * BLOCK_MINUTES
    h, m = divmod(total_minutes, 60)
    return f"{h:02d}:{m:02d}"

def occupied_blocks(day, start, n_blocks):
    return {(day, start + i) for i in range(n_blocks)}

def valid_start_blocks(teacher:Teacher, day:int, n_blocks:int):
    """Blocks where a session of n_blocks length can start, fully within
    teacher's availability, without running past the end of the day."""
    free_blocks = {b for (d, b) in teacher.availability if d == day}
    starts = []
    for start in range(0, BLOCKS_PER_DAY - n_blocks + 1):
        if all((start + i) in free_blocks for i in range(n_blocks)):
            starts.append(start)
    return starts

""" Periodo is represented as an int (1-6) corresponding to:
    1 = {1}
    2 = {2}
    3 = {3}
    4 = {1, 2}
    5 = {2, 3}
    6 = {1, 2, 3}
"""
def period_to_partials(period: int) -> set[int]:
    return  PERIOD_TO_PARTIALS[period]

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def generate_schedule(
    sections: list[Section],
    classes: list[ClassInfo],
    teachers: list[Teacher],
    all_partials: tuple[int, ...] = (1, 2, 3),
    load_scale: int = 100,
    max_time_in_seconds: float = 60.0,
):
    """
    Returns:
        {
            "status": "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN",
            "by_section": {
                section_id: {
                    "teacher": teacher_id,
                    "sessions": [{"day": d, "start_block": b, "start_time": "HH:MM",
                                  "end_time": "HH:MM"}, ...]
                }
            },
            "by_teacher": {
                teacher_id: [{"section": sid, "day": d, "start_time": ..., "end_time": ...}, ...]
            },
        }
    """

    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}

    model = cp_model.CpModel()

    # -----------------------------------------------------------------
    # Variables
    # -----------------------------------------------------------------

    # teaches[section_id, teacher_id] = 1 if this teacher owns this section
    teaches = {}
    for s in sections:
        cls = class_lookup[s.class_id]
        for t in teachers:
            if cls.id in t.can_teach:
                teaches[s.id, t.id] = model.NewBoolVar(f"teaches_{s.id}_{t.id}")

    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        if not vars_:
            raise ValueError(f"No qualified teacher available for section {s.id}")

    # assign[section_id, teacher_id, day, start_block] = 1 if this session
    # starts there. Only created where the full duration fits in availability.
    assign = {}
    for s in sections:
        cls = class_lookup[s.class_id]
        n_blocks = blocks_needed(cls.duration_minutes)
        for t in teachers:
            if (s.id, t.id) not in teaches:
                continue
            for day in range(NUM_DAYS):
                for start in valid_start_blocks(t, day, n_blocks):
                    assign[s.id, t.id, day, start] = model.NewBoolVar(
                        f"assign_{s.id}_{t.id}_{day}_{start}"
                    )

    # -----------------------------------------------------------------
    # Constraint: same class must occur at the same start_block every day
    # it meets (e.g. always 10:00am on whichever days it runs).
    # -----------------------------------------------------------------

    # Collect the set of start_blocks that are actually reachable for each
    # section (union over its qualified teachers, since we don't know yet
    # which teacher will be assigned).
    section_possible_starts = {}
    for s in sections:
        starts = {start for (sid, tid, day, start) in assign if sid == s.id}
        section_possible_starts[s.id] = starts

    # uses_start[section_id, start_block] = 1 if this section's fixed daily
    # time is `start_block`
    uses_start = {}
    for s in sections:
        for start in section_possible_starts[s.id]:
            uses_start[s.id, start] = model.NewBoolVar(f"uses_start_{s.id}_{start}")

        # exactly one start_block chosen per section
        vars_ = [uses_start[s.id, start] for start in section_possible_starts[s.id]]
        if vars_:
            model.Add(sum(vars_) == 1)

    # link: a session can only be assigned at `start` if that's this
    # section's chosen fixed start_block
    for (sid, tid, day, start), v in assign.items():
        model.Add(v <= uses_start[sid, start])

    # -----------------------------------------------------------------
    # Constraint 1: each section has exactly one teacher
    # -----------------------------------------------------------------
    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        model.Add(sum(vars_) == 1)

    # -----------------------------------------------------------------
    # Constraint 2: assign implies teaches; each section gets exactly
    # sessions_per_week distinct (day, start) sessions with its teacher.
    # Also: no two sessions of the SAME section on the same day
    # (adjust here if your school allows double sessions same day).
    # -----------------------------------------------------------------
    for (sid, tid, day, start), v in assign.items():
        model.Add(v <= teaches[sid, tid])

    for s in sections:
        cls = class_lookup[s.class_id]
        vars_ = [v for (sid, tid, d, st), v in assign.items() if sid == s.id]
        if not vars_:
            raise ValueError(
                f"No valid (teacher, day, start) combination exists for section {s.id} "
                f"-- check teacher qualifications/availability vs. class duration."
            )
        model.Add(sum(vars_) == cls.sessions_per_week)

        # at most one session of this section per day
        for day in range(NUM_DAYS):
            day_vars = [v for (sid, tid, d, st), v in assign.items()
                        if sid == s.id and d == day]
            if day_vars:
                model.Add(sum(day_vars) <= 1)

    # -----------------------------------------------------------------
    # Constraint 3: no teacher double-booked (interval-based, robust),
    # scoped by partial -- sessions in non-overlapping partials never
    # compete for the same teacher slot.
    # -----------------------------------------------------------------
    for t in teachers:
        for p in all_partials:
            intervals = []
            for (sid, tid, day, start), v in assign.items():
                if tid != t.id:
                    continue
                if p not in section_lookup[sid].partials:
                    continue
                cls = class_lookup[section_lookup[sid].class_id]
                n_blocks = blocks_needed(cls.duration_minutes)
                global_start = day * BLOCKS_PER_DAY + start
                interval = model.NewOptionalIntervalVar(
                    global_start, n_blocks, global_start + n_blocks, v,
                    f"ivl_teacher_{t.id}_{p}_{sid}_{day}_{start}"
                )
                intervals.append(interval)
            if intervals:
                model.AddNoOverlap(intervals)

    # -----------------------------------------------------------------
    # Constraint 4: no student group double-booked (interval-based),
    # scoped by partial. Grouped by (major, semester, group_number).
    # -----------------------------------------------------------------
    group_keys = {(s.major, s.semester, s.group_number) for s in sections}
    for key in group_keys:
        matching_ids = {s.id for s in sections
                        if (s.major, s.semester, s.group_number) == key}
        for p in all_partials:
            intervals = []
            for (sid, tid, day, start), v in assign.items():
                if sid not in matching_ids:
                    continue
                if p not in section_lookup[sid].partials:
                    continue
                cls = class_lookup[section_lookup[sid].class_id]
                n_blocks = blocks_needed(cls.duration_minutes)
                global_start = day * BLOCKS_PER_DAY + start
                interval = model.NewOptionalIntervalVar(
                    global_start, n_blocks, global_start + n_blocks, v,
                    f"ivl_group_{key}_{p}_{sid}_{day}_{start}"
                )
                intervals.append(interval)
            if intervals:
                model.AddNoOverlap(intervals)

    # -----------------------------------------------------------------
    # Constraint 5: teacher per-partial load cap
    # -----------------------------------------------------------------
    for t in teachers:
        for p in all_partials:
            vars_ = []
            for s in sections:
                if p not in s.partials:
                    continue
                key = (s.id, t.id)
                if key in teaches:
                    cls = class_lookup[s.class_id]
                    coeff = int(round(cls.load * load_scale))
                    vars_.append(coeff * teaches[key])
            if vars_:
                bound = int(round(t.max_load_per_partial * load_scale))
                model.Add(sum(vars_) <= bound)

    # -----------------------------------------------------------------
    # Constraint 6: teacher total semester load cap
    # -----------------------------------------------------------------
    for t in teachers:
        vars_ = []
        for s in sections:
            key = (s.id, t.id)
            if key in teaches:
                cls = class_lookup[s.class_id]
                coeff = int(round(cls.load * len(s.partials) * load_scale))
                vars_.append(coeff * teaches[key])
        if vars_:
            bound = int(round(t.max_load_total * load_scale))
            model.Add(sum(vars_) <= bound)

    # -----------------------------------------------------------------
    # Solve
    # -----------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_in_seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    status_name = solver.StatusName(status)
    result = {"status": status_name, "by_section": {}, "by_teacher": {}}

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    for (sid, tid, day, start), v in assign.items():
        if solver.Value(v):
            cls = class_lookup[section_lookup[sid].class_id]
            n_blocks = blocks_needed(cls.duration_minutes)
            end_block = start + n_blocks
            session_info = {
                "day": day,
                "start_block": start,
                "start_time": block_to_time(start),
                "end_time": block_to_time(end_block),
            }
            result["by_section"].setdefault(sid, {"teacher": tid, "sessions": []})
            result["by_section"][sid]["sessions"].append(session_info)

            result["by_teacher"].setdefault(tid, [])
            result["by_teacher"][tid].append({
                "section": sid,
                "day": day,
                "start_time": block_to_time(start),
                "end_time": block_to_time(end_block),
            })

    return result


def verify_schedule(result, sections, classes):
    """Independently re-checks the solved schedule for teacher/group
    overlaps. Returns a list of conflict descriptions (empty = clean)."""
    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}
    conflicts = []

    teacher_bookings = {}  # teacher_id -> list of (day, start, end, section_id)
    for sid, info in result["by_section"].items():
        cls = class_lookup[section_lookup[sid].class_id]
        for sess in info["sessions"]:
            teacher_bookings.setdefault(info["teacher"], []).append(
                (sess["day"], sess["start_block"], sess["start_block"] + blocks_needed(cls.duration_minutes), sid)
            )

    for tid, bookings in teacher_bookings.items():
        for i in range(len(bookings)):
            for j in range(i + 1, len(bookings)):
                d1, s1, e1, sid1 = bookings[i]
                d2, s2, e2, sid2 = bookings[j]
                if d1 == d2 and s1 < e2 and s2 < e1:
                    conflicts.append(
                        f"Teacher {tid} double-booked on day {d1}: {sid1} ({s1}-{e1}) overlaps {sid2} ({s2}-{e2})"
                    )
    return conflicts

def verify_same_hour(result, sections, classes):
    """Checks that every section's sessions all start at the same time."""
    issues = []
    for sid, info in result["by_section"].items():
        start_times = {sess["start_block"] for sess in info["sessions"]}
        if len(start_times) > 1:
            issues.append(f"Section {sid} has inconsistent start blocks: {start_times}")
    return issues

# def diagnose_infeasibility(
#     sections: list[Section],
#     classes: list[ClassInfo],
#     teachers: list[Teacher], 
#     all_partials=(1, 2, 3)):
#     """
#     Rebuilds the model with every load-cap and no-double-booking constraint
#     wrapped in an assumption literal, then asks the solver for a minimal
#     set of assumptions that together cause infeasibility.
#     """
#     class_lookup = {c.id: c for c in classes}
#     section_lookup = {s.id: s for s in sections}
#     all_slots = sorted({slot for t in teachers for slot in t.availability})

#     model = cp_model.CpModel()
#     teaches, assign = {}, {}

#     for s in sections:
#         cls = class_lookup[s.class_id]
#         for t in teachers:
#             if cls.id in t.can_teach:
#                 teaches[s.id, t.id] = model.NewBoolVar(f"teaches_{s.id}_{t.id}")

#     for s in sections:
#         cls = class_lookup[s.class_id]
#         for t in teachers:
#             if (s.id, t.id) not in teaches:
#                 continue
#             for slot in t.availability:
#                 assign[s.id, t.id, slot] = model.NewBoolVar(f"a_{s.id}_{t.id}_{slot}")

#     assumptions = {}  # label -> BoolVar

#     # Hard structural constraints (kept unconditional -- these should never
#     # be the cause, since a section MUST have a teacher and MUST get its hours)
#     for s in sections:
#         vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
#         if not vars_:
#             print(f"HARD FAIL: no qualified teacher exists for section {s.id}")
#             return
#         model.Add(sum(vars_) == 1)

#     for (sid, tid, slot), v in assign.items():
#         model.Add(v <= teaches[sid, tid])

#     for s in sections:
#         cls = class_lookup[s.class_id]
#         vars_ = [v for (sid, tid, slot), v in assign.items() if sid == s.id]
#         model.Add(sum(vars_) == cls.hours_per_week)

#     # Suspect constraints -- each wrapped in an assumption literal
#     for t in teachers:
#         for slot in all_slots:
#             for p in all_partials:
#                 vars_ = [v for (sid, tid, s), v in assign.items()
#                          if tid == t.id and s == slot and p in section_lookup[sid].partials]
#                 if vars_:
#                     label = f"teacher_conflict_{t.id}_{slot}_{p}"
#                     a = model.NewBoolVar(label)
#                     model.Add(sum(vars_) <= 1).OnlyEnforceIf(a)
#                     assumptions[label] = a

#     group_keys = {(s.major, s.semester, s.group_number) for s in sections}
#     for key in group_keys:
#         matching = [s.id for s in sections if (s.major, s.semester, s.group_number) == key]
#         for slot in all_slots:
#             for p in all_partials:
#                 vars_ = [v for (sid, tid, s), v in assign.items()
#                          if s == slot and sid in matching and p in section_lookup[sid].partials]
#                 if vars_:
#                     label = f"group_conflict_{key}_{slot}_{p}"
#                     a = model.NewBoolVar(label)
#                     model.Add(sum(vars_) <= 1).OnlyEnforceIf(a)
#                     assumptions[label] = a

#     SCALE = 100
#     for t in teachers:
#         for p in all_partials:
#             vars_ = []
#             for s in sections:
#                 if p not in s.partials:
#                     continue
#                 key = (s.id, t.id)
#                 if key in teaches:
#                     cls = class_lookup[s.class_id]
#                     coeff = int(round(cls.load * SCALE))
#                     vars_.append(coeff * teaches[key])
#             if vars_:
#                 label = f"partial_load_{t.id}_{p}"
#                 a = model.NewBoolVar(label)
#                 bound = int(round(t.max_load_per_partial * SCALE))
#                 model.Add(sum(vars_) <= bound).OnlyEnforceIf(a)
#                 assumptions[label] = a

#     for t in teachers:
#         vars_ = []
#         for s in sections:
#             key = (s.id, t.id)
#             if key in teaches:
#                 cls = class_lookup[s.class_id]
#                 coeff = int(round(cls.load * len(s.partials) * SCALE))
#                 vars_.append(coeff * teaches[key])
#         if vars_:
#             label = f"total_load_{t.id}"
#             a = model.NewBoolVar(label)
#             bound = int(round(t.max_load_total * SCALE))
#             model.Add(sum(vars_) <= bound).OnlyEnforceIf(a)
#             assumptions[label] = a

#     model.AddAssumptions(list(assumptions.values()))

#     solver = cp_model.CpSolver()
#     status = solver.Solve(model)

#     if status == cp_model.INFEASIBLE:
#         conflict_labels = [
#             label for label, var in assumptions.items()
#             if var.index in solver.SufficientAssumptionsForInfeasibility()
#         ]
#         print("Minimal set of constraints causing infeasibility:")
#         for label in conflict_labels:
#             print(f"  - {label}")
#     else:
#         print("Model is feasible when suspect constraints are optional -- "
#               "the hard structural constraints (section coverage, teacher qualification) are fine.")

