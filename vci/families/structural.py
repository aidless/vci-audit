"""Structural families: grid pathfinding, constraint satisfaction, scheduling,
topological order, cellular automata and code repair."""
import itertools
import json
import subprocess
import sys
import time
from collections import deque
from typing import Any, Dict, List, Optional

from ..schema import Candidate, Task, Verdict
from ..util import parse_number
from .base import Family


# --------------------------------------------------------------------- paths
def _bfs(grid: List[str], start, goal, dirs=((1, 0), (0, 1), (-1, 0), (0, -1))):
    rows, cols = len(grid), len(grid[0])
    prev = {tuple(start): None}
    q = deque([tuple(start)])
    while q:
        cur = q.popleft()
        if cur == tuple(goal):
            break
        for dr, dc in dirs:
            nr, nc = cur[0] + dr, cur[1] + dc
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] != "#" and (nr, nc) not in prev:
                prev[(nr, nc)] = cur
                q.append((nr, nc))
    if tuple(goal) not in prev:
        return None
    path, cur = [], tuple(goal)
    while cur is not None:
        path.append(list(cur))
        cur = prev[cur]
    return path[::-1]


class GridPath(Family):
    name = "grid_path"
    domain = "planning"
    task_shape = "find shortest paths for K start/goal pairs on an obstacle grid"
    premise = "exact BFS distance; obstacle and adjacency rules are decidable"
    scoring = "fraction of paths that are valid, obstacle-free and optimal length"
    item_unit = "one start/goal pair"
    payload_kind = "list"

    def make_one(self, rng, idx):
        rows = cols = rng.randint(5, 7)
        grid = ["".join("#" if rng.random() < 0.22 else "." for _ in range(cols))
                for _ in range(rows)]
        pairs = []
        attempts = 0
        while len(pairs) < 3 and attempts < 500:
            attempts += 1
            s = (rng.randrange(rows), rng.randrange(cols))
            g = (rng.randrange(rows), rng.randrange(cols))
            if s == g or grid[s[0]][s[1]] == "#" or grid[g[0]][g[1]] == "#":
                continue
            p1 = _bfs(grid, s, g)
            p2 = _bfs(grid, s, g, ((-1, 0), (0, -1), (1, 0), (0, 1)))
            if p1 is None or len(p1) < 6:
                continue
            pairs.append({"start": list(s), "goal": list(g), "path": p1,
                          "alt": p2 or p1})
        if len(pairs) < 3:
            return self.make_one(rng, idx)
        items = []
        for j, p in enumerate(pairs, 1):
            items.append({"unit": f"p{j}", "expected": {"start": p["start"],
                                                        "goal": p["goal"],
                                                        "len": len(p["path"])},
                          "path": p["path"], "alt": p["alt"]})
        prompt = ("Find a shortest 4-connected path from S to G on each grid "
                  "(# = blocked).  Return a JSON array with one path per pair; a "
                  "path is a list of [row, col] cells starting at S and ending at G.\n"
                  f"  grid = {grid}\n  pairs = " +
                  str([{"start": p["start"], "goal": p["goal"]} for p in pairs]))
        return self.task(f"grid_path-{idx:03d}", prompt, items, {"grid": grid})

    def canonical(self, task):
        return [it["path"] for it in task.items]

    def equivalents(self, task, rng):
        return [([it["alt"] for it in task.items], "an alternative shortest path")]

    def wrongs(self, task, rng):
        base = [it["path"] for it in task.items]
        p0 = base[0]
        diag = [p0[0], [p0[0][0] + 1, p0[0][1] + 1]] + p0[1:]
        short = [x[:-1] for x in base]
        longp = [p0[:1] + [p0[0], p0[1]] + p0[2:]] + base[1:]
        return [("boundary", diag + base[1:], "diagonal step at the first corner"),
                ("off_by_one", short, "first path stops one cell before the goal"),
                ("type_mismatch", ["->".join(f"{r},{c}" for r, c in p0)] + base[1:],
                 "path encoded as a string"),
                ("order", [list(reversed(p)) for p in base], "paths reversed"),
                ("missing", base[:-1], "last path omitted"),
                ("extra", base + [[[0, 0], [0, 1]]], "extra path appended"),
                ("semantic_wrong", longp, "valid but non-shortest path (repeated cell)")]

    def corrupt_item(self, task, item, rng):
        return item["path"][:-2]

    def grade_item(self, task, item, answer):
        grid = task.meta["grid"]
        exp = item["expected"]
        if not isinstance(answer, list) or not all(isinstance(c, (list, tuple)) and len(c) == 2
                                                   for c in answer):
            return False, "path must be a list of [row, col] cells"
        cells = [(int(c[0]), int(c[1])) for c in answer]
        problems = []
        if list(cells[0]) != exp["start"]:
            problems.append("wrong start")
        if list(cells[-1]) != exp["goal"]:
            problems.append("wrong goal")
        rows, cols = len(grid), len(grid[0])
        if any(not (0 <= r < rows and 0 <= c < cols) for r, c in cells):
            problems.append("cell out of bounds")
        if any(grid[r][c] == "#" for r, c in cells if 0 <= r < rows and 0 <= c < cols):
            problems.append("path crosses an obstacle")
        if any(abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1 for a, b in zip(cells, cells[1:])):
            problems.append("non-adjacent step")
        if len(cells) != exp["len"]:
            problems.append(f"length {len(cells)} != optimal {exp['len']}")
        return (not problems), ("valid shortest path" if not problems else "; ".join(problems))


