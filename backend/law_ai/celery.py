"""Celery application factory (spec 011 FR-11)."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "law_ai.settings.dev")

app = Celery("law_ai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Spec 018 T-009: Autonomy beat schedule (all disabled when AUTONOMY_ENABLED=False).
# Operators activate by setting AUTONOMY_ENABLED=true in their environment.
#
# NOTE: The autonomy tasks are routed to the "autonomy" queue. The worker
# container must include "-Q autonomy,celery" (or use CELERY_TASK_ROUTES)
# to consume these entries. See docker-compose.yml worker command.
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    # Pillar B — corpus sweep every 6h (constitution §12 invariant I4).
    "autonomy-content-sweep": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": 6 * 3600,  # every 6 hours (seconds)
        "kwargs": {"kind": "corpus_growth", "budget": 25},
        "options": {"queue": "autonomy"},
    },
    # Pillar A — nightly test synthesis (06:00 UTC).
    "autonomy-nightly-tests": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {"kind": "test_pillar"},
        "options": {"queue": "autonomy"},
    },
    # Pillar C — daily autonomy digest (07:00 UTC, spec 018 T-010).
    # BL-20260511-23: this is the one entry that does NOT use the generic
    # `autonomy_cycle` task. The digest is a pure audit-log query, so a
    # dropped connection would otherwise produce an empty-but-successful
    # file; `compose_digest_task` retries transient DB faults instead.
    "autonomy-daily-digest": {
        "task": "law_ai.core.tasks.compose_digest_task",
        "schedule": crontab(hour=7, minute=0),
        "kwargs": {"kind": "digest"},
        "options": {"queue": "autonomy"},
    },
    # Pillar D — daily LSAT content drafting (04:00 UTC, spec 019 FR-11).
    # Drafts only; every proposal stays in the HITL queue until a reviewer
    # explicitly approves via POST /api/lsat/proposals/<id>/approve.
    "autonomy-lsat-content": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=4, minute=0),
        "kwargs": {"kind": "lsat_content", "budget": 5},
        "options": {"queue": "autonomy"},
    },
    # Pillar D — nightly LSAT content-factory batch (03:00 UTC, spec 024
    # FR-8 / BL-20260702-04). Coverage-driven: plan → compile → generate on
    # the LOCAL model (pinned; a beat entry never bills a hosted tier) →
    # intake gates → pending proposals. budget caps the manifest at four jobs
    # so a small box finishes before the 04:00 drafting beat starts.
    "autonomy-lsat-factory": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=3, minute=0),
        "kwargs": {"kind": "lsat_factory", "budget": 4},
        "options": {"queue": "autonomy"},
    },
    # Pillar D — weekly LSAT knowledge-library review (Monday 05:00 UTC,
    # spec 048 FR-17). Review only: every result lands as a pending
    # `library_finding` proposal and nothing under data/library/ is written.
    # Weekly rather than daily because prose about exam structure does not
    # change on a daily cadence, and each review is a full-article model call.
    "autonomy-lsat-library": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=5, minute=0, day_of_week=1),
        "kwargs": {"kind": "lsat_library", "budget": 3},
        "options": {"queue": "autonomy"},
    },
    # Pillar D — weekly LSAT bank cross-check (Tuesday 05:00 UTC,
    # BL-20260905-58). Blind-solves unchecked questions through the provider
    # chain and files only *disagreements* as pending `crosscheck` proposals,
    # so a mis-keyed question surfaces on a cadence instead of when a learner
    # happens to trip over it. Weekly and budget-capped at five because every
    # question is a real provider call; questions already carrying a verdict
    # or a queued row are skipped, so consecutive runs advance rather than
    # re-solve. A day after the library review so the two never overlap.
    "autonomy-lsat-cross-check": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": crontab(hour=5, minute=0, day_of_week=2),
        "kwargs": {"kind": "lsat_cross_check", "budget": 5},
        "options": {"queue": "autonomy"},
    },
    # Ingestion HITL — apply human approvals every 15 minutes (spec 029
    # follow-up BL-20260811-02). Not an autonomy *decision*: every row it
    # touches was already approved by a person, and the sweep is idempotent
    # (``committed_at`` short-circuits), so the only risk of running it often
    # is an empty query. Routed through ``autonomy_cycle`` so the
    # AUTONOMY_ENABLED kill-switch and the cycle audit event both apply.
    "ingestion-commit-approved": {
        "task": "law_ai.core.tasks.autonomy_cycle",
        "schedule": 15 * 60,
        "kwargs": {"kind": "commit_approved", "budget": 25},
        "options": {"queue": "autonomy"},
    },
    # Matter deadlines — remind on user-entered due dates hourly
    # (BL-20260817-02). Not an autonomy decision and not routed through
    # `autonomy_cycle`: it reads the user's own tasks, writes only
    # `reminded_at`, and must keep working on an instance with autonomy off.
    "matter-task-reminders": {
        "task": "law_ai.matters.sweep_task_reminders",
        "schedule": 3600,
    },
    # Repo governance — weekly spec + backlog triage (Monday 08:00 UTC,
    # BL-20260503-14). Runs scripts/spec_validator.py AND
    # scripts/backlog_lint.py over the mounted repo and, when
    # GOVERNANCE_TRIAGE_GITHUB_* are configured, keeps one idempotent triage
    # issue up to date. CI runs both validators against the diff in front of
    # it; nothing was watching the parts nobody diffs — a spec left
    # inconsistent for a month, an `## Open` item untouched since spring.
    #
    # Not on the autonomy queue and not routed through `autonomy_cycle`: this
    # takes no autonomous action, and it must keep working on an instance with
    # AUTONOMY_ENABLED=false. It needs the repo bind-mounted (REPO_ROOT=/repo)
    # and says so plainly in the log when it is not — "could not look" is
    # never reported as "found nothing".
    "governance-triage": {
        "task": "law_ai.core.tasks.governance_triage",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
        "kwargs": {"stale_days": 60},
    },
}
app.conf.beat_schedule_filename = "celerybeat-schedule"


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:  # pragma: no cover - debug helper
    return f"Request: {self.request!r}"
