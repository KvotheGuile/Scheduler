from dataclasses import dataclass
from ortools.sat.python import cp_model
from classes import ClassInfo, Section, Teacher 

SCALE = 100

def generate_schedule(
    sections: list[Section],
    classes: list[ClassInfo],
    teachers: list[Teacher],
    all_partials: tuple[int, ...] = (1, 2, 3),
    max_time_in_seconds: float = 60.0,
):
    """
    Returns a dict:
        {
            "status": "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN",
            "by_section": {section_id: {"teacher": teacher_id, "slots": [(day, period), ...]}},
            "by_teacher": {teacher_id: [(section_id, day, period), ...]},
        }
    NOTE: the "no double-booking" constraint for students groups a Section
    by (mayor, semester, group_number) across ALL classes. This assumes
    group_number represents the SAME physical cohort of students across
    different classes for that mayor+semester (the common real-world case).
    If your group numbering is independent per class, this constraint
    needs to be scoped differently -- flag this if that's the case.
    """

    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}

    # All timeslots that appear in any teacher's availability
    all_slots = sorted({slot for t in teachers for slot in t.availability})

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

    # assign[section_id, teacher_id, slot] = 1 if this session happens then
    assign = {}
    for s in sections:
        cls = class_lookup[s.class_id]
        for t in teachers:
            if (s.id, t.id) not in teaches:
                continue
            for slot in t.availability:
                assign[s.id, t.id, slot] = model.NewBoolVar(
                    f"assign_{s.id}_{t.id}_{slot[0]}_{slot[1]}"
                )

    # -----------------------------------------------------------------
    # Constraint 1: each section has exactly one teacher
    # -----------------------------------------------------------------
    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        if not vars_:
            raise ValueError(f"No qualified teacher available for section {s.id}")
        model.Add(sum(vars_) == 1)

    # -----------------------------------------------------------------
    # Constraint 2: assign implies teaches, and each section gets exactly
    # hours_per_week distinct slots (all with its one assigned teacher)
    # -----------------------------------------------------------------
    for (sid, tid, slot), v in assign.items():
        model.Add(v <= teaches[sid, tid])

    for s in sections:
        cls = class_lookup[s.class_id]
        vars_ = [v for (sid, tid, slot), v in assign.items() if sid == s.id]
        model.Add(sum(vars_) == cls.hours_per_week)

    # -----------------------------------------------------------------
    # Constraint 3: no teacher double-booked in a slot, scoped by partial
    # -----------------------------------------------------------------
    for t in teachers:
        for slot in all_slots:
            for p in all_partials:
                vars_ = [
                    v for (sid, tid, s), v in assign.items()
                    if tid == t.id and s == slot and p in section_lookup[sid].partials
                ]
                if vars_:
                    model.Add(sum(vars_) <= 1)

    # -----------------------------------------------------------------
    # Constraint 4: no student group double-booked in a slot, scoped by partial
    # Grouped by (mayor, semester, group_number) across all classes.
    # -----------------------------------------------------------------
    group_keys = {(s.mayor, s.semester, s.group_number) for s in sections}
    for key in group_keys:
        matching_sections = [s.id for s in sections
                              if (s.mayor, s.semester, s.group_number) == key]
        for slot in all_slots:
            for p in all_partials:
                vars_ = [
                    v for (sid, tid, s), v in assign.items()
                    if s == slot and sid in matching_sections and p in section_lookup[sid].partials
                ]
                if vars_:
                    model.Add(sum(vars_) <= 1)

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
                    coeff = int(round(cls.load * SCALE))
                    vars_.append(coeff * teaches[key])
            if vars_:
                bound = int(round(t.max_load_per_partial * SCALE))
                model.Add(sum(vars_) <= bound)
                # NOTE: if load/caps are non-integer, scale as needed for CP-SAT
                # (CP-SAT works over integers). Adjust scaling factor to your data.

    # -----------------------------------------------------------------
    # Constraint 6: teacher total semester load cap
    # -----------------------------------------------------------------
    for t in teachers:
        vars_ = []
        for s in sections:
            key = (s.id, t.id)
            if key in teaches:
                cls = class_lookup[s.class_id]
                coeff = int(round(cls.load * len(s.partials) * SCALE))
                vars_.append(coeff * teaches[key])
        if vars_:
               bound = int(round(t.max_load_total * SCALE))
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
        return result  # caller should check status before using empty results

    for (sid, tid, slot), v in assign.items():
        if solver.Value(v):
            result["by_section"].setdefault(sid, {"teacher": tid, "slots": []})
            result["by_section"][sid]["slots"].append(slot)
            result["by_teacher"].setdefault(tid, [])
            result["by_teacher"][tid].append((sid, slot[0], slot[1]))

    return result