# ------------------------------------------------------------------------ CSP
def _csp_solutions(nodes, edges, n_colors, pins, limit=2, seed_order=None):
    adjacency = {n: set() for n in nodes}
    for u, v in edges:
        adjacency[u].add(v)
        adjacency[v].add(u)
    order = list(nodes) if seed_order is None else list(seed_order)
    solutions = []

    def valid_partial(assign):
        for n, c in assign.items():
            if n in pins and pins[n] != c:
                return False
            for nb in adjacency[n]:
                if nb in assign and assign[nb] == c:
                    return False
        return True

    def rec(i, assign):
        if len(solutions) >= limit:
            return
        if i == len(order):
            solutions.append(dict(assign))
            return
        n = order[i]
        for c in range(1, n_colors + 1):
            assign[n] = c
            if valid_partial(assign):
                rec(i + 1, assign)
            del assign[n]
            if len(solutions) >= limit:
                return

    rec(0, {})
    return solutions


class CspAssign(Family):
    name = "csp_assign"
    domain = "constraint programming"
    task_shape = "colour K small graphs under edge and pin constraints"
    premise = "finite domains; constraints are decidable and multiple solutions are legal"
    scoring = "fraction of sub-problems whose assignment satisfies every constraint"
    item_unit = "one colouring problem"
    payload_kind = "list"

    def make_one(self, rng, idx):
        items = []
        for j in range(1, 4):
            nodes = [chr(65 + i) for i in range(rng.randint(4, 5))]
            pairs = [(u, v) for i, u in enumerate(nodes) for v in nodes[i + 1:]]
            edges = [p for p in pairs if rng.random() < 0.55]
            while len(edges) < 2:  # an edge-free graph is unverifiable, not a task
                edges.append(rng.choice([p for p in pairs if p not in edges]))
            sols = _csp_solutions(nodes, edges, 3, {})
            while not sols and len(edges) > 2:
                edges = edges[:-1]
                sols = _csp_solutions(nodes, edges, 3, {})
            pins = {}
            if sols and rng.random() < 0.7:
                n = rng.choice(nodes)
                pins = {n: sols[0][n]}
            sols = _csp_solutions(nodes, edges, 3, pins)
            items.append({"unit": f"g{j}", "expected": sols[0],
                          "constraints": {"nodes": nodes, "edges": edges, "pins": pins,
                                          "colors": 3}})
        prompt = ("Colour each graph with colours 1, 2, 3 so that adjacent nodes differ "
                  "and pinned nodes keep their colour.  Return a JSON array with one "
                  "object {node: colour} per graph, in order.\n  problems = " +
                  str([it["constraints"] for it in items]))
        return self.task(f"csp_assign-{idx:03d}", prompt, items, {})

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        alt = []
        for it in task.items:
            c = it["constraints"]
            sols = _csp_solutions(c["nodes"], c["edges"], c["colors"], c["pins"],
                                  limit=2, seed_order=list(reversed(c["nodes"])))
            alt.append(sols[-1] if sols else it["expected"])
        return [(alt, "a different valid colouring")]

    def _conflict_variant(self, it):
        c = it["constraints"]
        sol = dict(it["expected"])
        for u, v in c["edges"]:
            cand = dict(sol)
            cand[v] = sol[u]
            return cand
        return dict(sol)

    def _invalid_variant(self, it):
        c = it["constraints"]
        sol = dict(it["expected"])
        nodes, edges, pins = c["nodes"], c["edges"], c["pins"]
        if pins:
            n = list(pins)[0]
            for col in range(1, c["colors"] + 1):
                if col != pins[n]:
                    cand = dict(sol)
                    cand[n] = col
                    return cand
        return self._conflict_variant(it)

    def _near_miss(self, it):
        """Increment one node's colour; keep the first alternative that is invalid."""
        c = it["constraints"]
        sol = dict(it["expected"])
        nodes = c["nodes"]
        for n in nodes:
            for delta in (1, 2):
                col = ((sol[n] - 1 + delta) % c["colors"]) + 1
                cand = dict(sol)
                cand[n] = col
                if not self._is_valid(c, cand):
                    return cand
        return self._conflict_variant(it)

    @staticmethod
    def _is_valid(c, cand):
        if set(cand) != set(c["nodes"]):
            return False
        for u, v in c["edges"]:
            if cand[u] == cand[v]:
                return False
        for n, col in c["pins"].items():
            if cand[n] != col:
                return False
        return True

    def wrongs(self, task, rng):
        base = [dict(it["expected"]) for it in task.items]
        bad = self._invalid_variant(task.items[0])
        conflict = self._conflict_variant(task.items[0])
        near = self._near_miss(task.items[0])
        typ = [json.dumps(base[0])] + base[1:]
        rot = list(reversed(base))
        if all(self._is_valid(task.items[i]["constraints"], rot[i]) for i in range(len(rot))):
            rot[0] = self._conflict_variant(task.items[0])
        return [("boundary", [bad] + base[1:], "pinned node moved off its pin"),
                ("off_by_one", [near] + base[1:], "one node colour incremented into a conflict"),
                ("type_mismatch", typ, "assignment encoded as a string"),
                ("order", rot, "assignments reversed"),
                ("missing", base[:-1], "last assignment omitted"),
                ("extra", base + [{"Z": 1}], "extra assignment appended"),
                ("semantic_wrong", [conflict] + base[1:], "edge constraint violated")]

    def corrupt_item(self, task, item, rng):
        return self._invalid_variant(item)

    def grade_item(self, task, item, answer):
        c = item["constraints"]
        if not isinstance(answer, dict):
            return False, f"expected an object, got {type(answer).__name__}"
        if set(answer) != set(c["nodes"]):
            return False, f"nodes mismatch: expected {c['nodes']}, got {sorted(answer)}"
        for n, v in answer.items():
            v_parsed = parse_number(v)
            if v_parsed is None or v_parsed.denominator != 1 or not (1 <= int(v_parsed) <= c["colors"]):
                return False, f"colour for {n} is not an integer in 1..{c['colors']}"
        for u, v in c["edges"]:
            if int(parse_number(answer[u])) == int(parse_number(answer[v])):
                return False, f"edge {u}-{v} has equal colours"
        for n, col in c["pins"].items():
            if int(parse_number(answer[n])) != col:
                return False, f"pin {n}={col} violated"
        return True, "all constraints satisfied"


