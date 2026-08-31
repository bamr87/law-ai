#!/usr/bin/env python3
"""UX / navigation contract audit for the Law AI frontend.

The mechanical half of the repeatable UI/UX review (`/ux-review`). The human
half — flows, copy, information hierarchy — lives in
[docs/ui-ux-review.md](../docs/ui-ux-review.md); this file checks only the
rules a machine can check, so a review pass spends its attention on judgement
instead of on grepping.

Every rule below encodes a regression that actually shipped, or that the
spec 041 shell rework removed and must not get back:

  R1  one scroller       — ad-hoc `overflow-auto` instead of the shell classes
  R2  viewport height    — a screen claiming the viewport the shell owns
  R3  one <main>         — pages nesting a second main landmark
  R4  z-index scale      — hand-written z-indexes that fight the shell
  R5  focus indicator    — `focus:outline-none` with nothing put back
  R6  landmark labels    — an unnamed <nav>/<aside>
  R7  page frame         — a route not using PageLayout without saying why
  R8  route states       — a route group with no loading/error/not-found
  R9  sticky offsets     — a magic `top-<n>` instead of the sticky stack
  R10 composite widgets  — a tablist/radiogroup with no name, or tabs with
                           no panel association
  R11 control names      — a form control whose only name is a placeholder

Opt out of *all* rules for one file by putting `ux-audit: exempt — <reason>`
in a comment in it; opt one page out of R7 with `ux-audit: bare-page —
<reason>`. Both require a reason on the same line, so an exemption is always
self-documenting.

Host stdlib only, no container — same class of gate as spec_validator.py and
backlog_lint.py.

Usage::

    python3 scripts/ux_audit.py            # audit frontend/
    python3 scripts/ux_audit.py --list     # print the rules and exit
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
APP = FRONTEND / "app"
APP_GROUP = APP / "(app)"
COMPONENTS = FRONTEND / "components"
SHELL = COMPONENTS / "shell"

# The shell itself owns the viewport and the only <main>; it is measured
# against the rules it defines, not against the rules for screens.
SHELL_OWNER = SHELL / "AppShell.tsx"

EXEMPT_RE = re.compile(r"ux-audit:\s*exempt\s*[—-]\s*\S")
BARE_PAGE_RE = re.compile(r"ux-audit:\s*bare-page\s*[—-]\s*\S")

# `<nav …>` / `<aside …>` opening tags. JSX attribute values containing a bare
# `>` would truncate the match; none exist today and a truncated match fails
# loudly rather than passing silently.
LANDMARK_RE = re.compile(r"<(nav|aside)\b(.*?)>", re.S)


@dataclass
class Finding:
    path: Path
    line: int
    rule: str
    message: str


@dataclass
class Audit:
    findings: list[Finding] = field(default_factory=list)
    exempted: list[tuple[Path, str]] = field(default_factory=list)
    checked: int = 0

    def add(self, path: Path, line: int, rule: str, message: str) -> None:
        self.findings.append(Finding(path, line, rule, message))


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _sources(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix in {".ts", ".tsx"} and "node_modules" not in p.parts
    )


def _strip_comments(text: str) -> str:
    """Blank out block and line comments so prose about a rule never trips it."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def rule_scroll_containers(path: Path, lines: list[str], audit: Audit) -> None:
    """R1 — one scroller. Content scrolls in `.shell-scroll`; panels use
    `.shell-panel-scroll`. Both contain overscroll and share a scrollbar, which
    an ad-hoc `overflow-auto` does not."""
    for i, line in enumerate(lines, 1):
        if "overflow-auto" not in line and "overflow-y-auto" not in line:
            continue
        if "shell-scroll" in line or "shell-panel-scroll" in line:
            continue
        # <pre>/code blocks legitimately need horizontal scroll, which the
        # panel class deliberately clips.
        if "<pre" in line or "whitespace-pre" in line:
            continue
        audit.add(path, i, "R1", "ad-hoc scroll container — use shell-panel-scroll")


def rule_viewport_height(path: Path, lines: list[str], audit: Audit) -> None:
    """R2 — only the shell claims the viewport. A screen sizing itself to
    `h-dvh`/`h-screen` inside a viewport-locked shell either overflows its
    region or double-scrolls. `max-h-[calc(100dvh…)]` is a measurement, not a
    claim, and is allowed."""
    if path == SHELL_OWNER or path.parent == APP and path.name == "not-found.tsx":
        return
    pattern = re.compile(r"\b(?:min-)?h-(?:screen|dvh)\b")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            audit.add(path, i, "R2", "screen claims the viewport the shell owns")


