#!/usr/bin/env python3
# Stack-Dump -> Traceback for LINOX / ReTi-Code
#
# Usage:  python stacktrace.py <labels_file> <dump_file>      (dump_file "-" or omitted: stdin)
#
# Dump format: every integer in the text is one stack cell, TOP of stack first
# (like STACK_DUMP prints it). Other text / line prefixes are ignored.
#
# Frame layout (see kernel/doc.md, stack_call_labels.txt), n = argument count, bottom -> top:
#   [IN1][M0..M9][arg1..argn][n][absolute return address]      -> 13 + n cells
# Return address = index of the instruction right after "JUMP CALL" (index in the
# compiled file without comments / empty lines / labels). The 5 instructions of a call are:
#   LOADI *CALLEE / STORE 1024 / MOVE PC ACC / STORE 1025 / JUMP CALL
# so  code[ret-1] == "JUMP CALL"  and  code[ret-5] == "LOADI *CALLEE".

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labels as lp

FRAME_BASE = 13  # frame size without arguments
MAX_ARGS = 64    # plausibility limit for the argument count


class Program:
    def __init__(self, labels_path: str):
        code = lp.getCode(labels_path)
        entries = lp.findLabels(code)
        self.code: list[str] = []            # instruction text by index
        self.labels_at: dict[int, list[str]] = {}
        for idx, line, lbls in entries:
            if idx == -1:
                continue
            # strip trailing comment, normalize whitespace
            text = " ".join(line.split("#")[0].split())
            self.code.append(text)
            if lbls:
                self.labels_at[idx] = lbls
        self.label_idx = {l: i for i, ls in self.labels_at.items() for l in ls}

        # function labels = every label referenced via "LOADI *LABEL"
        self.func_labels: set[str] = set()
        for text in self.code:
            m = re.match(r"LOADI\s+\*(\w+)", text, re.I)
            if m and m.group(1) in self.label_idx:
                self.func_labels.add(m.group(1))
        self.func_starts = sorted({self.label_idx[l] for l in self.func_labels})

    # --- helpers -------------------------------------------------------
    def is_call_return(self, r: int) -> bool:
        return (5 <= r <= len(self.code)
                and self.code[r - 1].upper() == "JUMP CALL"
                and re.match(r"LOADI\s+\*\w+", self.code[r - 5], re.I) is not None)

    def callee(self, r: int) -> str:
        return re.match(r"LOADI\s+\*(\w+)", self.code[r - 5], re.I).group(1)

    def func_at(self, idx: int) -> str:
        """Name of the function containing instruction idx."""
        best = None
        for s in self.func_starts:
            if s <= idx:
                best = s
        if best is None:
            return self.near_label(idx)[0]
        return next(l for l in self.labels_at[best] if l in self.func_labels)

    def near_label(self, idx: int) -> tuple[str, int]:
        for i in range(idx, -1, -1):
            if i in self.labels_at:
                return self.labels_at[i][-1], idx - i
        return "?", idx


def parse_dump(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"-?\d+", text)]


def find_frames(prog: Program, stack: list[int]):
    """stack: bottom -> top. Returns frames (bottom -> top) and warnings."""
    n_cells = len(stack)
    # candidate return-address cells p: stack[p]=ret, stack[p-1]=argcount
    cands = []
    for p in range(1, n_cells):
        r, n = stack[p], stack[p - 1]
        if not (0 <= n <= MAX_ARGS):
            continue
        f = p - 12 - n
        if f < 0:
            continue
        if prog.is_call_return(r) or r in prog.func_starts:
            cands.append(p)

    frames = []
    warnings = []
    limit = n_cells  # exclusive upper bound for p
    cand_set = sorted(cands, reverse=True)
    upper_func = None       # function that the frame above this one lives in
    while True:
        usable = [p for p in cand_set if p < limit]
        if not usable:
            break
        pick = None
        if upper_func is not None:
            for p in usable:
                r = stack[p]
                if prog.is_call_return(r) and prog.callee(r) == upper_func:
                    pick = p
                    break
                if r in prog.func_starts and prog.func_at(r) == upper_func:
                    pick = p  # process entry frame (prepared by the scheduler)
                    break
            if pick is None:
                # fall back: highest candidate, flag inconsistency
                pick = usable[0]
                warnings.append(
                    f"Frame bei Stack-Index {pick}: Aufrufer passt nicht zur Kette "
                    f"(erwartet Callee '{upper_func}'), evtl. Fehlalarm / Offset."
                )
        else:
            pick = usable[0]

        r, n = stack[pick], stack[pick - 1]
        f = pick - 12 - n
        frame = dict(pos=f, ret=r, nargs=n, args=stack[f + 11:f + 11 + n])
        if prog.is_call_return(r):
            frame["callee"] = prog.callee(r)
            frame["site"] = r - 1
            frame["caller"] = prog.func_at(r - 1)
            upper_func = frame["caller"]
        else:  # process entry (stack prepared by SCHEDULER_PREPARE_PROCESS_STACK)
            frame["callee"] = prog.func_at(r)
            frame["site"] = None
            frame["caller"] = None
            upper_func = None
        frames.append(frame)
        limit = f
        if frame["site"] is None:
            break
    frames.reverse()

    # report cells between frames that don't belong to any frame (own pushes of functions)
    return frames, warnings


def traceback(dump_text: str, labels_path: str) -> str:
    prog = Program(labels_path)
    top_first = parse_dump(dump_text)
    stack = list(reversed(top_first))
    frames, warnings = find_frames(prog, stack)

    out = ["Traceback (most recent call last):"]
    if not frames:
        out.append("  (keine gueltigen Call-Frames im Dump gefunden)")
    prev_end = 0
    for fr in frames:
        if fr["site"] is None:
            out.append(f"  [Prozess-Einstieg] {fr['callee']}  (Entry {fr['ret']})"
                       + _args(fr))
        else:
            lbl, off = prog.near_label(fr["site"])
            out.append(f"  in {fr['caller']} (Instr {fr['site']}, {lbl}+{off})")
            out.append(f"      -> CALL {fr['callee']}{_args(fr)}")
        gap = fr["pos"] - prev_end
        if gap > 0 and prev_end > 0:
            out.append(f"      ({gap} zusaetzliche Zelle(n) auf dem Stack vor diesem Frame: "
                       f"{stack[prev_end:fr['pos']]})")
        prev_end = fr["pos"] + FRAME_BASE + fr["nargs"]
    if frames:
        top_extra = len(stack) - prev_end
        out.append(f"  ... aktuell in {frames[-1]['callee']}"
                   + (f"  ({top_extra} Zelle(n) lokal auf dem Stack: {stack[prev_end:]})"
                      if top_extra else ""))
    if frames and frames[0]["pos"] > 0:
        out.append(f"  (Hinweis: {frames[0]['pos']} Zelle(n) unterhalb des untersten Frames, "
                   f"z.B. process-globale Werte)")
    for w in warnings:
        out.append("  WARNUNG: " + w)
    return "\n".join(out)


def _args(fr) -> str:
    return "(" + ", ".join(map(str, fr["args"])) + ")"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__ if __doc__ else "usage: stacktrace.py <labels_file> [dump_file]")
        sys.exit(1)
    labels_file = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] != "-":
        with open(sys.argv[2], encoding="utf-8") as f:
            dump = f.read()
    else:
        dump = sys.stdin.read()
    print(traceback(dump, labels_file))