# ----------------------------------------------------------------- scheduling
class ScheduleSlots(Family):
    name = "schedule_slots"
    domain = "scheduling"
    task_shape = "place K small meeting sets into free calendar slots"
    premise = "30-minute discrete slots; availability and room conflicts are decidable"
    scoring = "fraction of sub-schedules satisfying availability, duration and non-overlap"
    item_unit = "one meeting set"
    payload_kind = "list"

    SLOTS = 16

    def _make_problem(self, rng):
        n_meet = rng.randint(2, 3)
        meetings = [{"id": f"m{i + 1}", "dur": rng.randint(1, 2),
                     "who": rng.sample(["ann", "bob", "cy"], rng.randint(1, 2))}
                    for i in range(n_meet)]
        busy = {}
        for person in ("ann", "bob", "cy"):
            busy[person] = sorted(rng.sample(range(self.SLOTS), rng.randint(2, 4)))
        return {"meetings": meetings, "busy": busy}

    def _valid(self, prob, starts):
        occupied = []
        for m in prob["meetings"]:
            s = starts.get(m["id"])
            if s is None or not isinstance(s, int) or s < 0 or s + m["dur"] > self.SLOTS:
                return False
            cells = set(range(s, s + m["dur"]))
            for person in m["who"]:
                if cells & set(prob["busy"][person]):
                    return False
            if any(cells & occ for occ in occupied):
                return False
            occupied.append(cells)
        return set(starts) == {m["id"] for m in prob["meetings"]}

    def _solve(self, prob, limit=2):
        ids = [m["id"] for m in prob["meetings"]]
        durs = [m["dur"] for m in prob["meetings"]]
        out = []
        for combo in itertools.product(range(self.SLOTS), repeat=len(ids)):
            starts = dict(zip(ids, combo))
            if all(s + d <= self.SLOTS for s, d in zip(combo, durs)) and self._valid(prob, starts):
                out.append(starts)
                if len(out) >= limit:
                    break
        return out

    def make_one(self, rng, idx):
        items = []
        for j in range(1, 4):
            prob = None
            sols = []
            for _ in range(60):
                prob = self._make_problem(rng)
                sols = self._solve(prob, limit=2)
                if sols:
                    break
            if not sols:
                return self.make_one(rng, idx)
            items.append({"unit": f"s{j}", "expected": sols[0], "alt": sols[-1],
                          "problem": prob})
        prompt = ("Schedule each meeting set into 30-minute slots 0..15 (slot 0 = 09:00).  "
                  "Meetings must fit their attendees' busy slots, stay inside the day, "
                  "and not overlap (single room).  Return a JSON array with one object "
                  "{meeting_id: start_slot} per set, in order.\n  problems = " +
                  str([it["problem"] for it in items]))
        return self.task(f"schedule_slots-{idx:03d}", prompt, items, {})

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        return [([it["alt"] for it in task.items], "an alternative valid schedule")]

    def _shift_invalid(self, prob, sol):
        ids = [m["id"] for m in prob["meetings"]]
        for mid in ids:
            for delta in (1, -1, 2, -2):
                cand = dict(sol)
                cand[mid] = sol[mid] + delta
                if not self._valid(prob, cand):
                    return cand
        return dict(sol)

    def wrongs(self, task, rng):
        it0 = task.items[0]
        prob, sol = it0["problem"], it0["expected"]
        base = [it["expected"] for it in task.items]
        bad = self._shift_invalid(prob, sol)
        late = dict(sol)
        mid = prob["meetings"][0]["id"]
        late[mid] = self.SLOTS - prob["meetings"][0]["dur"] + 1
        busy = dict(sol)
        for m in prob["meetings"]:
            b = prob["busy"][m["who"][0]]
            if b:
                busy[m["id"]] = b[0]
                break
        strings = [{k: f"{9 + v // 2:02d}:{(v % 2) * 30:02d}" for k, v in sol.items()}]
        rot = base[1:] + base[:1]
        # Under multi-solution grading a rotated answer can still be valid for the
        # problem it lands on; make one entry genuinely infeasible so the payload
        # really is wrong.
        if all(self._valid(it["problem"], r) for it, r in zip(task.items, rot)):
            rot[0] = self._shift_invalid(task.items[0]["problem"], rot[0])
        return [("boundary", [late] + base[1:], "meeting starts past the end of day"),
                ("off_by_one", [bad] + base[1:], "meeting shifted by one slot into a conflict"),
                ("type_mismatch", strings + base[1:], "clock strings instead of slot integers"),
                ("order", rot, "schedules rotated one position"),
                ("missing", base[:-1], "last schedule omitted"),
                ("extra", base + [{"m9": 0}], "extra schedule appended"),
                ("semantic_wrong", [busy] + base[1:], "meeting placed on a busy slot")]

    def corrupt_item(self, task, item, rng):
        return self._shift_invalid(item["problem"], item["expected"])

    def grade_item(self, task, item, answer):
        prob = item["problem"]
        if not isinstance(answer, dict):
            return False, f"expected an object, got {type(answer).__name__}"
        parsed = {}
        for k, v in answer.items():
            pv = parse_number(v)
            if pv is None or pv.denominator != 1:
                return False, f"start slot for {k} is not an integer"
            parsed[k] = int(pv)
        if set(parsed) != {m["id"] for m in prob["meetings"]}:
            return False, "meeting ids do not match the problem"
        return self.ok(self._valid(prob, parsed), "all scheduling constraints satisfied",
                       "availability, duration or non-overlap constraint violated")


