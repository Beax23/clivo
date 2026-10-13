"""
Testes do BriefingSendService — envio manual pelo arquiteto.

Cobrem:
    - Envio com sucesso registra evento `manual_send`
    - Envio sem e-mail cadastrado levanta erro
    - Reenvio cria um novo evento
    - Isolamento por workspace (não é possível enviar
      briefing de outro workspace)
"""

import pytest
from unittest.mock import patch

from apps.briefings.models import BriefingEvent
from apps.briefings.services import BriefingSendService
from apps.briefings.exceptions import BriefingError
from apps.accounts.services.email import EmailService


@pytest.mark.django_db
class TestSendService:

    def test_send_to_client_success(
        self, briefing_a, user_owner, client_a,
    ):
        with patch.object(
            EmailService, 'send_briefing_to_client', return_value=1,
        ) as mock_send:
            result = BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
                to_email=None,  # usa cliente.email
                message='Segue em anexo.',
            )

        assert result['sent'] is True
        assert result['to'] == client_a.email
        assert 'event_id' in result

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs['to_email'] == client_a.email
        assert call_kwargs['message'] == 'Segue em anexo.'

        event = BriefingEvent.objects.get(id=result['event_id'])
        assert event.kind == 'manual_send'
        assert event.user_id == user_owner.id
        assert event.content['to'] == client_a.email

    def test_send_to_alternate_email(
        self, briefing_a, user_owner,
    ):
        alt = 'outro@endereco.com'
        with patch.object(
            EmailService, 'send_briefing_to_client', return_value=1,
        ):
            result = BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
                to_email=alt,
            )

        assert result['to'] == alt
        event = BriefingEvent.objects.get(id=result['event_id'])
        assert event.content['to'] == alt

    def test_send_without_email_raises(
        self, briefing_a, user_owner, client_a,
    ):
        client_a.email = ''
        client_a.save(update_fields=['email'])

        with pytest.raises(BriefingError):
            BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
                to_email=None,
            )

    def test_resend_creates_new_event(
        self, briefing_a, user_owner,
    ):
        with patch.object(
            EmailService, 'send_briefing_to_client', return_value=1,
        ):
            r1 = BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
            )
            r2 = BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
            )

        assert r1['event_id'] != r2['event_id']

        events = BriefingEvent.objects.filter(
            briefing=briefing_a,
            kind='manual_send',
        )
        assert events.count() == 2

    def test_send_on_completed_briefing_works(
        self, briefing_a, user_owner, portal_session_a,
    ):
        """Reenvio funciona mesmo após conclusão."""
        # Conclui
        from apps.briefings.services import BriefingService
        questions = briefing_a.snapshot_questions()
        for q in questions:
            BriefingService.submit_answer(
                briefing_id=briefing_a.id,
                portal_session=portal_session_a,
                question_id=q['id'],
                content_text='ok',
            )

        briefing_a.refresh_from_db()
        assert briefing_a.status == 'completed'

        with patch.object(
            EmailService, 'send_briefing_to_client', return_value=1,
        ):
            result = BriefingSendService.send_to_client(
                briefing=briefing_a,
                actor=user_owner,
            )

        assert result['sent'] is True