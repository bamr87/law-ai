"""Server-persisted setting values (BL-20260830-07 / spec 040).

The precedence engine stays in TypeScript (`frontend/lib/scope/resolver.ts`):
this module is storage plus authorisation, nothing more. It answers three
questions and no others — which rows apply to this caller, may this caller
write this row, and who wrote it.

Scope identifiers are the frontend's opaque strings. Two shapes are live:

* ``instance:local`` — one row per key for the whole deployment. Writable by
  staff only: an instance default is an admin action, and `locked` on an
  instance row overrides every user.
* ``user:<pk>`` (or ``user:me``, resolved to the caller) — the caller's own
  preferences. Writable only by that user, which is the whole IDOR surface
  here and is checked on every write.

Anonymous callers get the instance rows and nothing else, and every write is
refused — the frontend keeps its localStorage behaviour byte-identical for
them (spec 040 plan.md, "no accounts required").
"""

from __future__ import annotations

import json
from typing import Any

from django.urls import path
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import is_signed_in
from law_ai.core.models import SettingValue
from law_ai.core.provenance import provenance

INSTANCE_SCOPE_ID = "instance:local"
#: A stored value must survive a JSON round-trip and stay small: this table is
#: a preference store, not a document store.
MAX_VALUE_BYTES = 4096


def user_scope_id(request: Any) -> str | None:
    """The caller's own user scope, or ``None`` when not signed in."""
    if not is_signed_in(request):
        return None
    return f"user:{request.user.pk}"


def scope_type_of(scope_id: str) -> str:
    return scope_id.split(":", 1)[0] if ":" in scope_id else scope_id


def resolve_scope(request: Any, scope_id: str) -> str:
    """Expand the ``user:me`` alias so a client need not know its own pk."""
    if scope_id in {"user:me", "me"}:
        return user_scope_id(request) or scope_id
    return scope_id


def may_write(request: Any, scope_id: str) -> tuple[bool, str]:
    """``(allowed, reason)`` for a write to *scope_id*."""
    if not is_signed_in(request):
        return False, "sign in to change stored settings"
    kind = scope_type_of(scope_id)
    if kind == SettingValue.SCOPE_INSTANCE:
        if not getattr(request.user, "is_staff", False):
            return False, "instance settings are staff-only"
        return True, ""
    if kind == SettingValue.SCOPE_USER:
        if scope_id != user_scope_id(request):
            return False, "not your settings scope"
        return True, ""
    return False, f"unknown scope {scope_id!r}"


def visible_scope_ids(request: Any) -> list[str]:
    """The scope chain this caller may read, root-first."""
    chain = [INSTANCE_SCOPE_ID]
    own = user_scope_id(request)
    if own:
        chain.append(own)
    return chain


def writable_scope_ids(request: Any) -> list[str]:
    """The subset of the visible chain this caller may actually write.

    BL-20260906-73. Readability and writability are not the same question here
    — everyone reads the instance row, only staff may set it — and until this
    shipped the client could not tell them apart. A settings UI that offers an
    instance write to a non-admin is offering something the server will refuse:
    the row stays local to that browser and nothing says so. Derived from
    :func:`may_write` rather than re-deciding, so the answer the client renders
    and the answer the write gets can never disagree.
    """
    return [s for s in visible_scope_ids(request) if may_write(request, s)[0]]


class SettingValuesView(APIView):
    """``GET /api/settings/values`` — every row in the caller's scope chain."""

    permission_classes = [AllowAny]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        scopes = visible_scope_ids(request)
        rows = SettingValue.objects.filter(scope_id__in=scopes)
        return Response(
            {
                "scopes": scopes,
                "writableScopes": writable_scope_ids(request),
                "values": [row.as_row() for row in rows],
            }
        )


class SettingValueDetailView(APIView):
    """``PUT``/``DELETE /api/settings/values/<scope_id>/<key>``."""

    permission_classes = [AllowAny]

    def put(
        self, request: Any, scope_id: str, key: str, *args: Any, **kwargs: Any
    ) -> Response:
        scope_id = resolve_scope(request, scope_id)
        allowed, reason = may_write(request, scope_id)
        if not allowed:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}
        if "value" not in data:
            return Response(
                {"detail": 'body must be {"value": …, "locked": bool}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        value = data["value"]
        try:
            encoded = json.dumps(value)
        except (TypeError, ValueError):
            return Response(
                {"detail": "value must be JSON-serialisable"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
            return Response(
                {"detail": f"value exceeds {MAX_VALUE_BYTES} bytes"},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        row, created = SettingValue.objects.update_or_create(
            scope_type=scope_type_of(scope_id),
            scope_id=scope_id,
            key=key,
            defaults={
                "value": value,
                "locked": bool(data.get("locked", False)),
                "updated_by": request.user,
            },
        )
        provenance.log_event(
            "setting_value.updated",
            {
                "source": "settings",
                "scope_id": scope_id,
                "key": key,
                "locked": row.locked,
                "actor": request.user.get_username(),
            },
        )
        return Response(
            row.as_row(),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(
        self, request: Any, scope_id: str, key: str, *args: Any, **kwargs: Any
    ) -> Response:
        scope_id = resolve_scope(request, scope_id)
        allowed, reason = may_write(request, scope_id)
        if not allowed:
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)
        deleted, _ = SettingValue.objects.filter(scope_id=scope_id, key=key).delete()
        if not deleted:
            return Response(
                {"detail": "no such setting"}, status=status.HTTP_404_NOT_FOUND
            )
        provenance.log_event(
            "setting_value.deleted",
            {
                "source": "settings",
                "scope_id": scope_id,
                "key": key,
                "actor": request.user.get_username(),
            },
        )
        return Response({"scopeId": scope_id, "key": key, "deleted": True})


urlpatterns = [
    path("values", SettingValuesView.as_view(), name="setting-values"),
    path(
        "values/<str:scope_id>/<str:key>",
        SettingValueDetailView.as_view(),
        name="setting-value-detail",
    ),
]
