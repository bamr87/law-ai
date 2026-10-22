#!/usr/bin/env python3
"""Generate ``docs/reference/http-routes.md`` from the Django URLconf.

Every HTTP and WebSocket route the backend serves is declared in
``backend/law_ai/urls.py``, the URL modules it includes, and
``backend/law_ai/agentsapi/routing.py``. This script reads those files with
``ast`` — it never imports Django, so it runs on the host like
``scripts/spec_validator.py`` and needs no container — and renders one table
per mount: the route, the HTTP methods its view defines, the view, and the
first sentence of the view's docstring. Docs link the page instead of
re-listing routes by hand (UPS-DOC-05); ``docs/api-examples.md`` stays the
hand-written curl companion.

    python3 scripts/gen_route_reference.py           # rewrite the page
    python3 scripts/gen_route_reference.py --check   # exit 1 when it is stale

``tests/test_generated_reference.py`` runs ``--check`` in the root structural
suite, so a route added without regenerating the page fails CI.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
ROOT_URLCONF = "law_ai.urls"
WS_ROUTING = "law_ai.agentsapi.routing"
OUTPUT = REPO / "docs" / "reference" / "http-routes.md"
COMMAND = "python3 scripts/gen_route_reference.py"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


@dataclass
class Route:
    path: str
    methods: str
    view: str
    summary: str


def module_file(module: str) -> pathlib.Path:
    return BACKEND / (module.replace(".", "/") + ".py")


def resolve_module(base: str, node: ast.ImportFrom) -> str:
    """Absolute module name for ``from X import …`` written inside module ``base``."""
    if not node.level:
        return node.module or ""
    parts = base.split(".")[: -node.level]
    return ".".join(parts + ([node.module] if node.module else []))


def _first_sentence(doc: str | None) -> str:
    if not doc:
        return ""
    paragraph = " ".join(doc.strip().split("\n\n", 1)[0].split())
    paragraph = re.sub(
        r"``([^`]+)``", r"`\1`", paragraph
    )  # reST literals -> Markdown code
    return re.split(r"(?<=[.!?])\s", paragraph, maxsplit=1)[0]


class Module:
    """One parsed Python module: its classes, functions, imports and pattern lists."""

    _cache: dict[str, Module] = {}

    def __init__(self, name: str) -> None:
        self.name = name
        self.tree = ast.parse(module_file(name).read_text(encoding="utf-8"))
        self.defs = {
            n.name: n
            for n in self.tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.imports: dict[str, tuple[str, str]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                source = resolve_module(name, node)
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (source, alias.name)

    @classmethod
    def load(cls, name: str) -> Module:
        if name not in cls._cache:
            cls._cache[name] = cls(name)
        return cls._cache[name]

    def lookup(self, name: str) -> tuple[Module, ast.AST] | None:
        """Find the definition of ``name``, following ``from law_ai… import`` once per hop."""
        if name in self.defs:
            return self, self.defs[name]
        source = self.imports.get(name)
        if (
            source
            and source[0].startswith("law_ai")
            and module_file(source[0]).is_file()
        ):
            return Module.load(source[0]).lookup(source[1])
        return None

    def methods(self, node: ast.AST) -> list[str]:
        """HTTP verbs a view class defines, walking local base classes."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        assert isinstance(node, ast.ClassDef)
        found = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in HTTP_METHODS
        ]
        if not found:
            for base in node.bases:
                if isinstance(base, ast.Name) and (hit := self.lookup(base.id)):
                    found = hit[0].methods(hit[1])
                    if found:
                        break
        return [m for m in HTTP_METHODS if m in found]

    def patterns(self, variable: str = "urlpatterns") -> list[tuple[Module, ast.Call]]:
        """``(owning module, path() call)`` bound to ``variable``, including ``+=`` extensions."""
        calls: list[tuple[Module, ast.Call]] = []
        for node in self.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                target = (
                    node.targets[0] if isinstance(node, ast.Assign) else node.target
                )
                if (
                    isinstance(target, ast.Name)
                    and target.id == variable
                    and isinstance(node.value, ast.List)
                ):
                    calls = [
                        (self, e) for e in node.value.elts if isinstance(e, ast.Call)
                    ]
            elif (
                isinstance(node, ast.AugAssign)
                and getattr(node.target, "id", "") == variable
            ):
                if isinstance(node.value, ast.Name) and node.value.id in self.imports:
                    source, original = self.imports[node.value.id]
                    calls += Module.load(source).patterns(original)
                elif isinstance(node.value, ast.List):
                    calls += [
                        (self, e) for e in node.value.elts if isinstance(e, ast.Call)
                    ]
        return calls


