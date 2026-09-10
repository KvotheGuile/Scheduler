from dataclasses import dataclass
from ortools.sat.python import cp_model
from classes import ClassInfo, Section, Teacher 
from collections import defaultdict

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
    # return (1, 2, 3)


def partials_to_periods(partials: set[int]) -> int: 
    first = 1 in partials
    second = 2 in partials
    third = 3 in partials

    if first and second and third:
        return 6
    elif second and third:
        return 5
    elif first and second:
        return 4
    elif third:
        return 3
    elif second:
        return 2
    elif second:
        return 1
    return 7

def days_numbers_2_text(days: list[int]) -> str:
    r = ""

    if 0 in days:
        r += "Lu"
    if 1 in days:
        r += "Ma"
    if 2 in days:
        r += "Mi"
    if 3 in days:
        r += "Ju"
    if 4 in days:
        r += "Vi"

    return r


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def generate_schedule(
    sections: list[Section],
    classes: list[ClassInfo],
    teachers: list[Teacher],
    classrooms: list[str],
    all_partials: tuple[int, ...] = (1, 2, 3),
    load_scale: int = 100,
    max_time_in_seconds: float = 180.0,
    relative_gap_limit = 0.05,
    w_teacher_gaps=10,
    w_days_used=5,
    w_teacher_load_imbalance=8,
    w_undesirable_time=3,
    w_group_gaps=10,
    w_group_balance=8,
    w_group_room=20,
    undesirable_start_blocks: set = None,
    
):
    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}
    teacher_lookup = {t.id: t for t in teachers}

    model = cp_model.CpModel()

    # -----------------------------------------------------------------
    # Variables
    # -----------------------------------------------------------------

    # -----------------------------------------------------------------
    # Variables: teaches[section_id, teacher_id]
    # Pre-filtered: skip pairs that are load-infeasible from the start,
    # so we never create assign variables for them either.
    # -----------------------------------------------------------------
    teaches = {}
    skipped_pairs = []  # for diagnostics, see below
    for s in sections:
        cls = class_lookup[s.class_id]
        for t in teachers:
            if cls.id not in t.can_teach:
                continue  # not qualified -- already filtered before this change

            # Minimum load this teacher would carry if given ONLY this section,
            # for its full run across all partials it's active in.
            min_possible_total_load = cls.load * len(s.partials)

            # Minimum load in the single heaviest partial this section touches
            # (a teacher could still be maxed out per-partial even if their
            # total cap has room).
            min_possible_partial_load = cls.load  # per active partial, same value each partial

            if min_possible_total_load > t.max_load_total:
                skipped_pairs.append((s.id, t.id, "exceeds max_load_total alone"))
                continue

            if min_possible_partial_load > t.max_load_per_partial:
                skipped_pairs.append((s.id, t.id, "exceeds max_load_per_partial alone"))
                continue

            teaches[s.id, t.id] = model.NewBoolVar(f"teaches_{s.id}_{t.id}")

    # Sanity check: every section must still have at least one viable teacher
    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        if not vars_:
            raise ValueError(
                f"No qualified AND load-feasible teacher exists for section {s.id} "
                f"-- check can_teach, max_load_total, and max_load_per_partial across teachers."
            )

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

    NUM_CLASSROOMS = len(classrooms)

    room_id = {}
    for s in sections:
        room_id[s.id] = model.NewIntVar(0, NUM_CLASSROOMS - 1, f"room_{s.id}")
        

    # Build once, reuse everywhere instead of scanning assign.items() repeatedly
    by_teacher_partial = defaultdict(list)
    by_group_partial = defaultdict(list)

    for (sid, tid, day, start), v in assign.items():
        s = section_lookup[sid]
        key_group = (s.major, s.semester, s.group_number)
        for p in s.partials:  # only iterate the partials this section is ACTUALLY in
            by_teacher_partial[tid, p].append((sid, day, start, v))
            by_group_partial[key_group, p].append((sid, day, start, v))

    # -----------------------------------------------------------------
    # Constraint 1: same class must occur at the same start_block every day
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
    # Constraint 2: each section has exactly one teacher
    # -----------------------------------------------------------------
    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        model.Add(sum(vars_) == 1)

    # -----------------------------------------------------------------
    # Constraint 3: assign implies teaches; each section gets exactly
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
    # Constraint 4: no teacher double-booked (interval-based, robust),
    # scoped by partial -- sessions in non-overlapping partials never
    # compete for the same teacher slot.
    # -----------------------------------------------------------------
    for t in teachers:
        for p in all_partials:
            entries = by_teacher_partial.get((t.id, p), [])
            if not entries:
                continue
            intervals = []
            for sid, day, start, v in entries:
                cls = class_lookup[section_lookup[sid].class_id]
                n_blocks = blocks_needed(cls.duration_minutes)
                global_start = day * BLOCKS_PER_DAY + start
                intervals.append(model.NewOptionalIntervalVar(
                    global_start, n_blocks, global_start + n_blocks, v, f"ivl_{sid}_{day}_{start}_{p}"
                ))
            model.AddNoOverlap(intervals)

    # -----------------------------------------------------------------
    # Constraint 5: no student group double-booked (interval-based),
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
    # Constraint 6: teacher per-partial load cap
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
    # Constraint 7: teacher total semester load cap
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
    # Constraint 8: No double-booked classrooms
    # -----------------------------------------------------------------
    for p in all_partials:
        time_intervals = []
        room_intervals = []
        for (sid, tid, day, start), v in assign.items():
            if p not in section_lookup[sid].partials:
                continue
            cls = class_lookup[section_lookup[sid].class_id]
            n_blocks = blocks_needed(cls.duration_minutes)
            global_start = day * BLOCKS_PER_DAY + start

            t_ivl = model.NewOptionalIntervalVar(
                global_start, n_blocks, global_start + n_blocks, v,
                f"room_time_{sid}_{tid}_{day}_{start}_{p}"
            )
            r_ivl = model.NewOptionalIntervalVar(
                room_id[sid], 1, room_id[sid] + 1, v,
                f"room_dim_{sid}_{tid}_{day}_{start}_{p}"
            )
            time_intervals.append(t_ivl)
            room_intervals.append(r_ivl)

        if time_intervals:
            model.AddNoOverlap2D(time_intervals, room_intervals)


    # -----------------------------------------------------------------
    # Optimization 1: Minimize the "span" between first and last class.
    # -----------------------------------------------------------------

    teacher_day_span_terms = []
    if w_teacher_gaps > 0:
        for t in teachers:
            for day in range(NUM_DAYS):
                day_sessions = [
                    (start, start + blocks_needed(class_lookup[section_lookup[sid].class_id].duration_minutes), v)
                    for (sid, tid, d, start), v in assign.items()
                    if tid == t.id and d == day
                ]
                if not day_sessions:
                    continue

                earliest = model.NewIntVar(0, BLOCKS_PER_DAY, f"earliest_{t.id}_{day}")
                latest = model.NewIntVar(0, BLOCKS_PER_DAY, f"latest_{t.id}_{day}")
                any_session_today = model.NewBoolVar(f"any_{t.id}_{day}")

                session_vars = [v for (_, _, v) in day_sessions]
                model.Add(sum(session_vars) >= 1).OnlyEnforceIf(any_session_today)
                model.Add(sum(session_vars) == 0).OnlyEnforceIf(any_session_today.Not())

                for start, end, v in day_sessions:
                    model.Add(earliest <= start).OnlyEnforceIf(v)
                    model.Add(latest >= end).OnlyEnforceIf(v)

                span = model.NewIntVar(0, BLOCKS_PER_DAY, f"span_{t.id}_{day}")
                model.Add(span == latest - earliest).OnlyEnforceIf(any_session_today)
                model.Add(span == 0).OnlyEnforceIf(any_session_today.Not())

                teacher_day_span_terms.append(span)

    
    # -----------------------------------------------------------------
    # Optimization 2: Minimize the amount of days teacher have classes.
    # -----------------------------------------------------------------

    teacher_days_used_terms = []
    if w_days_used > 0:
        for t in teachers:
            for day in range(NUM_DAYS):
                used = model.NewBoolVar(f"day_used_{t.id}_{day}")
                day_vars = [v for (sid, tid, d, start), v in assign.items() if tid == t.id and d == day]
                if day_vars:
                    model.Add(sum(day_vars) >= 1).OnlyEnforceIf(used)
                    model.Add(sum(day_vars) == 0).OnlyEnforceIf(used.Not())
                    teacher_days_used_terms.append(used)

    
    # -----------------------------------------------------------------
    # Optimization 3: Equalize's teacher load
    # -----------------------------------------------------------------

    teacher_load_vars = []
    for t in teachers:
        load_terms = []
        for s in sections:
            key = (s.id, t.id)
            if key in teaches:
                cls = class_lookup[s.class_id]
                coeff = int(round(cls.load * len(s.partials) * load_scale))
                load_terms.append(coeff * teaches[key])
        total = model.NewIntVar(0, 100000, f"total_load_{t.id}")
        model.Add(total == sum(load_terms)) if load_terms else model.Add(total == 0)
        teacher_load_vars.append(total)

    max_load = model.NewIntVar(0, 100000, "max_load")
    min_load = model.NewIntVar(0, 100000, "min_load")
    model.AddMaxEquality(max_load, teacher_load_vars)
    model.AddMinEquality(min_load, teacher_load_vars)
    load_imbalance = model.NewIntVar(0, 100000, "load_imbalance")
    model.Add(load_imbalance == max_load - min_load)

    
    # -----------------------------------------------------------------
    # Optimization 4: Undesirable hours
    # -----------------------------------------------------------------

    undesirable_penalty_terms = []
    if undesirable_start_blocks is not None and w_undesirable_time > 0:
        for (sid, start), var in uses_start.items():
            if start in undesirable_start_blocks:
                undesirable_penalty_terms.append(var)


    # -----------------------------------------------------------------
    # Optimization 5: Avoid gaps on students's classes
    # -----------------------------------------------------------------

    group_keys = {(s.major, s.semester, s.group_number) for s in sections}

    group_day_span_terms = []
    if w_group_gaps:
        for key in group_keys:
            key_str = "_".join(str(x) for x in key)
            matching_ids = {s.id for s in sections
                            if (s.major, s.semester, s.group_number) == key}

            for day in range(NUM_DAYS):
                day_sessions = []
                for (sid, tid, d, start), v in assign.items():
                    if sid not in matching_ids or d != day:
                        continue
                    cls = class_lookup[section_lookup[sid].class_id]
                    n_blocks = blocks_needed(cls.duration_minutes)
                    day_sessions.append((start, start + n_blocks, v))
                if not day_sessions:
                    continue

                earliest = model.NewIntVar(0, BLOCKS_PER_DAY, f"g_earliest_{key_str}_{day}")
                latest = model.NewIntVar(0, BLOCKS_PER_DAY, f"g_latest_{key_str}_{day}")
                any_session_today = model.NewBoolVar(f"g_any_{key_str}_{day}")

                session_vars = [v for (_, _, v) in day_sessions]
                model.Add(sum(session_vars) >= 1).OnlyEnforceIf(any_session_today)
                model.Add(sum(session_vars) == 0).OnlyEnforceIf(any_session_today.Not())

                for start, end, v in day_sessions:
                    model.Add(earliest <= start).OnlyEnforceIf(v)
                    model.Add(latest >= end).OnlyEnforceIf(v)

                span = model.NewIntVar(0, BLOCKS_PER_DAY, f"g_span_{key_str}_{day}")
                model.Add(span == latest - earliest).OnlyEnforceIf(any_session_today)
                model.Add(span == 0).OnlyEnforceIf(any_session_today.Not())

                group_day_span_terms.append(span)

    # -----------------------------------------------------------------
    # Optimization 6: Balance days
    # -----------------------------------------------------------------

    group_day_balance_terms = []
    if w_group_balance:
        for key in group_keys:
            key_str = "_".join(str(x) for x in key)
            matching_ids = {s.id for s in sections
                            if (s.major, s.semester, s.group_number) == key}

            day_counts = []
            for day in range(NUM_DAYS):
                vars_ = [v for (sid, tid, d, start), v in assign.items()
                        if sid in matching_ids and d == day]
                count = model.NewIntVar(0, 20, f"g_count_{key_str}_{day}")
                if vars_:
                    model.Add(count == sum(vars_))
                else:
                    model.Add(count == 0)
                day_counts.append(count)

            max_count = model.NewIntVar(0, 20, f"g_max_{key_str}")
            min_count = model.NewIntVar(0, 20, f"g_min_{key_str}")
            model.AddMaxEquality(max_count, day_counts)
            model.AddMinEquality(min_count, day_counts)

            imbalance = model.NewIntVar(0, 20, f"g_dist_imbalance_{key_str}")
            model.Add(imbalance == max_count - min_count)
            group_day_balance_terms.append(imbalance)

    
    # -----------------------------------------------------------------
    # Optimization 7: All classes of a group in same room
    # -----------------------------------------------------------------

    group_room_penalty_terms = []
    if w_group_room:
        for key in group_keys:
            matching_ids = [s.id for s in sections
                            if (s.major, s.semester, s.group_number) == key]
            for i in range(len(matching_ids)):
                for j in range(i + 1, len(matching_ids)):
                    sid1, sid2 = matching_ids[i], matching_ids[j]
                    diff = model.NewBoolVar(f"room_diff_{sid1}_{sid2}")
                    model.Add(room_id[sid1] != room_id[sid2]).OnlyEnforceIf(diff)
                    model.Add(room_id[sid1] == room_id[sid2]).OnlyEnforceIf(diff.Not())
                    group_room_penalty_terms.append(diff)

    # -----------------------------------------------------------------
    # Optimization Weights
    # -----------------------------------------------------------------
    
    objective_terms = []

    objective_terms += [w_teacher_gaps * v for v in teacher_day_span_terms]
    objective_terms += [w_days_used * v for v in teacher_days_used_terms]
    objective_terms.append(w_teacher_load_imbalance * load_imbalance)
    objective_terms += [w_undesirable_time * v for v in undesirable_penalty_terms]
    objective_terms += [w_group_gaps * v for v in group_day_span_terms]
    objective_terms += [w_group_balance * v for v in group_day_balance_terms]
    objective_terms += [w_group_room * v for v in group_room_penalty_terms]

    if objective_terms:
        model.Minimize(sum(objective_terms))

    # -----------------------------------------------------------------
    # Solve
    # -----------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_in_seconds
    solver.parameters.relative_gap_limit = relative_gap_limit
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True  # prints search stats live
    status = solver.Solve(model)

    print(solver.ResponseStats())

    status_name = solver.StatusName(status)
    result = {"status": status_name, 
              "by_section": {}, 
              "by_teacher": {},
              "schedule": []}

    full_schedule = {}

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    for (sid, tid, day, start), v in assign.items():
        if solver.Value(v):
            sct = section_lookup[sid]
            cls = class_lookup[sct.class_id]
            tch = teacher_lookup[tid]
            
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

            full_schedule.setdefault((sid, tid, start), {})
            full_schedule[(sid, tid, start)]["carrera"] = sct.major
            full_schedule[(sid, tid, start)]["semestre"] = sct.semester
            full_schedule[(sid, tid, start)]["claseId"] = sct.class_id
            full_schedule[(sid, tid, start)]["profeId"] = tid
            full_schedule[(sid, tid, start)]["claseNombre"] = cls.name
            full_schedule[(sid, tid, start)]["profeNombre"] = tch.name
            full_schedule[(sid, tid, start)]["grupo"] = sct.group_number + 100 * partials_to_periods(cls.partials)
            full_schedule[(sid, tid, start)].setdefault("dias", [])
            full_schedule[(sid, tid, start)]["dias"].append(day)
            full_schedule[(sid, tid, start)]["horaInicio"] = block_to_time(start)
            full_schedule[(sid, tid, start)]["horaFinal"] = block_to_time(end_block)
            full_schedule[(sid, tid, start)]["salon"]  = classrooms[solver.Value(room_id[sid])]
            full_schedule[(sid, tid, start)]["carga"] = cls.load

    for key in full_schedule:
        full_schedule[key]["dias"] = days_numbers_2_text(full_schedule[key]["dias"])
        result["schedule"].append(full_schedule[key])

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