def rule_single_main(path: Path, lines: list[str], audit: Audit) -> None:
    """R3 — one <main>. The shell renders it; a page that renders another
    nests the landmark and breaks the skip link."""
    if path == SHELL_OWNER or (path.parent == APP and path.name == "not-found.tsx"):
        return
    for i, line in enumerate(lines, 1):
        if "<main" in line:
            audit.add(path, i, "R3", "second <main> landmark — the shell owns it")


def rule_z_scale(path: Path, lines: list[str], audit: Audit) -> None:
    """R4 — z-index comes off the scale in `frontend/ui/layout.css`. A literal
    is a number that has no idea the drawer sits at 60."""
    pattern = re.compile(r"(?<![-\w])z-(?:\[\d|\d)")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            audit.add(path, i, "R4", "literal z-index — use a --z-* token")


def rule_focus_indicator(path: Path, lines: list[str], audit: Audit) -> None:
    """R5 — never remove focus without putting an indicator back."""
    for i, line in enumerate(lines, 1):
        if "focus:outline-none" not in line:
            continue
        if any(k in line for k in ("focus-ring", "focus-visible:outline", "focus:ring")):
            continue
        audit.add(path, i, "R5", "focus removed with no ring — add focus-ring")


def rule_landmark_labels(path: Path, text: str, audit: Audit) -> None:
    """R6 — every <nav>/<aside> is named. Three unnamed navigations sound
    identical to a screen-reader user."""
    for m in LANDMARK_RE.finditer(text):
        attrs = m.group(2)
        if "aria-label" in attrs or "aria-labelledby" in attrs:
            continue
        line = text.count("\n", 0, m.start()) + 1
        audit.add(path, line, "R6", f"<{m.group(1)}> landmark has no accessible name")


def rule_sticky_offsets(path: Path, lines: list[str], audit: Audit) -> None:
    """R9 — sticky things park on the shell's stack, not on a magic number
    that silently desynchronises when the header height changes."""
    pattern = re.compile(r"sticky\s+(?:[a-z]+:)?top-\d")
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            audit.add(
                path, i, "R9", "magic sticky offset — use shell-sticky-* or a token"
            )


COMPOSITE_GROUPS = ("tablist", "radiogroup", "listbox", "menu", "tree")

CONTROL_TAGS = ("input", "textarea", "select")


def _jsx_tags(text: str, names: tuple[str, ...]) -> list[tuple[int, str]]:
    """Yield (offset, attribute-text) for each opening JSX tag in `names`.

    Brace-aware on purpose. A naive ``<input[^>]*>`` regex truncates at the
    ``>`` inside ``onChange={(e) => ...}``, so it reports controls as unlabeled
    whenever an arrow function precedes their ``aria-label`` — the exact false
    positive that would get this rule deleted.
    """
    out: list[tuple[int, str]] = []
    for name in names:
        needle = "<" + name
        i = 0
        while True:
            i = text.find(needle, i)
            if i == -1:
                break
            nxt = text[i + len(needle) : i + len(needle) + 1]
            if nxt and (nxt.isalnum() or nxt in "_-"):
                i += len(needle)
                continue
            j, depth, quote = i + len(needle), 0, ""
            while j < len(text):
                c = text[j]
                if quote:
                    if c == quote:
                        quote = ""
                elif c in "\"'":
                    quote = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                elif c == ">" and depth == 0:
                    break
                j += 1
            out.append((i, text[i + len(needle) : j]))
            i = j if j > i else i + len(needle)
    return out


def rule_control_names(path: Path, text: str, audit: Audit) -> None:
    """R11 — a placeholder is not a label.

    It disappears the moment the user types, is not reliably announced, and
    fails WCAG 3.3.2. A control needs `aria-label`, `aria-labelledby`, or an
    `id` a `<label htmlFor>` in the same file points at. An implicit
    `<label>` wrapper also counts, which is why a wrapped control with no
    attributes at all is left alone — only `placeholder`-bearing controls are
    flagged, and those are never the wrapped-label idiom in this codebase.
    """
    for offset, attrs in _jsx_tags(text, CONTROL_TAGS):
        if "placeholder" not in attrs:
            continue
        if "aria-label" in attrs or "aria-labelledby" in attrs:
            continue
        m = re.search(r'id="([^"]+)"', attrs)
        if m and f'htmlFor="{m.group(1)}"' in text:
            continue
        line = text.count("\n", 0, offset) + 1
        audit.add(path, line, "R11", "control named only by its placeholder")


