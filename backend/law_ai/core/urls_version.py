"""``/version`` endpoint (fleet standard UPS-BE-11).

Open like ``/health``: it returns the release version and, when the image
was built with them, the commit sha and build time. A deployment that must
not disclose the sha leaves ``GIT_SHA`` unset and ``commit`` is ``null``.
"""

from __future__ import annotations

import os
from typing import Any

from django.urls import path
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.version import DISTRIBUTION, get_version


class VersionView(APIView):
    """Release version and build provenance of the running service."""

    permission_classes = [AllowAny]
    authentication_classes: list[type[BaseAuthentication]] = []

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            {
                "name": DISTRIBUTION,
                "version": get_version(),
                "commit": os.environ.get("GIT_SHA") or None,
                "built_at": os.environ.get("BUILT_AT") or None,
            }
        )


urlpatterns = [path("", VersionView.as_view(), name="version")]