# ----------------------------------------------------------------------- DAGs
class TopoOrder(Family):
    name = "topo_order"
    domain = "graph algorithms"
    task_shape = "produce a topological order for K DAGs"
    premise = "any order satisfying all edge constraints is correct"
    scoring = "fraction of DAGs whose output order respects every edge and lists each node once"
    item_unit = "one DAG"
    payload_kind = "list"

    def make_one(self, rng, idx):
        items = []
        for j in range(1, 4):
            n = rng.randint(5, 7)
            nodes = [chr(65 + i) for i in range(n)]
            hidden = list(nodes)
            rng.shuffle(hidden)
            edges = [(hidden[i], hidden[k]) for i in range(n) for k in range(i + 1, n)
                     if rng.random() < 0.35]
            if len(edges) < 4:
                edges += [(hidden[i], hidden[i + 1]) for i in range(n - 1)
                          if (hidden[i], hidden[i + 1]) not in edges]
            alt = self._kahn(nodes, edges, rng)
            items.append({"unit": f"d{j}", "expected": hidden, "alt": alt,
                          "graph": {"nodes": nodes, "edges": edges}})
        prompt = ("Return one topological order per directed acyclic graph: every edge "
                  "u -> v must have u before v.  Any valid order is accepted.  Answer "
                  "with a JSON array of node arrays.\n  graphs = " +
                  str([it["graph"] for it in items]))
        return self.task(f"topo_order-{idx:03d}", prompt, items, {})

    @staticmethod
    def _kahn(nodes, edges, rng):
        indeg = {n: 0 for n in nodes}
        for u, v in edges:
            indeg[v] += 1
        ready = sorted(n for n in nodes if indeg[n] == 0)
        out = []
        while ready:
            n = ready.pop(rng.randrange(len(ready)))
            out.append(n)
            for u, v in edges:
                if u == n:
                    indeg[v] -= 1
                    if indeg[v] == 0:
                        ready.append(v)
        return out

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        return [([it["alt"] for it in task.items], "a different valid topological order")]

    def _swap_edge(self, order, edges):
        for i, u in enumerate(order):
            for v in order[i + 1:]:
                if (u, v) in edges:
                    out = list(order)
                    out[out.index(u)] = v
                    out[out.index(v)] = u
                    # ensure the swap really violates an edge
                    pos = {n: k for k, n in enumerate(out)}
                    if any(pos[a] > pos[b] for a, b in edges):
                        return out
        return list(reversed(order))

    def _shift_by_one(self, order, edges):
        """Move one node just past its own successor, which must break an edge."""
        pos = {n: i for i, n in enumerate(order)}
        for u in order:
            succ = [v for a, v in edges if a == u]
            if succ:
                v = min(succ, key=lambda x: pos[x])
                out = [n for n in order if n != u]
                out.insert(out.index(v) + 1, u)
                pos2 = {n: k for k, n in enumerate(out)}
                if any(pos2[a] > pos2[b] for a, b in edges):
                    return out
        return self._swap_edge(order, edges)

    def wrongs(self, task, rng):
        it0 = task.items[0]
        edges = it0["graph"]["edges"]
        base = [it["expected"] for it in task.items]
        moved = [self._shift_by_one(base[0], edges)] + base[1:]
        swapped = self._swap_edge(base[0], edges)
        double = base[0][:-1] + [base[0][0]]
        return [("order", [swapped] + base[1:], "two edge-connected nodes swapped"),
                ("off_by_one", moved, "one node moved past its successor"),
                ("boundary", [list(reversed(base[0]))] + base[1:], "entire order reversed"),
                ("type_mismatch", [[{"n": x} for x in base[0]]] + base[1:], "nodes wrapped in objects"),
                ("missing", [base[0][:-1]] + base[1:], "one node omitted"),
                ("extra", [double] + base[1:], "one node duplicated"),
                ("semantic_wrong", [self._swap_edge(base[0], edges)] + base[1:], "constraint-breaking order")]

    def corrupt_item(self, task, item, rng):
        return self._swap_edge(item["expected"], item["graph"]["edges"])

    def grade_item(self, task, item, answer):
        graph = item["graph"]
        if not isinstance(answer, list):
            return False, "expected an array of node names"
        names = [x for x in answer if isinstance(x, str)]
        if len(names) != len(answer) or set(names) != set(graph["nodes"]) or len(names) != len(set(names)):
            return False, "order must list each node exactly once"
        pos = {n: i for i, n in enumerate(names)}
        for u, v in graph["edges"]:
            if pos[u] > pos[v]:
                return False, f"edge {u}->{v} violated"
        return True, "all edges respected"