def diagnose_infeasibility(
    sections: list[Section],
    classes: list[ClassInfo],
    teachers: list[Teacher], 
    all_partials=(1, 2, 3)):
    """
    Rebuilds the model with every load-cap and no-double-booking constraint
    wrapped in an assumption literal, then asks the solver for a minimal
    set of assumptions that together cause infeasibility.
    """
    class_lookup = {c.id: c for c in classes}
    section_lookup = {s.id: s for s in sections}
    all_slots = sorted({slot for t in teachers for slot in t.availability})

    model = cp_model.CpModel()
    teaches, assign = {}, {}

    for s in sections:
        cls = class_lookup[s.class_id]
        for t in teachers:
            if cls.id in t.can_teach:
                teaches[s.id, t.id] = model.NewBoolVar(f"teaches_{s.id}_{t.id}")

    for s in sections:
        cls = class_lookup[s.class_id]
        for t in teachers:
            if (s.id, t.id) not in teaches:
                continue
            for slot in t.availability:
                assign[s.id, t.id, slot] = model.NewBoolVar(f"a_{s.id}_{t.id}_{slot}")

    assumptions = {}  # label -> BoolVar

    # Hard structural constraints (kept unconditional -- these should never
    # be the cause, since a section MUST have a teacher and MUST get its hours)
    for s in sections:
        vars_ = [v for (sid, tid), v in teaches.items() if sid == s.id]
        if not vars_:
            print(f"HARD FAIL: no qualified teacher exists for section {s.id}")
            return
        model.Add(sum(vars_) == 1)

    for (sid, tid, slot), v in assign.items():
        model.Add(v <= teaches[sid, tid])

    for s in sections:
        cls = class_lookup[s.class_id]
        vars_ = [v for (sid, tid, slot), v in assign.items() if sid == s.id]
        model.Add(sum(vars_) == cls.hours_per_week)

    # Suspect constraints -- each wrapped in an assumption literal
    for t in teachers:
        for slot in all_slots:
            for p in all_partials:
                vars_ = [v for (sid, tid, s), v in assign.items()
                         if tid == t.id and s == slot and p in section_lookup[sid].partials]
                if vars_:
                    label = f"teacher_conflict_{t.id}_{slot}_{p}"
                    a = model.NewBoolVar(label)
                    model.Add(sum(vars_) <= 1).OnlyEnforceIf(a)
                    assumptions[label] = a

    group_keys = {(s.mayor, s.semester, s.group_number) for s in sections}
    for key in group_keys:
        matching = [s.id for s in sections if (s.mayor, s.semester, s.group_number) == key]
        for slot in all_slots:
            for p in all_partials:
                vars_ = [v for (sid, tid, s), v in assign.items()
                         if s == slot and sid in matching and p in section_lookup[sid].partials]
                if vars_:
                    label = f"group_conflict_{key}_{slot}_{p}"
                    a = model.NewBoolVar(label)
                    model.Add(sum(vars_) <= 1).OnlyEnforceIf(a)
                    assumptions[label] = a

    SCALE = 100
    for t in teachers:
        for p in all_partials:
            vars_ = []
            for s in sections:
                if p not in s.partials:
                    continue
                key = (s.id, t.id)
                if key in teaches:
                    cls = class_lookup[s.class_id]
                    coeff = int(round(cls.load * SCALE))
                    vars_.append(coeff * teaches[key])
            if vars_:
                label = f"partial_load_{t.id}_{p}"
                a = model.NewBoolVar(label)
                bound = int(round(t.max_load_per_partial * SCALE))
                model.Add(sum(vars_) <= bound).OnlyEnforceIf(a)
                assumptions[label] = a

    for t in teachers:
        vars_ = []
        for s in sections:
            key = (s.id, t.id)
            if key in teaches:
                cls = class_lookup[s.class_id]
                coeff = int(round(cls.load * len(s.partials) * SCALE))
                vars_.append(coeff * teaches[key])
        if vars_:
            label = f"total_load_{t.id}"
            a = model.NewBoolVar(label)
            bound = int(round(t.max_load_total * SCALE))
            model.Add(sum(vars_) <= bound).OnlyEnforceIf(a)
            assumptions[label] = a

    model.AddAssumptions(list(assumptions.values()))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.INFEASIBLE:
        conflict_labels = [
            label for label, var in assumptions.items()
            if var.index in solver.SufficientAssumptionsForInfeasibility()
        ]
        print("Minimal set of constraints causing infeasibility:")
        for label in conflict_labels:
            print(f"  - {label}")
    else:
        print("Model is feasible when suspect constraints are optional -- "
              "the hard structural constraints (section coverage, teacher qualification) are fine.")