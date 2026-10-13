"""
Testes de prazo e reabertura.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.services import BriefingService
from apps.briefings.exceptions import BriefingReopenError


@pytest.mark.django_db
class TestReopen:

    def test_reopen_expired_without_new_deadline_fails(
        self, briefing_a, user_owner,
    ):
        # Força estado expirado
        briefing_a.status = Briefing.STATUS_EXPIRED
        briefing_a.save(update_fields=['status'])

        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
            )

    def test_reopen_expired_with_past_deadline_fails(
        self, briefing_a, user_owner,
    ):
        briefing_a.status = Briefing.STATUS_EXPIRED
        briefing_a.save(update_fields=['status'])

        past = timezone.now() - timedelta(days=1)
        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
                new_expires_at=past,
            )

    def test_reopen_expired_with_future_deadline_succeeds(
        self, briefing_a, user_owner,
    ):
        briefing_a.status = Briefing.STATUS_EXPIRED
        briefing_a.save(update_fields=['status'])

        future = timezone.now() + timedelta(days=7)
        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
            new_expires_at=future, reason='Prorrogado por pedido do cliente.',
        )

        assert b.status == Briefing.STATUS_IN_PROGRESS
        assert b.expires_at is not None
        assert b.expires_at >= future - timedelta(seconds=2)

        # Evento registrado
        ev = BriefingEvent.objects.filter(
            briefing=b, kind=BriefingEvent.KIND_REOPENED,
        ).order_by('-created_at').first()
        assert ev is not None
        assert ev.content.get('reason') == 'Prorrogado por pedido do cliente.'
        assert ev.content.get('new_expires_at') is not None

    def test_reopen_closed_without_deadline_succeeds(
        self, briefing_a, user_owner,
    ):
        # Fecha o briefing
        BriefingService.close(briefing=briefing_a, actor=user_owner)
        briefing_a.refresh_from_db()
        assert briefing_a.status == Briefing.STATUS_CLOSED

        b = BriefingService.reopen(
            briefing=briefing_a, actor=user_owner,
            reason='Reaberto manualmente.',
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

    def test_reopen_invalid_state_fails(
        self, briefing_a, user_owner,
    ):
        # Já está in_progress — não é estado reabrível
        with pytest.raises(BriefingReopenError):
            BriefingService.reopen(
                briefing=briefing_a, actor=user_owner,
            )