# --------------------------------------------------------------- cellular world
class LifeStep(Family):
    name = "life_step"
    domain = "cellular automata"
    task_shape = "advance one Conway Life board by one generation (dead border)"
    premise = "fully deterministic local rule"
    scoring = "fraction of output rows that match exactly"
    item_unit = "one output row"
    payload_kind = "list"

    def _step(self, board, wrap=False):
        rows, cols = len(board), len(board[0])
        out = []
        for r in range(rows):
            line = []
            for c in range(cols):
                n = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == dc == 0:
                            continue
                        rr, cc = r + dr, c + dc
                        if wrap:
                            rr, cc = rr % rows, cc % cols
                        elif 0 <= rr < rows and 0 <= cc < cols:
                            pass
                        else:
                            continue
                        n += board[rr][cc]
                line.append("1" if (n == 3 or (n == 2 and board[r][c])) else "0")
            out.append("".join(line))
        return out

    def _born_at_two(self, board):
        rows, cols = len(board), len(board[0])
        out = []
        for r in range(rows):
            line = []
            for c in range(cols):
                n = sum(board[rr][cc]
                        for rr in range(max(0, r - 1), min(rows, r + 2))
                        for cc in range(max(0, c - 1), min(cols, c + 2))
                        if (rr, cc) != (r, c))
                line.append("1" if (n in (2, 3)) else "0")
            out.append("".join(line))
        return out

    def make_one(self, rng, idx):
        for _ in range(60):
            rows, cols = rng.randint(5, 6), rng.randint(5, 7)
            board = [[1 if rng.random() < 0.35 else 0 for _ in range(cols)]
                     for _ in range(rows)]
            board[0][0] = 1
            board[rows - 1][cols - 1] = 1
            variants = self._variants(board)
            expected = self._step(board)
            if all(v != expected for v in variants.values()) and sum(
                    sum(row) for row in board) >= 2:
                items = [{"unit": f"r{i + 1}", "expected": expected[i]}
                         for i in range(rows)]
                grid = ["".join(str(x) for x in row) for row in board]
                prompt = ("Apply one generation of Conway's Game of Life (B3/S23) to the "
                          "board below.  Cells outside the board are dead.  Return the "
                          "new board as a JSON array of row strings of 0/1.\n  board = "
                          + str(grid))
                return self.task(f"life_step-{idx:03d}", prompt, items,
                                 {"board": grid, "rows": rows})
        return self.make_one(rng, idx)

    def _variants(self, board):
        rows, cols = len(board), len(board[0])
        expected = self._step(board)
        wrap = self._step(board, wrap=True)
        born = self._born_at_two(board)
        return {
            "boundary": wrap,
            "off_by_one": born,
            "order": list(reversed(expected)),
            "missing": expected[:-1],
            "extra": expected + ["0" * cols],
            "unchanged": ["".join(str(x) for x in row) for row in board],
        }

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        cols = len(task.items[0]["expected"])
        lists = [[int(ch) for ch in it["expected"]] for it in task.items]
        return [(lists, "rows as integer arrays")]

    def wrongs(self, task, rng):
        v = self._variants([[int(ch) for ch in row] for row in task.meta["board"]])
        base = self.canonical(task)
        typ = [None] + base[1:]
        return [("boundary", v["boundary"], "toroidal wrap at the border"),
                ("off_by_one", v["off_by_one"], "birth rule fires at two neighbours"),
                ("type_mismatch", typ, "null row"),
                ("order", v["order"], "rows reversed"),
                ("missing", v["missing"], "last row omitted"),
                ("extra", v["extra"], "extra row appended"),
                ("semantic_wrong", v["unchanged"], "board left unchanged")]

    def corrupt_item(self, task, item, rng):
        exp = item["expected"]
        allrows = {i["expected"] for i in task.items}
        cand = "".join("1" if ch == "0" else "0" for ch in exp)
        k = 0
        while cand in allrows and k < len(exp):
            cand = exp[:k] + ("1" if exp[k] == "0" else "0") + exp[k + 1:]
            k += 1
        return cand

    def extract_answers(self, task, payload):
        if isinstance(payload, dict) and set(payload) == {"answers"}:
            payload = payload["answers"]
        if not isinstance(payload, (list, tuple)):
            return {}, [], f"payload is {type(payload).__name__}, expected a list of rows"
        answers, extras = {}, []
        for i, row in enumerate(payload):
            if i >= len(task.items):
                extras.append(f"extra[{i}]")
                continue
            if isinstance(row, list):
                row = "".join(str(int(x)) for x in row if isinstance(x, (int, float)) and not isinstance(x, bool))
            answers[task.items[i]["unit"]] = row
        return answers, extras, None

    def grade_item(self, task, item, answer):
        if not isinstance(answer, str):
            return False, f"row must be a string of 0/1, got {type(answer).__name__}"
        s = answer.strip().replace(" ", "")
        if len(s) != len(item["expected"]) or set(s) - {"0", "1"}:
            return False, f"row must be {len(item['expected'])} binary digits"
        return self.ok(s == item["expected"], "row matches",
                       f"expected {item['expected']}, got {s}")


