"""
Testes de prazo e reabertura.

O modelo `Briefing` tem 4 estados: in_progress / paused / completed
/ cancelled. Estados que existiam antes (`closed`, `expired`) foram
removidos e fundidos em `cancelled` — controlado por `cancelled_at`
e `expires_at`. Os testes abaixo refletem o contrato atual.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.services import BriefingService
from apps.briefings.exceptions import BriefingReopenError


@pytest.mark.django_db
class TestReopen:

    def test_reopen_cancelled_with_expired_deadline_requires_new(
        self, briefing_a, user_owner,
    ):
        # Cancela com prazo expirado
        briefing_a.status = Briefing.STATUS_CANCELLED
        briefing_a.cancelled_at = timezone.now() - timedelta(days=1)
        briefing_a.expires_at = timezone.now() - timedelta(days=1)
        briefing_a.save(update_fields=[
            'status', 'cancelled_at', 'expires_at',
        ])

        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
            )

    def test_reopen_cancelled_with_past_new_deadline_fails(
        self, briefing_a, user_owner,
    ):
        briefing_a.status = Briefing.STATUS_CANCELLED
        briefing_a.cancelled_at = timezone.now() - timedelta(days=1)
        briefing_a.expires_at = timezone.now() - timedelta(days=1)
        briefing_a.save(update_fields=[
            'status', 'cancelled_at', 'expires_at',
        ])

        past = timezone.now() - timedelta(hours=1)
        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
                new_expires_at=past,
            )

    def test_reopen_cancelled_with_future_deadline_succeeds(
        self, briefing_a, user_owner,
    ):
        briefing_a.status = Briefing.STATUS_CANCELLED
        briefing_a.cancelled_at = timezone.now() - timedelta(days=1)
        briefing_a.expires_at = timezone.now() - timedelta(days=1)
        briefing_a.save(update_fields=[
            'status', 'cancelled_at', 'expires_at',
        ])

        future = timezone.now() + timedelta(days=7)
        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
            new_expires_at=future,
            reason='Prorrogado por pedido do cliente.',
        )

        assert b.status == Briefing.STATUS_IN_PROGRESS
        assert b.expires_at is not None
        assert b.expires_at >= future - timedelta(seconds=2)

        ev = BriefingEvent.objects.filter(
            briefing=b, kind=BriefingEvent.KIND_REOPENED,
        ).order_by('-created_at').first()
        assert ev is not None
        assert ev.content.get('reason') == 'Prorrogado por pedido do cliente.'

    def test_reopen_cancelled_without_deadline_succeeds(
        self, briefing_a, user_owner,
    ):
        # Cancela SEM prazo expirado (não precisa de novo prazo)
        BriefingService.cancel(briefing=briefing_a, actor=user_owner)
        briefing_a.refresh_from_db()
        assert briefing_a.status == Briefing.STATUS_CANCELLED
        assert briefing_a.has_expired() is False

        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
            reason='Reaberto manualmente.',
        )
        assert b.status == Briefing.STATUS_IN_PROGRESS

    def test_reopen_paused_succeeds(self, briefing_a, user_owner):
        BriefingService.pause(briefing=briefing_a, actor=user_owner)
        briefing_a.refresh_from_db()
        assert briefing_a.status == Briefing.STATUS_PAUSED

        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
        )
        assert b.status == Briefing.STATUS_IN_PROGRESS

    def test_reopen_completed_without_deadline_succeeds(
        self, briefing_a, user_owner,
    ):
        briefing_a.status = Briefing.STATUS_COMPLETED
        briefing_a.completed_at = timezone.now()
        briefing_a.save(update_fields=['status', 'completed_at'])

        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
        )
        assert b.status == Briefing.STATUS_IN_PROGRESS
        assert b.completed_at is None

    def test_reopen_in_progress_fails(self, briefing_a, user_owner):
        # Já está in_progress — não é estado reabrível
        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
            )