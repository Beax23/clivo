"""
Testes do NotificationService — envio automático em conclusão.

Cobrem:
    - Envio único por briefing (idempotência)
    - Segundo chamado NÃO dispara novo envio
    - Falha de e-mail NÃO marca como enviado
    - Status diferente de `completed` não dispara
    - Briefing inexistente não levanta
    - submit_answer AGENDA a notificação via on_commit

Estratégia de teste:
    Chamamos `NotificationService.on_briefing_completed()` DIRETAMENTE
    em vez de depender do on_commit do `submit_answer`. Motivo: dentro
    do `@pytest.mark.django_db` cada teste roda numa transação envolvida
    que faz rollback — e o `on_commit` do Django não dispara nesse
    contexto. O contrato "on_commit agenda" é verificado separadamente
    (test_completion_schedules_on_commit).
"""

import pytest
from unittest.mock import patch
from uuid import uuid4

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.services import (
    BriefingService,
    NotificationService,
)
from apps.accounts.services.email import EmailService


def _complete_briefing(briefing, portal_session):
    """Leva um briefing a `completed` respondendo todas as perguntas."""
    questions = briefing.snapshot_questions()
    for q in questions:
        BriefingService.submit_answer(
            briefing_id=briefing.id,
            portal_session=portal_session,
            question_id=q['id'],
            content_text='ok',
        )


@pytest.mark.django_db
class TestCompletionNotification:

    # ==================================================================
    # IDEMPOTÊNCIA
    # ==================================================================

    def test_notification_runs_once_on_completed_briefing(
        self, briefing_a, portal_session_a,
    ):
        """
        Primeira chamada envia; segunda NÃO envia.

        Checa o marcador `completion_email_sent` e a contagem de
        chamadas ao EmailService.
        """
        # Leva ao estado completed
        _complete_briefing(briefing_a, portal_session_a)
        briefing_a.refresh_from_db()
        assert briefing_a.status == Briefing.STATUS_COMPLETED

        with patch.object(
            EmailService, 'send_briefing_completed', return_value=1,
        ) as mock_send:
            first = NotificationService.on_briefing_completed(
                briefing_a.id,
            )
            second = NotificationService.on_briefing_completed(
                briefing_a.id,
            )

        # Primeira faz o envio
        assert first is True
        # Segunda é idempotente e não envia
        assert second is False

        # Uma única chamada real ao EmailService
        assert mock_send.call_count == 1

        # Um único evento marcador
        markers = BriefingEvent.objects.filter(
            briefing=briefing_a,
            kind=BriefingEvent.KIND_COMPLETION_EMAIL_SENT,
        )
        assert markers.count() == 1

    def test_notification_not_sent_when_not_completed(self, briefing_a):
        """
        Briefing ainda `in_progress` NÃO dispara notificação.
        """
        with patch.object(
            EmailService, 'send_briefing_completed', return_value=1,
        ) as mock_send:
            result = NotificationService.on_briefing_completed(
                briefing_a.id,
            )

        assert result is False
        mock_send.assert_not_called()

    def test_notification_no_exception_for_missing_briefing(self):
        """
        Briefing inexistente retorna False sem levantar.
        """
        result = NotificationService.on_briefing_completed(uuid4())
        assert result is False

    # ==================================================================
    # FALHA DE ENVIO
    # ==================================================================

    def test_failed_send_does_not_mark_as_sent(
        self, briefing_a, portal_session_a,
    ):
        """
        Se o envio falha, o evento marcador NÃO é gravado — retentativa
        é possível.
        """
        _complete_briefing(briefing_a, portal_session_a)
        briefing_a.refresh_from_db()

        # 1ª tentativa — falha
        with patch.object(
            EmailService, 'send_briefing_completed',
            side_effect=Exception('smtp down'),
        ):
            result = NotificationService.on_briefing_completed(
                briefing_a.id,
            )
        assert result is False

        # Nenhum marcador
        assert BriefingEvent.objects.filter(
            briefing=briefing_a,
            kind=BriefingEvent.KIND_COMPLETION_EMAIL_SENT,
        ).count() == 0

        # 2ª tentativa — sucesso
        with patch.object(
            EmailService, 'send_briefing_completed', return_value=1,
        ):
            result = NotificationService.on_briefing_completed(
                briefing_a.id,
            )
        assert result is True

        assert BriefingEvent.objects.filter(
            briefing=briefing_a,
            kind=BriefingEvent.KIND_COMPLETION_EMAIL_SENT,
        ).count() == 1

    # ==================================================================
    # AGENDAMENTO VIA on_commit
    # ==================================================================

    def test_completion_schedules_on_commit(
        self, briefing_a, portal_session_a,
    ):
        """
        Verifica que `submit_answer` AGENDA um on_commit quando o
        briefing passa a `completed`. Não executamos o callback —
        apenas checamos que foi agendado.

        Usa `django.test.TestCase.captureOnCommitCallbacks` via
        `django.test.utils`, disponível no pytest-django.
        """
        from django.test import TestCase

        # Envolvemos a chamada num capture de callbacks do Django.
        # `captureOnCommitCallbacks` exige uma instância de TestCase.
        class _Capture(TestCase):
            def runTest(self):
                pass

        capture = _Capture()

        with capture.captureOnCommitCallbacks(execute=False) as callbacks:
            _complete_briefing(briefing_a, portal_session_a)

        # Pelo menos um callback de on_commit foi agendado
        # (idealmente o de notificação; pode haver também o de
        # transcrição, mas não há áudio neste teste).
        assert len(callbacks) >= 1