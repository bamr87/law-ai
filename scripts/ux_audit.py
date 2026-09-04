#!/usr/bin/env python3
"""UX / navigation contract audit for Law AI's two front ends.

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
  R12 shared-CSS drift   — the two copies of base.css have diverged
  R13 LSAT parity drift  — a platform LSAT component with no static
                           counterpart and no stated reason

**Two surfaces, one contract.** `frontend/` is the platform shell;
`lsat-static/` is a Tailwind-free static export with no shell at all. The
*universal* rules (R3-R6, R9-R11) hold everywhere — a landmark needs a name and
a control needs a label whichever app it is in. The *shell* rules (R1, R2, R7,
R8) describe chrome the static site does not have and are checked on
`frontend/` only. Holding the static site to rules it structurally cannot
satisfy would teach everyone to ignore the audit.

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

# The static LSAT export. No shell, no routes, no Tailwind — universal rules
# only (see the module docstring).
LSAT_STATIC = REPO_ROOT / "lsat-static"
LSAT_STATIC_DIRS = [LSAT_STATIC / "app", LSAT_STATIC / "components"]

# Hand-written stylesheets. The static site expresses its whole layout in CSS
# rather than in class strings, so the z-scale and sticky-offset rules have to
# read CSS too or they simply do not apply to half the product.
STYLESHEETS = [
    FRONTEND / "ui" / "layout.css",
    FRONTEND / "ui" / "base.css",
    LSAT_STATIC / "app" / "globals.css",
]

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
    """R3 — one <main>, on the surface that owns it.

    On the platform the shell renders it, so a page rendering another nests the
    landmark and breaks the skip link. The static export has no shell, so its
    page is exactly where <main> belongs — checked separately by
    `rule_static_single_main`.
    """
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


def _inside_label(text: str, offset: int) -> bool:
    """True when `offset` sits inside a `<label>…</label>` wrapper.

    Implicit labelling — `<label><span class="sr-only">Name</span><input/></label>`
    — names a control just as well as `aria-label`, and `lsat-static` uses it.
    Compare the nearest preceding `<label` against the nearest preceding
    `</label>`: an opener that is more recent than the last closer means we are
    still inside one.
    """
    opener = text.rfind("<label", 0, offset)
    if opener == -1:
        return False
    closer = text.rfind("</label>", 0, offset)
    return opener > closer


def rule_control_names(path: Path, text: str, audit: Audit) -> None:
    """R11 — a placeholder is not a label.

    It disappears the moment the user types, is not reliably announced, and
    fails WCAG 3.3.2. A control needs `aria-label`, `aria-labelledby`, or an
    `id` a `<label htmlFor>` in the same file points at — or an enclosing
    `<label>` wrapper, which `lsat-static` uses with an `sr-only` span and
    which is every bit as valid.
    """
    for offset, attrs in _jsx_tags(text, CONTROL_TAGS):
        if "placeholder" not in attrs:
            continue
        if "aria-label" in attrs or "aria-labelledby" in attrs:
            continue
        m = re.search(r'id="([^"]+)"', attrs)
        if m and f'htmlFor="{m.group(1)}"' in text:
            continue
        if _inside_label(text, offset):
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


CSS_BLOCK_RE = re.compile(r"[^{}]*\{([^{}]*)\}")


def rule_css_layout(path: Path, text: str, audit: Audit) -> None:
    """R4 / R9 in stylesheets.

    `frontend/` writes layout in class strings, so scanning `.tsx` covers it.
    `lsat-static` writes layout in CSS, where a bare `z-index: 10` or a
    `top: 5rem` under `position: sticky` is the same defect and was previously
    invisible to this audit.

    `top: 0` is allowed: pinning to the top of the viewport is unambiguous and
    has nothing to desynchronise from.
    """
    for block in CSS_BLOCK_RE.finditer(text):
        body = block.group(1)
        block_line = text.count("\n", 0, block.start()) + 1

        for m in re.finditer(r"z-index:\s*([^;]+);", body):
            if "var(" in m.group(1):
                continue
            audit.add(
                path,
                block_line + body.count("\n", 0, m.start()),
                "R4",
                "literal z-index in CSS — use a --z-* token",
            )

        if not re.search(r"position:\s*sticky", body):
            continue
        for m in re.finditer(r"(?<![\w-])top:\s*([^;]+);", body):
            value = m.group(1).strip()
            if "var(" in value or value in {"0", "0px", "0rem", "auto"}:
                continue
            audit.add(
                path,
                block_line + body.count("\n", 0, m.start()),
                "R9",
                "magic sticky offset in CSS — key it off a token",
            )


def rule_static_single_main(paths: list[Path], audit: Audit) -> None:
    """R3, static surface — exactly one <main> across the whole export.

    The static site has no shell to own the landmark, so the rule is a count,
    not a location: zero means no main landmark and a dead skip link, more than
    one means an ambiguous one.
    """
    hits = [
        (p, _strip_comments(p.read_text(encoding="utf-8")).count("<main"))
        for p in paths
    ]
    total = sum(n for _, n in hits)
    if total == 1:
        return
    target = next((p for p, n in hits if n), paths[0] if paths else LSAT_STATIC)
    audit.add(
        target,
        1,
        "R3",
        f"static export declares {total} <main> landmarks, expected exactly 1",
    )


PLATFORM_LSAT = FRONTEND / "components" / "lsat"
#: Where a ported platform component may live. Spec 045's solve components
#: landed under `components/solve/`; spec 048's library components under
#: `components/library/`. The rule asks "is it ported", not "is it ported to
#: one blessed directory", so search the whole component tree.
STATIC_COMPONENTS = LSAT_STATIC / "components"
STATIC_PARITY_RE = re.compile(r"static-parity:\s*none\s*[—-]\s*\S")


def rule_lsat_parity(audit: Audit) -> None:
    """R13 — the two LSAT products drift only on purpose.

    Spec 045 shipped a hint carousel and five diagram types to the platform and
    nothing to the published static site, and no gate noticed for a week. The
    static export is the surface a prospective student reaches first, so a
    feature landing on only one side has to be a decision, not an oversight.

    A platform component under `frontend/components/lsat/` passes when either a
    same-named file exists anywhere under `lsat-static/components/`, or it carries
    `static-parity: none — <reason>`. Plenty of them legitimately cannot port —
    anything needing the provider chain or an API cannot run serverless — and
    saying so in one line is the whole ask.
    """
    if not PLATFORM_LSAT.is_dir():
        return
    ported = (
        {p.name for p in STATIC_COMPONENTS.rglob("*.tsx")}
        if STATIC_COMPONENTS.is_dir()
        else set()
    )
    for path in sorted(PLATFORM_LSAT.rglob("*.tsx")):
        if path.name in ported:
            continue
        text = path.read_text(encoding="utf-8")
        if STATIC_PARITY_RE.search(text):
            audit.exempted.append((path, "static-parity: none (declared)"))
            continue
        audit.add(
            path,
            1,
            "R13",
            "no lsat-static counterpart and no `static-parity: none — <reason>`",
        )


BASE_CSS = FRONTEND / "ui" / "base.css"
BASE_CSS_MIRROR = LSAT_STATIC / "app" / "base.css"


def rule_shared_css_mirror(audit: Audit) -> None:
    """R12 — the two front ends really do share one set of primitives.

    Next refuses to resolve a CSS `@import` outside an app's own root, so the
    static export cannot import `frontend/ui/base.css` across the repo (tried;
    Turbopack: "Module not found"). A committed mirror is the workable answer,
    and a mirror nobody checks is just a fork with extra steps — so this fails
    the build the moment they differ.
    """
    if not BASE_CSS.is_file() or not BASE_CSS_MIRROR.is_file():
        audit.add(BASE_CSS_MIRROR, 1, "R12", "shared base.css mirror is missing")
        return
    if BASE_CSS.read_bytes() != BASE_CSS_MIRROR.read_bytes():
        audit.add(
            BASE_CSS_MIRROR,
            1,
            "R12",
            "drifted from frontend/ui/base.css — run `make ui-sync`",
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
    ("R12", "the mirrored base.css copies are identical"),
    ("R13", "every platform LSAT component is ported or explains why not"),
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
    platform = [(p, True) for p in _sources(APP) + _sources(COMPONENTS)]
    static = [
        (p, False) for d in LSAT_STATIC_DIRS for p in _sources(d)
    ]

    for path, has_shell in platform + static:
        raw = path.read_text(encoding="utf-8")
        if EXEMPT_RE.search(raw):
            reason = EXEMPT_RE.search(raw)
            audit.exempted.append((path, raw[reason.start() : reason.end() + 60].strip()))
            continue
        audit.checked += 1
        text = _strip_comments(raw)
        lines = text.split("\n")

        # Universal — a landmark needs a name in either app.
        rule_z_scale(path, lines, audit)
        rule_focus_indicator(path, lines, audit)
        rule_landmark_labels(path, text, audit)
        rule_sticky_offsets(path, lines, audit)
        rule_composite_widgets(path, text, audit)
        rule_control_names(path, text, audit)

        # Shell-only — the static export has no `.shell-scroll` and no shell
        # that owns the viewport.
        if has_shell:
            rule_single_main(path, lines, audit)
            rule_scroll_containers(path, lines, audit)
            rule_viewport_height(path, lines, audit)

    for sheet in STYLESHEETS:
        if not sheet.is_file():
            continue
        audit.checked += 1
        rule_css_layout(sheet, sheet.read_text(encoding="utf-8"), audit)

    rule_shared_css_mirror(audit)
    rule_lsat_parity(audit)
    rule_static_single_main([p for p, _ in static], audit)
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
            f"across {audit.checked} file(s) in both front ends. "
            "See docs/ui-ux-review.md; run scripts/ux_audit.py --list for the rules."
        )
        return 1

    print(
        f"OK: {audit.checked} file(s) across both front ends satisfy the UX contract."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