def rule_composite_widgets(path: Path, text: str, audit: Audit) -> None:
    """R10 — a composite widget announces itself or it is noise.

    A `role="tablist"` with no accessible name is "tab list" to a screen
    reader, and three of them on a page are indistinguishable. A `role="tab"`
    with no `aria-controls` never tells the user what it switches.

    The keyboard half of the pattern (one tab stop, arrows move within) is
    behavioural and is covered by `frontend/__tests__/shell/` instead — a
    static check cannot see whether a handler actually moves focus.
    """
    for m in re.finditer(r'role="(%s)"' % "|".join(COMPOSITE_GROUPS), text):
        role = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        # The element's own attributes: scan the tag this role sits in.
        start = text.rfind("<", 0, m.start())
        end = text.find(">", m.end())
        tag = text[start : end + 1] if start != -1 and end != -1 else ""
        if "aria-label" not in tag and "aria-labelledby" not in tag:
            audit.add(
                path, line, "R10", f'role="{role}" has no accessible name'
            )

    for m in re.finditer(r'role="tab"', text):
        line = text.count("\n", 0, m.start()) + 1
        start = text.rfind("<", 0, m.start())
        end = text.find(">", m.end())
        tag = text[start : end + 1] if start != -1 and end != -1 else ""
        if "aria-controls" not in tag:
            audit.add(
                path, line, "R10", 'role="tab" has no aria-controls panel'
            )


def rule_page_frame(audit: Audit) -> None:
    """R7 — every route uses PageLayout so the sticky header, gutters, and
    reading width are the same everywhere."""
    for page in sorted(APP_GROUP.rglob("page.tsx")):
        text = page.read_text(encoding="utf-8")
        if BARE_PAGE_RE.search(text) or EXEMPT_RE.search(text):
            audit.exempted.append((page, "bare page"))
            continue
        # `<PageLayout`, not a bare mention: a comment naming the component
        # must not satisfy the rule.
        if "<PageLayout" not in text:
            audit.add(page, 1, "R7", "route does not use PageLayout")


def rule_route_states(audit: Audit) -> None:
    """R8 — a route group without loading/error states fails by going blank."""
    for name, why in (
        ("loading.tsx", "navigation shows no progress"),
        ("error.tsx", "a thrown error takes the whole shell down"),
    ):
        if not (APP_GROUP / name).is_file():
            audit.add(APP_GROUP / name, 1, "R8", f"missing — {why}")
    if not (APP / "not-found.tsx").is_file():
        audit.add(APP / "not-found.tsx", 1, "R8", "missing — 404s render unstyled")


RULES = [
    ("R1", "one scroller: no ad-hoc overflow-auto"),
    ("R2", "viewport height: only the shell claims it"),
    ("R3", "one <main> landmark"),
    ("R4", "z-index comes off the --z-* scale"),
    ("R5", "focus is never removed without a ring"),
    ("R6", "every <nav>/<aside> has an accessible name"),
    ("R7", "every route uses PageLayout"),
    ("R8", "route group ships loading/error/not-found"),
    ("R9", "sticky offsets use the shell stack"),
    ("R10", "composite widgets are named and tabs point at panels"),
    ("R11", "no form control is named only by its placeholder"),
]


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for rule, desc in RULES:
            print(f"{rule}  {desc}")
        return 0

    if not FRONTEND.is_dir():
        print(f"FAIL: {_rel(FRONTEND)} not found")
        return 1

    audit = Audit()
    for path in _sources(APP) + _sources(COMPONENTS):
        raw = path.read_text(encoding="utf-8")
        if EXEMPT_RE.search(raw):
            reason = EXEMPT_RE.search(raw)
            audit.exempted.append((path, raw[reason.start() : reason.end() + 60].strip()))
            continue
        audit.checked += 1
        text = _strip_comments(raw)
        lines = text.split("\n")
        rule_scroll_containers(path, lines, audit)
        rule_viewport_height(path, lines, audit)
        rule_single_main(path, lines, audit)
        rule_z_scale(path, lines, audit)
        rule_focus_indicator(path, lines, audit)
        rule_landmark_labels(path, text, audit)
        rule_sticky_offsets(path, lines, audit)
        rule_composite_widgets(path, text, audit)
        rule_control_names(path, text, audit)

    rule_page_frame(audit)
    rule_route_states(audit)

    for path, reason in audit.exempted:
        print(f"note: {_rel(path)} exempt ({reason.splitlines()[0]})")

    if audit.findings:
        print()
        for f in sorted(audit.findings, key=lambda f: (str(f.path), f.line)):
            print(f"{_rel(f.path)}:{f.line}: {f.rule} {f.message}")
        print(
            f"\nFAIL: {len(audit.findings)} UX contract violation(s) "
            f"across {audit.checked} file(s). "
            "See docs/ui-ux-review.md; run scripts/ux_audit.py --list for the rules."
        )
        return 1

    print(f"OK: {audit.checked} frontend file(s) satisfy the UX contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
