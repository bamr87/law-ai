"""``manage.py seed_admin`` — idempotently provision an admin login from env.

Reads ``DJANGO_SUPERUSER_USERNAME`` and ``DJANGO_SUPERUSER_PASSWORD`` (plus an
optional ``DJANGO_SUPERUSER_EMAIL``). When either is empty the command is a
no-op, so the default dev and prod stacks never grow an account by accident;
the ``backend-e2e`` compose service (spec 051 / BL-20260503-17) sets both so
the browser HITL spec can log in at ``/admin/``.

The password is (re)set on every run — a rotated env value takes effect on the
next boot instead of silently keeping the old one — and the row is always a
superuser + staff, which is what the admin login requires.
"""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed a superuser from DJANGO_SUPERUSER_USERNAME/PASSWORD (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        if not username or not password:
            self.stdout.write("seed_admin: DJANGO_SUPERUSER_* unset — skipped")
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        if email:
            user.email = email
        user.set_password(password)
        user.save()
        verb = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"seed_admin: {verb} {username!r}"))
