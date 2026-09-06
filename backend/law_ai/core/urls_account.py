"""Account self-service: export and deletion (BL-20260817-01).

Mounted at ``/api/account/``. Both routes are the user acting on their own
account, so both require a real session — an API key, even one bound to a
user, cannot delete the account it authenticates as: that is a footgun with no
upside, and a leaked key should never be able to end an account.

``POST delete`` demands the caller retype their username. A destructive,
irreversible action taken on a single unconfirmed click is a bug, not a
feature.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import logout
from django.urls import path
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import is_signed_in


class _SessionOnly(APIView):
    permission_classes = [AllowAny]

    def initial(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if not is_signed_in(request):
            from rest_framework.exceptions import NotAuthenticated

            raise NotAuthenticated("sign in first")


class AccountExportView(_SessionOnly):
    """``GET /api/account/export`` — every matter the caller owns, in one file."""

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        from law_ai.matters.models import Matter
        from law_ai.matters.services.export import BUNDLE_VERSION, export_matter

        matters = Matter.objects.filter(owner=request.user)
        bundle = {
            "bundle_version": BUNDLE_VERSION,
            "account": {
                "username": request.user.get_username(),
                "id": request.user.pk,
            },
            "matters": [export_matter(m, log=False) for m in matters],
        }
        response = Response(bundle)
        response["Content-Disposition"] = 'attachment; filename="law-ai-export.json"'
        return response


class AccountDeleteView(_SessionOnly):
    """``POST /api/account/delete`` — de-identify this account."""

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        from law_ai.core.accounts.deletion import delete_account

        confirm = str((request.data or {}).get("confirm_username") or "")
        if confirm != request.user.get_username():
            return Response(
                {"detail": "confirm_username must match the signed-in username"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        summary = delete_account(
            request.user, reason=str((request.data or {}).get("reason") or "")
        )
        # The session belongs to an account that no longer exists as itself.
        logout(request)
        return Response(summary)


urlpatterns = [
    path("export", AccountExportView.as_view(), name="account-export"),
    path("delete", AccountDeleteView.as_view(), name="account-delete"),
]