# ------------------------------------------------------------------ code patch
_CODE_TEMPLATES = [
    {
        "name": "running_max",
        "spec": "return the running maximum after each element",
        "sig": ["nums"],
        "cases": [[[3, -1, 4]], [[-5, -2, -9]], [[7]], [[0, 4, 0]], [[]]],
        "correct": "def solve(nums):\n    out = []\n    best = None\n    for x in nums:\n"
                   "        best = x if best is None or x > best else best\n"
                   "        out.append(best)\n    return out\n",
        "alt": "def solve(nums):\n    return [max(nums[:i+1]) for i in range(len(nums))]\n",
        "buggy": "def solve(nums):\n    out = []\n    best = 0\n    for x in nums:\n"
                 "        if x > best:\n            best = x\n        out.append(best)\n    return out\n",
        "boundary": "def solve(nums):\n    if not nums:\n        return [0]\n    out=[]\n"
                     "    best=None\n    for x in nums:\n"
                     "        best = x if best is None or x > best else best\n"
                     "        out.append(best)\n    return out\n",
        "off1": "def solve(nums):\n    out=[]\n    best=None\n    for x in nums:\n"
                "        best = x if best is None or x > best else best\n"
                "        out.append(best)\n    return out[1:] + ([out[-1]] if out else [])\n",
        "type": "def solve(nums):\n    out=[]\n    best=None\n    for x in nums:\n"
                "        best = x if best is None or x > best else best\n"
                "        out.append(str(best))\n    return out\n",
        "order": "def solve(nums):\n    out=[]\n    best=None\n    for x in nums:\n"
                 "        best = x if best is None or x > best else best\n"
                 "        out.append(best)\n    return list(reversed(out))\n",
        "extra": "def solve(nums):\n    out=[]\n    best=None\n    for x in nums:\n"
                 "        best = x if best is None or x > best else best\n"
                 "        out.append(best)\n    return (out, 'done')\n",
    },
    {
        "name": "count_vowels",
        "spec": "count lower/upper case vowels a e i o u",
        "sig": ["s"],
        "cases": [["Ada Lovelace"], ["xyz"], ["AEIOU"], ["moon"]],
        "correct": "def solve(s):\n    n = 0\n    for ch in s:\n"
                   "        if ch.lower() in 'aeiou':\n            n += 1\n    return n\n",
        "alt": "def solve(s):\n    return sum(1 for ch in s.lower() if ch in 'aeiou')\n",
        "buggy": "def solve(s):\n    n = 0\n    for ch in s:\n"
                 "        if ch in 'aeio':\n            n += 1\n    return n\n",
        "boundary": "def solve(s):\n    n = 0\n    for ch in s:\n"
                    "        if ch in 'aeiou':\n            n += 1\n    return n\n",
        "off1": "def solve(s):\n    n = 0\n    for ch in s[:-1]:\n"
                "        if ch.lower() in 'aeiou':\n            n += 1\n    return n\n",
        "type": "def solve(s):\n    n = 0\n    for ch in s:\n"
                "        if ch.lower() in 'aeiou':\n            n += 1\n    return str(n)\n",
        "extra": "def solve(s):\n    n = 0\n    for ch in s:\n"
                 "        if ch.lower() in 'aeiou':\n            n += 1\n    return (n, len(s))\n",
    },
    {
        "name": "chunk",
        "spec": "split a list into consecutive chunks of size k, keeping the remainder",
        "sig": ["items", "k"],
        "cases": [[[1, 2, 3, 4, 5], 2], [[1, 2, 3, 4], 2], [[7], 3], [[], 2]],
        "correct": "def solve(items, k):\n    return [items[i:i+k] for i in range(0, len(items), k)]\n",
        "alt": "def solve(items, k):\n    out = []\n    while items:\n"
               "        out.append(items[:k])\n        items = items[k:]\n    return out\n",
        "buggy": "def solve(items, k):\n    out = []\n    i = 0\n"
                 "    while i + k <= len(items):\n        out.append(items[i:i+k])\n        i += k\n"
                 "    return out\n",
        "boundary": "def solve(items, k):\n    if not items:\n        return [[]]\n"
                    "    return [items[i:i+k] for i in range(0, len(items), k)]\n",
        "off1": "def solve(items, k):\n    return [items[i:i+k+1] for i in range(0, len(items), k)]\n",
        "type": "def solve(items, k):\n    return str([items[i:i+k] for i in range(0, len(items), k)])\n",
        "order": "def solve(items, k):\n    return list(reversed([items[i:i+k] for i in range(0, len(items), k)]))\n",
        "extra": "def solve(items, k):\n    out = [items[i:i+k] for i in range(0, len(items), k)]\n"
                 "    return out + [[]]\n",
    },
    {
        "name": "safe_div",
        "spec": "return a/b as a float, or null when b is zero",
        "sig": ["a", "b"],
        "cases": [[7, 2], [0, 5], [9, 0], [-8, 4], [10, -2]],
        "correct": "def solve(a, b):\n    if b == 0:\n        return None\n    return a / b\n",
        "alt": "def solve(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return None\n",
        "buggy": "def solve(a, b):\n    return a / b\n",
        "boundary": "def solve(a, b):\n    if b <= 0:\n        return None\n    return a / b\n",
        "off1": "def solve(a, b):\n    if b == 0:\n        return None\n    return a / b + 0.1\n",
        "type": "def solve(a, b):\n    if b == 0:\n        return None\n    return str(a / b)\n",
        "order": "def solve(a, b):\n    if a == 0:\n        return None\n    return b / a\n",
        "extra": "def solve(a, b):\n    if b == 0:\n        return None\n    return (a / b, a % b)\n",
    },
    {
        "name": "dedupe",
        "spec": "remove duplicates while preserving first-occurrence order",
        "sig": ["xs"],
        "cases": [[[3, 1, 3, 2, 1]], [[0, 5, 0]], [[4, 4, 4]], [[9]]],
        "correct": "def solve(xs):\n    out = []\n    for x in xs:\n"
                   "        if x not in out:\n            out.append(x)\n    return out\n",
        "alt": "def solve(xs):\n    return list(dict.fromkeys(xs))\n",
        "buggy": "def solve(xs):\n    return sorted(set(xs))\n",
        "boundary": "def solve(xs):\n    out = []\n    for x in xs:\n"
                    "        if x and x not in out:\n            out.append(x)\n    return out\n",
        "off1": "def solve(xs):\n    out = []\n    for x in xs[1:]:\n"
                "        if x not in out:\n            out.append(x)\n    return out\n",
        "type": "def solve(xs):\n    out = []\n    for x in xs:\n"
                "        if x not in out:\n            out.append(x)\n    return str(out)\n",
        "order": "def solve(xs):\n    out = []\n    for x in xs:\n"
                 "        if x not in out:\n            out.append(x)\n    return sorted(out)\n",
        "extra": "def solve(xs):\n    out = []\n    for x in xs:\n"
                 "        if x not in out:\n            out.append(x)\n    return out + ([out[-1]] if out else [])\n",
    },
]

