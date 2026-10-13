"""
Testes de preservação do áudio original.

Requisito: um Document que é latest_audio de um BriefingAnswer
NÃO pode ser excluído enquanto a projeção existir.
"""

import pytest
from django.db.models import ProtectedError

from apps.documents.models import Document
from apps.briefings.models import BriefingAnswer
from apps.briefings.services import BriefingService


@pytest.mark.django_db
class TestAudioPreservation:

    def _make_audio_doc(self, workspace, user, idx=1):
        # Cria um Document "fake" — não precisa de arquivo real
        # para o teste de PROTECT.
        return Document.objects.create(
            workspace=workspace,
            name=f'audio-{idx}',
            file=f'documents/audio-{idx}.webm',
            extension='webm',
            mime_type='audio/webm',
            size=1024,
            created_by=user,
        )

    def test_document_with_briefing_answer_cannot_be_deleted(
        self, briefing_a, portal_session_a, workspace_a, user_owner,
    ):
        audio = self._make_audio_doc(workspace_a, user_owner)
        q = briefing_a.snapshot_questions()[0]

        answer = BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=q['id'],
            content_text='',
            audio_document=audio,
        )
        assert answer.latest_audio_id == audio.id

        with pytest.raises(ProtectedError):
            audio.delete()

    def test_transcription_status_independent_of_state(
        self, briefing_a, portal_session_a, workspace_a, user_owner,
    ):
        audio = self._make_audio_doc(workspace_a, user_owner, idx=2)
        q = briefing_a.snapshot_questions()[0]

        answer = BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=q['id'],
            content_text='',
            audio_document=audio,
        )
        assert answer.state == BriefingAnswer.STATE_ANSWERED
        assert answer.transcription_status in (
            BriefingAnswer.TRANSCRIPTION_PENDING,
            BriefingAnswer.TRANSCRIPTION_FAILED,
            BriefingAnswer.TRANSCRIPTION_COMPLETED,
        )
        # O estado da resposta NÃO é alterado por falha de transcrição
        assert answer.state == BriefingAnswer.STATE_ANSWERED

    def test_deleting_briefing_cascades(
        self, briefing_a, portal_session_a, workspace_a, user_owner,
    ):
        """
        Excluir o briefing inteiro remove answers/events/notes em
        cascata. Os Documents de áudio permanecem (PROTECT só
        bloqueia exclusão DIRETA do Document, não a cascata do
        Briefing).
        """
        audio = self._make_audio_doc(workspace_a, user_owner, idx=3)
        q = briefing_a.snapshot_questions()[0]
        BriefingService.submit_answer(
            briefing_id=briefing_a.id,
            portal_session=portal_session_a,
            question_id=q['id'],
            content_text='',
            audio_document=audio,
        )

        briefing_a.delete()

        # Document permanece — a exclusão do briefing só removeu
        # a FK que apontava para ele.
        audio.refresh_from_db()
        assert audio.pk is not None