def verify_group_conflicts(result, sections, classes):
    """Checks no (major, semester, group) has overlapping sessions
    across different classes, during partials where they both run."""
    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}
    issues = []

    group_bookings = {}  # (major, semester, group) -> list of (day, start, end, section_id)
    for sid, info in result["by_section"].items():
        s = section_lookup[sid]
        key = (s.major, s.semester, s.group_number)
        cls = class_lookup[s.class_id]
        n_blocks = blocks_needed(cls.duration_minutes)
        for sess in info["sessions"]:
            group_bookings.setdefault(key, []).append(
                (sess["day"], sess["start_block"], sess["start_block"] + n_blocks, sid)
            )

    for key, bookings in group_bookings.items():
        for i in range(len(bookings)):
            for j in range(i + 1, len(bookings)):
                d1, s1, e1, sid1 = bookings[i]
                d2, s2, e2, sid2 = bookings[j]

                # Day & Time overlap check
                if d1 != d2 or not (s1 < e2 and s2 < e1):
                    continue

                # Only a real conflict if the two sections share at least on partial
                partials1 = section_lookup[sid1].partials
                partials2 = section_lookup[sid2].partials
                if partials1.isdisjoint(partials2):
                    continue  # different partials

                issues.append(
                    f"Group {key} double-booked on day {d1}: {sid1} ({s1}-{e1}, partials={partials1}) "
                    f"overlaps {sid2} ({s2}-{e2}, partials={partials2})"
                )

    return issues