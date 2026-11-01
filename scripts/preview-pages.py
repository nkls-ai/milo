#!/usr/bin/env python3
"""Render every QML page and the controls gallery offscreen, light and dark, from brain/tests/desktop/page_samples,
then click through each sample's interactions and check the commands they send.

    cd brain && .venv/Scripts/python.exe ../scripts/preview-pages.py [--page TodayPage] [--output build/qml-shots/pages]

Screenshots go to <output>/<Name>-<state>-<light|dark>.png. Exits non-zero on a QML warning or a wrong command.
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from milo.desktop import qml_preview as q  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", action="append", help="only these samples (by file name)")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "qml-shots" / "pages")
    args = parser.parse_args()
    samples = {name: s for name, s in q.samples().items() if not args.page or name in args.page}
    shapes = q.wire_shapes()
    problems: list[str] = []
    q.application()
    for appearance in ("light", "dark"):
        q.set_appearance(appearance)
        for name, sample in samples.items():
            for state in sample["states"]:
                with q.Warnings() as warnings:
                    loaded = q.load_sample(sample, state)
                    path = loaded.grab(args.output / f"{name}-{state}-{appearance}.png")
                    loaded.close()
                problems += [f"{name}/{state}/{appearance}: {w}" for w in warnings.messages]
                print(path)
    q.set_appearance("light")
    for name, sample in samples.items():
        for i, interaction in enumerate(sample.get("interactions", [])):
            with q.Warnings() as warnings:
                loaded = q.load_sample(sample, interaction["state"])
                q.run_steps(loaded, interaction["steps"])
                if interaction.get("shot"):
                    loaded.grab(args.output / f"{name}-{interaction['shot']}-light.png")
                loaded.close()
            where = f"{name} interaction {i}"
            problems += [f"{where}: {w}" for w in warnings.messages]
            if loaded.commands != interaction.get("expect", []):
                problems.append(f"{where}: sent {loaded.commands}, expected {interaction.get('expect', [])}")
            for command in loaded.commands:
                problems += [f"{where}: {p}" for p in q.wire_problems(command, shapes)]
            actions = [list(a) for a in loaded.actions]
            if "actions" in interaction and actions != interaction["actions"]:
                problems.append(f"{where}: actions {actions}, expected {interaction['actions']}")
            print(f"{where}: {len(loaded.commands)} command(s)")
    for problem in problems:
        print("PROBLEM", problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