_HARNESS = r'''
import json, sys
payload = json.load(sys.stdin)
src = payload["src"]
tests = payload["tests"]
ns = {}
exec(compile(src, "<candidate>", "exec"), ns)
fn = ns.get("solve")
out = []
for args in tests:
    try:
        if fn is None:
            raise NameError("solve is not defined")
        out.append({"ok": True, "value": fn(*args)})
    except Exception as e:
        out.append({"ok": False, "error": type(e).__name__})
print(json.dumps(out, default=str))
'''

# Strategy B for the harness differential experiment: run the whole suite twice
# in the same subprocess and require both passes to agree.  A candidate whose
# output depends on call history (a module-level counter, an arity memo) is
# caught when the second pass diverges from the first.
_HARNESS_TWICE = r'''
import json, sys
payload = json.load(sys.stdin)
src = payload["src"]
tests = payload["tests"]
ns = {}
exec(compile(src, "<candidate>", "exec"), ns)
fn = ns.get("solve")

def run_pass():
    out = []
    for args in tests:
        try:
            if fn is None:
                raise NameError("solve is not defined")
            out.append({"ok": True, "value": fn(*args)})
        except Exception as e:
            out.append({"ok": False, "error": type(e).__name__})
    return out

first = run_pass()
second = run_pass()
out = []
for a, b in zip(first, second):
    if not a.get("ok"):
        out.append(a)
    elif not b.get("ok"):
        out.append({"ok": False,
                    "error": "unstable: " + str(b.get("error")) + " on repeat"})
    elif a.get("value") != b.get("value"):
        out.append({"ok": False,
                    "error": "unstable: repeated run gave a different value"})
    else:
        out.append(a)
print(json.dumps(out, default=str))
'''

_BANNED = ("import os", "import sys", "subprocess", "open(", "__import__", "eval(", "exec(")