def _view(module: Module, call: ast.Call) -> tuple[str, list[str], str] | None:
    """``(view name, methods, summary)`` for one pattern, or None for an include/admin."""
    view = call.args[1]
    if (
        isinstance(view, ast.Call)
        and isinstance(view.func, ast.Attribute)
        and isinstance(view.func.value, ast.Name)
    ):
        name = view.func.value.id  # SomeView.as_view() / Consumer.as_asgi()
    elif isinstance(view, ast.Name):
        name = view.id
    else:
        return None
    hit = module.lookup(name)
    if not hit:
        return name, [], ""
    owner, node = hit
    methods = owner.methods(node) if isinstance(node, ast.ClassDef) else ["any"]
    return name, methods, _first_sentence(ast.get_docstring(node))


def _route_text(call: ast.Call) -> str:
    arg = call.args[0]
    return (
        arg.value
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        else "?"
    )


def http_routes() -> list[tuple[str, list[Route], bool]]:
    """``(mount, routes, slashless_twin)`` per ``include()`` in the root URLconf, in order."""
    root = Module.load(ROOT_URLCONF)
    mounts: list[tuple[str, str]] = []
    singles: list[Route] = []
    for _, call in root.patterns():
        prefix = _route_text(call)
        view = call.args[1]
        if isinstance(view, ast.Call) and getattr(view.func, "id", "") == "include":
            mounts.append((prefix, view.args[0].value))  # type: ignore[attr-defined]
        elif isinstance(view, ast.Attribute):
            singles.append(
                Route(
                    f"/{prefix}",
                    "ANY",
                    "django.contrib.admin",
                    "The Django admin site.",
                )
            )
        elif (found := _view(root, call)) is not None:
            name, methods, summary = found
            singles.append(
                Route(f"/{prefix}", " ".join(m.upper() for m in methods), name, summary)
            )

    prefixes = {prefix for prefix, _ in mounts}
    groups: list[tuple[str, list[Route], bool]] = (
        [("/", singles, False)] if singles else []
    )
    for prefix, module_name in mounts:
        if not prefix.endswith("/") and f"{prefix}/" in prefixes:
            continue  # the slashless twin of `prefix/` serves the same views; noted on the twin
        module = Module.load(module_name)
        routes: list[Route] = []
        for owner, call in module.patterns():
            found = _view(owner, call)
            if found is None:
                continue
            name, methods, summary = found
            routes.append(
                Route(
                    f"/{prefix}{_route_text(call)}",
                    " ".join(m.upper() for m in methods),
                    name,
                    summary,
                )
            )
        twin = prefix.endswith("/") and prefix[:-1] in prefixes
        groups.append((f"/{prefix}", routes, twin))
    return groups


def websocket_routes() -> list[Route]:
    module = Module.load(WS_ROUTING)
    routes: list[Route] = []
    for owner, call in module.patterns("websocket_urlpatterns"):
        found = _view(owner, call)
        if found:
            name, _, summary = found
            routes.append(Route(_route_text(call), "WS", name, summary))
    return routes


def _cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


def _table(routes: list[Route]) -> list[str]:
    out = ["| Route | Methods | View | Summary |", "| --- | --- | --- | --- |"]
    for r in routes:
        out.append(
            f"| `{_cell(r.path)}` | {r.methods} | `{r.view}` | {_cell(r.summary)} |"
        )
    return out


def render() -> str:
    groups = http_routes()
    total = sum(len(routes) for _, routes, _ in groups)
    out = [
        f"<!-- GENERATED by {COMMAND} — do not edit by hand -->",
        "# HTTP and WebSocket routes",
        "",
        "> Every route the Django backend serves, grouped by mount, with the methods its view defines and the first line of the view's docstring — generated from the URLconf.",
        "",
        f"{total} HTTP routes across {len(groups)} mounts, read statically from `backend/law_ai/urls.py` and the modules it includes. "
        "Authentication and per-scope API keys are described in [api-examples.md](../api-examples.md), which carries the curl examples, "
        f"and [security.md](../security.md). Change a route in its `urls.py`, then run `{COMMAND}`.",
    ]
    for mount, routes, twin in groups:
        out += ["", f"## `{mount}`", ""]
        if twin:
            out += [
                f"Also mounted without the trailing slash (`{mount[:-1]}`), so the bare prefix resolves too.",
                "",
            ]
        out += _table(routes)
    ws = websocket_routes()
    if ws:
        out += [
            "",
            "## WebSocket (`backend/law_ai/agentsapi/routing.py`)",
            "",
            *_table(ws),
        ]
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
