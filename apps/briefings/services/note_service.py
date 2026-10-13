"""
BriefingNoteService — Journal do arquiteto.

Notas privadas do escritório. Nunca expostas ao cliente.
Nunca enviadas automaticamente para Intelligence.
"""

import logging

from django.db import transaction

from apps.briefings.models import Briefing, BriefingNote
from apps.briefings.exceptions import (
    BriefingNoteNotFoundError,
    BriefingError,
)

logger = logging.getLogger('briefings')


class BriefingNoteService:

    @staticmethod
    @transaction.atomic
    def create_note(
        *,
        briefing: Briefing,
        author,
        content: str,
        question_id=None,
    ) -> BriefingNote:
        content = (content or '').strip()
        if not content:
            raise BriefingError('A anotação não pode ser vazia.')

        if question_id is not None:
            # Valida que a pergunta existe no snapshot
            snap = briefing.snapshot_question_by_id(question_id)
            if snap is None:
                raise BriefingError(
                    'Pergunta não encontrada no snapshot deste briefing.'
                )

        return BriefingNote.objects.create(
            briefing=briefing,
            question_id=question_id,
            author=author,
            content=content,
        )

    @staticmethod
    @transaction.atomic
    def update_note(
        *, note: BriefingNote, author, content: str,
    ) -> BriefingNote:
        content = (content or '').strip()
        if not content:
            raise BriefingError('A anotação não pode ser vazia.')
        note.content = content
        note.author = author  # registra quem editou por último
        note.save(update_fields=['content', 'author', 'updated_at'])
        return note

    @staticmethod
    @transaction.atomic
    def delete_note(*, note: BriefingNote) -> None:
        # DELETE real. Sem soft delete.
        note.delete()

    @staticmethod
    def get_or_raise(note_id, briefing) -> BriefingNote:
        try:
            note = BriefingNote.objects.filter(
                id=note_id, briefing=briefing,
            ).first()
        except (ValueError, TypeError):
            note = None
        if note is None:
            raise BriefingNoteNotFoundError('Anotação não encontrada.')
        return note

    @staticmethod
    def list_for_briefing(briefing: Briefing):
        return (
            BriefingNote.objects
            .filter(briefing=briefing)
            .select_related('author')
            .order_by('-created_at')
        )

    @staticmethod
    def list_for_question(briefing: Briefing, question_id):
        return (
            BriefingNote.objects
            .filter(briefing=briefing, question_id=question_id)
            .select_related('author')
            .order_by('-created_at')
        )