def _num_eq(exp, got, rel=1e-9):
    if isinstance(exp, bool) or isinstance(got, bool):
        return exp is got
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        if exp == got:
            return True
        denom = max(1e-12, abs(exp))
        return abs(exp - got) <= rel * denom
    if isinstance(exp, list) and isinstance(got, list):
        return len(exp) == len(got) and all(_num_eq(a, b, rel) for a, b in zip(exp, got))
    return exp == got


class CodePatch(Family):
    name = "code_patch"
    domain = "software engineering"
    task_shape = "repair a buggy Python function against a hidden test harness"
    premise = "unit tests are executable ground truth; code runs in an isolated subprocess"
    scoring = "fraction of unit tests that pass"
    item_unit = "one unit test"
    payload_kind = "list"

    def make_one(self, rng, idx):
        t = rng.choice(_CODE_TEMPLATES)
        return self.task(f"code_patch-{idx:03d}",
                         f"Fix the function below so that it satisfies: {t['spec']}.  "
                         "Return the full module source defining solve.\n\n" + t["buggy"],
                         [{"unit": f"t{i + 1}", "expected": None, "case_index": i}
                          for i in range(len(t["cases"]))],
                         {"template": t["name"], "sig": t["sig"]})

    def _expected(self, task):
        t = next(x for x in _CODE_TEMPLATES if x["name"] == task.meta["template"])
        fn = {}
        exec(compile(t["correct"], "<ref>", "exec"), fn)
        return [fn["solve"](*args) for args in t["cases"]]

    def canonical(self, task):
        t = next(x for x in _CODE_TEMPLATES if x["name"] == task.meta["template"])
        return t["correct"]

    def _variant(self, task, key):
        t = next(x for x in _CODE_TEMPLATES if x["name"] == task.meta["template"])
        return t.get(key, "")

    def equivalents(self, task, rng):
        return [(self._variant(task, "alt"), "equivalent implementation")]

    def wrongs(self, task, rng):
        return [("boundary", self._variant(task, "boundary"), "edge-case handling broken"),
                ("off_by_one", self._variant(task, "off1"), "off-by-one in the loop"),
                ("type_mismatch", self._variant(task, "type"), "wrong return type"),
                ("order", self._variant(task, "order"), "output order changed"),
                ("missing", "", "function body removed"),
                ("extra", self._variant(task, "extra"), "extra value returned"),
                ("semantic_wrong", self._variant(task, "buggy"), "original buggy implementation")]

    def partial(self, task, j, rng):
        expected = self._expected(task)
        cases = next(x for x in _CODE_TEMPLATES
                     if x["name"] == task.meta["template"])["cases"]
        table = ",\n    ".join(f"{repr(tuple(a))!r}: {expected[i]!r}"
                               for i, a in enumerate(cases[:j]))
        return ("def solve(*args):\n    table = {\n    " + table +
                "\n    }\n    return table.get(repr(args), '__wrong__')\n")

    def _verify_with(self, task, candidate: Candidate, harness: str) -> Verdict:
        t0 = time.perf_counter()
        src = candidate.payload
        evidence = []
        if not isinstance(src, str) or len(src) > 4000:
            for it in task.items:
                evidence.append({"unit": it["unit"], "ok": False,
                                 "detail": "candidate is not Python source"})
            return Verdict(False, 0.0, evidence, (time.perf_counter() - t0) * 1000)
        if any(b in src for b in _BANNED):
            for it in task.items:
                evidence.append({"unit": it["unit"], "ok": False,
                                 "detail": "candidate uses a banned construct"})
            return Verdict(False, 0.0, evidence, (time.perf_counter() - t0) * 1000)
        tpl = next(x for x in _CODE_TEMPLATES if x["name"] == task.meta["template"])
        expected = self._expected(task)
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", harness],
                input=json.dumps({"src": src, "tests": tpl["cases"]}),
                capture_output=True, text=True, timeout=3)
            results = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else []
        except Exception as ex:
            results = []
            err = f"runner failed: {type(ex).__name__}"
        else:
            err = "process exited with status %s" % proc.returncode
        passed = 0
        for i, it in enumerate(task.items):
            r = results[i] if i < len(results) else None
            if r is None or not r.get("ok"):
                detail = (r or {}).get("error", err)
                evidence.append({"unit": it["unit"], "ok": False, "detail": str(detail)})
                continue
            if _num_eq(expected[i], r["value"]):
                passed += 1
                evidence.append({"unit": it["unit"], "ok": True, "detail": "test passed"})
            else:
                evidence.append({"unit": it["unit"], "ok": False,
                                 "detail": f"expected {expected[i]!r}, got {r['value']!r}"})
        n = len(task.items)
        score = passed / n if n else 0.0
        return Verdict(passed == n and n > 0, score, evidence,
                       (time.perf_counter() - t0) * 1000)

    def verify(self, task, candidate: Candidate) -> Verdict:
        """Production strategy A: each case called once, single subprocess."""
        return self._verify_with(task, candidate, _HARNESS)

    def verify_twice(self, task, candidate: Candidate) -> Verdict:
        """Strategy B: the suite runs twice in-process; a changed or failed
        second pass rejects.  Used by the harness differential experiment."""
        return self._verify_with(task, candidate, _HARNESS_TWICE)

    def grade_item(self, task, item, answer):  # pragma: no cover - verify is overridden
        return False, "code_patch uses verify()"
