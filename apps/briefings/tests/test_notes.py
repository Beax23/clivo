"""
Testes do Journal (BriefingNote).
"""

import pytest

from apps.briefings.models import BriefingNote
from apps.briefings.services import BriefingNoteService
from apps.briefings.exceptions import (
    BriefingNoteNotFoundError,
    BriefingError,
)


URL_NOTES = '/api/briefings/{id}/notes/'


@pytest.mark.django_db
class TestNotesService:

    def test_create_general_note(self, briefing_a, user_owner):
        note = BriefingNoteService.create_note(
            briefing=briefing_a, author=user_owner,
            content='Nota geral sobre o briefing.',
        )
        assert note.question_id is None
        assert note.content == 'Nota geral sobre o briefing.'

    def test_create_note_for_question(self, briefing_a, user_owner):
        q = briefing_a.snapshot_questions()[0]
        note = BriefingNoteService.create_note(
            briefing=briefing_a, author=user_owner,
            content='Nota sobre a pergunta 1.',
            question_id=q['id'],
        )
        assert str(note.question_id) == str(q['id'])

    def test_create_note_for_unknown_question_fails(
        self, briefing_a, user_owner,
    ):
        import uuid
        with pytest.raises(BriefingError):
            BriefingNoteService.create_note(
                briefing=briefing_a, author=user_owner,
                content='Nota inválida.',
                question_id=uuid.uuid4(),
            )

    def test_empty_content_fails(self, briefing_a, user_owner):
        with pytest.raises(BriefingError):
            BriefingNoteService.create_note(
                briefing=briefing_a, author=user_owner,
                content='   ',
            )

    def test_delete_is_real_not_soft(self, briefing_a, user_owner):
        note = BriefingNoteService.create_note(
            briefing=briefing_a, author=user_owner, content='x',
        )
        note_id = note.id

        BriefingNoteService.delete_note(note=note)

        assert not BriefingNote.objects.filter(id=note_id).exists()


@pytest.mark.django_db
class TestNotesApi:

    def test_owner_creates_and_lists_notes(
        self, owner_client, briefing_a,
    ):
        url = URL_NOTES.format(id=briefing_a.id)

        resp = owner_client.post(
            url, {'content': 'Uma nota.'}, format='json',
        )
        assert resp.status_code == 201

        resp = owner_client.get(url)
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]['content'] == 'Uma nota.'

    def test_other_cannot_access_notes(
        self, other_client, briefing_a,
    ):
        url = URL_NOTES.format(id=briefing_a.id)
        resp = other_client.get(url)
        assert resp.status_code in (403, 404)