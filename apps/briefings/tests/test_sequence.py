"""
Testes do fluxo sequencial.

Cobrem o requisito "só responde a próxima pergunta elegível".
"""

import pytest

from apps.briefings.models import (
    Briefing,
    BriefingAnswer,
    BriefingEvent,
)
from apps.briefings.services import BriefingService
from apps.briefings.exceptions import InvalidQuestionSequenceError


@pytest.mark.django_db
class TestSequence:

    def test_answer_first_question(
        self, briefing_a, portal_session_a,
    ):
        questions = briefing_a.snapshot_questions()
        first = questions[0]

        answer = BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=first['id'],
            content_text='Minha rotina é tranquila.',
        )

        assert answer.state == BriefingAnswer.STATE_ANSWERED
        assert answer.latest_content == 'Minha rotina é tranquila.'

    def test_cannot_answer_question_out_of_order(
        self, briefing_a, portal_session_a,
    ):
        questions = briefing_a.snapshot_questions()
        third = questions[2]  # nunca respondida, e não é a próxima

        with pytest.raises(InvalidQuestionSequenceError):
            BriefingService.submit_answer(
                briefing_id=briefing_a.id,
                portal_session=portal_session_a,
                question_id=third['id'],
                content_text='Pulando fila.',
            )

    def test_flow_completes_when_all_answered(
        self, briefing_a, portal_session_a,
    ):
        questions = briefing_a.snapshot_questions()

        for q in questions:
            BriefingService.submit_answer(
                briefing_id=briefing_a.id,
                portal_session=portal_session_a,
                question_id=q['id'],
                content_text=f'Resposta para {q["id"]}',
            )

        briefing_a.refresh_from_db()
        assert briefing_a.status == Briefing.STATUS_COMPLETED
        assert briefing_a.completed_at is not None

    def test_review_requested_remains_next_eligible(
        self, briefing_a, portal_session_a,
    ):
        questions = briefing_a.snapshot_questions()
        first = questions[0]

        # Responde
        BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=first['id'],
            content_text='Minha rotina...',
        )

        # Cliente pede revisão na mesma pergunta
        BriefingService.request_review(
            briefing=briefing_a,
            portal_session=portal_session_a,
            question_id=first['id'],
            message='Quero complementar.',
        )

        # Próxima elegível é de novo a pergunta 1
        nxt = BriefingService.get_next_eligible_question(briefing_a)
        assert str(nxt['id']) == str(first['id'])

    def test_answer_event_created_per_submission(
        self, briefing_a, portal_session_a,
    ):
        """
        Reenvio de resposta exige `request_review` antes.

        O fluxo é:
            1. Cliente responde.
            2. Cliente pede revisão (volta a ser elegível).
            3. Cliente responde de novo.
            4. Dois eventos `answered` ficam registrados no histórico.
        """
        questions = briefing_a.snapshot_questions()
        first = questions[0]

        # 1ª resposta
        BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=first['id'],
            content_text='Primeira resposta.',
        )

        # Solicita revisão — reabre a pergunta
        BriefingService.request_review(
            briefing=briefing_a,
            portal_session=portal_session_a,
            question_id=first['id'],
            message='Quero reformular.',
        )

        # 2ª resposta — agora permitida, pois a pergunta voltou
        # a ser a próxima elegível
        BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=first['id'],
            content_text='Segunda resposta (após review).',
        )

        answered_events = BriefingEvent.objects.filter(
            briefing=briefing_a,
            kind=BriefingEvent.KIND_ANSWERED,
            question_id=first['id'],
        )
        assert answered_events.count() == 2

    def test_content_invalid_format_rejected(
        self, briefing_a, portal_session_a,
    ):
        from apps.briefings.exceptions import InvalidResponseFormatError

        questions = briefing_a.snapshot_questions()
        third = questions[2]  # allowed_response_formats=['text']

        # Responder as duas primeiras para liberar a terceira
        first, second = questions[0], questions[1]
        for q in (first, second):
            BriefingService.submit_answer(
                briefing_id=briefing_a.id,
                portal_session=portal_session_a,
                question_id=q['id'],
                content_text='ok',
            )

        # Agora `third` é a próxima elegível. Ela só aceita texto;
        # enviamos nada para forçar erro de formato.
        with pytest.raises(InvalidResponseFormatError):
            BriefingService.submit_answer(
                briefing_id=briefing_a.id,
                portal_session=portal_session_a,
                question_id=third['id'],
                content_text='',
            )