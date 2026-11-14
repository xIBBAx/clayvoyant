"""Check that nothing solid passes through anything else in a clay project.

    python tools/check_contacts.py examples/the-fast-one             # every drawing of the last filming
    python tools/check_contacts.py examples/the-fast-one --plan      # the planned shots, before filming
    python tools/check_contacts.py examples/nineteen-thirty --shots the_call_s03 --json report.json

Blender poses every drawing exactly as filming does and draws nothing. Every visible character is measured triangle
against triangle with the set and the props (as drawn: bevels, lumps, a pressed cushion), with every other character,
and with its own body away from its joints; a hand or a foot whose path between two drawings runs through something
is reported too. Touching is fine; anything inside is listed with the shot, the frame, the character, the part, what it
is in and how deep. Exit status: 0 clean, 1 contacts, 2 the check could not finish (never counted as clean).
The same check is `sastudio check PROJECT` (planned shots) and `sastudio check PROJECT --filmed`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project")
    ap.add_argument("--every", type=int, default=1, help="measure every Nth drawing of each shot (default: every one)")
    ap.add_argument("--shots", default="", help="only shots whose name contains this")
    ap.add_argument("--plan", action="store_true", help="check the planned shots (timed from the words) instead of the last filming")
    ap.add_argument("--jobs", type=int, default=2, help="Blenders at once (default 2; each needs about a gigabyte)")
    ap.add_argument("--json", help="write every contact to this file")
    a = ap.parse_args()
    from sastudio.stopmotion import check as C

    if a.plan:
        from sastudio.project import load_project

        jobs = C.planned_jobs(load_project(Path(a.project)), shots=a.shots)
    else:
        jobs = C.filmed_jobs(Path(a.project), a.shots)
        jobs = [(lb, j) for lb, j in jobs if not lb.endswith("_silent")]
    if not jobs:
        print(f"No shots to check in {a.project}: film it first (sastudio film {a.project}), or use --plan.")
        return 2
    rep = C.check(jobs, every=a.every, workers=a.jobs)
    for c in rep.contacts:
        print("  " + C.said(c))
    print(f"\n{len(rep.shots)} shots, {rep.drawings} drawings checked: {len(rep.contacts)} contact(s)."
          + (f" {len(rep.failed)} shot(s) could not be checked: {', '.join(s.label for s in rep.failed)}." if rep.failed else ""))
    for n, words in C.summary(rep.contacts):
        print(f"  {n:5}  {words}")
    if a.json:
        Path(a.json).write_text(json.dumps({"contacts": rep.contacts, "failed": {s.label: s.error for s in rep.failed},
                                            "drawings": rep.drawings}, indent=1), "utf-8")
    return rep.exit_code()


if __name__ == "__main__":
    sys.exit(main())
