#!/usr/bin/env python3
"""Generate ``docs/reference/make-targets.md`` from the Makefile.

The Makefile is the only place a target's behaviour and its one-line
description live: ``make help`` carries the descriptions, grouped, and the
recipes carry the rest. This script renders both, plus the VS Code task in
``.vscode/tasks.json`` that runs each target, so AGENTS.md, README.md and the
other docs can link one generated page instead of hand-copying a command table
that drifts (UPS-DOC-05). Stdlib only — a host-sanctioned helper beside
``scripts/spec_validator.py``; it never imports the app.

    python3 scripts/gen_make_reference.py           # rewrite the page
    python3 scripts/gen_make_reference.py --check   # exit 1 when it is stale

``tests/test_make_reference.py`` runs ``--check`` in the root structural
suite, so a Makefile or tasks.json change that is not regenerated fails CI.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
MAKEFILE = REPO / "Makefile"
TASKS = REPO / ".vscode" / "tasks.json"
OUTPUT = REPO / "docs" / "reference" / "make-targets.md"
COMMAND = "python3 scripts/gen_make_reference.py"

TARGET_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?!=)")
ECHO_RE = re.compile(r'^\t@echo "(.*)"\s*$')
ENTRY_RE = re.compile(r"^\s+(make\s+\S.*?)\s+-\s+(.*)$")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*[:?+]?=")


def _cell(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").strip()


def parse_targets(lines: list[str]) -> dict[str, str]:
    """Map every target to the first sentence of the comment block above it."""
    targets: dict[str, str] = {}
    for i, line in enumerate(lines):
        match = TARGET_RE.match(line)
        if not match or match.group(1) == ".PHONY":
            continue
        comment: list[str] = []
        j = i - 1
        while j >= 0 and ASSIGN_RE.match(lines[j]):
            j -= 1
        while j >= 0 and lines[j].startswith("#"):
            body = lines[j].lstrip("#").strip()
            if body and set(body) <= {
                "-",
                "=",
            }:  # a `# ----` section rule ends the block
                break
            comment.insert(0, body)
            j -= 1
        text = " ".join(part for part in comment if part)
        first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0] if text else ""
        targets.setdefault(match.group(1), first)
    return targets


def parse_help(lines: list[str]) -> tuple[str, list[tuple[str, list[tuple[str, str]]]]]:
    """Return ``make help``'s title and its ``(section, [(command, description)])`` groups."""
    start = next(i for i, line in enumerate(lines) if line.startswith("help:"))
    title = ""
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        echo = ECHO_RE.match(line)
        if not echo:
            continue
        text = echo.group(1)
        entry = ENTRY_RE.match(text)
        if entry:
            if not sections:
                raise SystemExit("make help lists a command before any section header")
            sections[-1][1].append(
                (re.sub(r"\s+", " ", entry.group(1)), entry.group(2).strip())
            )
        elif text.strip().endswith(":") and not text.startswith(" "):
            sections.append((text.strip().rstrip(":"), []))
        elif text.strip() and not title:
            title = text.strip()
    return title, sections


def _strip_jsonc(text: str) -> str:
    """Drop ``//`` and ``/* */`` comments outside strings (tasks.json is JSONC)."""
    out: list[str] = []
    i, in_string = 0, False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\":
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def parse_tasks() -> dict[str, list[str]]:
    """Map a target name to the VS Code task labels whose command is ``make <target> …``."""
    if not TASKS.is_file():
        return {}
    data = json.loads(_strip_jsonc(TASKS.read_text(encoding="utf-8")))
    labels: dict[str, list[str]] = {}
    for task in data.get("tasks", []):
        command = str(task.get("command", ""))
        match = re.match(r"^make\s+([A-Za-z0-9][A-Za-z0-9_.-]*)", command)
        if match and task.get("label"):
            labels.setdefault(match.group(1), []).append(str(task["label"]))
    return labels


def render() -> str:
    lines = MAKEFILE.read_text(encoding="utf-8").splitlines()
    targets = parse_targets(lines)
    title, sections = parse_help(lines)
    tasks = parse_tasks()

    described: set[str] = set()
    unknown: list[str] = []
    for _, entries in sections:
        for command, _ in entries:
            name = command.split()[1]
            described.add(name)
            if name not in targets:
                unknown.append(name)
    if unknown:
        raise SystemExit(
            f"make help names targets the Makefile does not define: {sorted(set(unknown))}"
        )

    out = [
        f"<!-- GENERATED by {COMMAND} — do not edit by hand -->",
        "# Make targets",
        "",
        "> Every `make` target in the Makefile, grouped as `make help` groups them, with the VS Code task that runs it — generated from the Makefile and `.vscode/tasks.json`.",
        "",
        f"`make help` prints the same list ({_cell(title)}). Each target shells into `docker compose` unless its group says host; "
        "the rule is in [AGENTS.md](../../AGENTS.md) § Docker-First Workflow. "
        f"Edit the `help:` recipe or a target's comment in the [Makefile](../../Makefile), then run `{COMMAND}`.",
    ]
    for section, entries in sections:
        out += [
            "",
            f"## {section}",
            "",
            "| Command | What it does | VS Code task |",
            "| --- | --- | --- |",
        ]
        for command, description in entries:
            label = ", ".join(tasks.get(command.split()[1], []))
            out.append(
                f"| `{_cell(command)}` | {_cell(description)} | {_cell(label)} |"
            )

    rest = [name for name in targets if name not in described and name != "help"]
    if rest:
        out += [
            "",
            "## Not listed in `make help`",
            "",
            "Helpers and companions of the targets above. The note is the first sentence of the comment above the target in the Makefile, when it has one.",
            "",
            "| Command | Note | VS Code task |",
            "| --- | --- | --- |",
        ]
        for name in rest:
            out.append(
                f"| `make {name}` | {_cell(targets[name])} | {_cell(', '.join(tasks.get(name, [])))} |"
            )
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(
                f"{OUTPUT.relative_to(REPO)} is stale — run `{COMMAND}`",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {OUTPUT.relative_to(REPO)} is current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
