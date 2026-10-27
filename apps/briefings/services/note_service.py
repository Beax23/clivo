"""
BriefingNoteService — Journal do arquiteto.

Notas privadas do escritório. Nunca expostas ao cliente.
Nunca enviadas automaticamente para Intelligence.

Toda mudança emite um `BriefingEvent` (`note.created`,
`note.updated`, `note.deleted`) para que a inteligência acompanhe
a evolução do conhecimento do cliente sobre o briefing.

Esses eventos NUNCA são expostos ao portal. O portal serializer
(`PortalBriefingSerializer`) filtra apenas respostas/perguntas e
não consulta `BriefingNote`.

PIN
---
`is_pinned` é organização, não conteúdo. Não emite evento de
`note.updated` — apenas atualiza `updated_at` e a ordenação.
"""

import logging

from django.db import transaction

from apps.briefings.models import Briefing, BriefingNote, BriefingEvent
from apps.briefings.exceptions import (
    BriefingNoteNotFoundError,
    BriefingError,
)
from apps.briefings.services.event_service import BriefingEventService

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
        is_pinned: bool = False,
    ) -> BriefingNote:
        content = (content or '').strip()
        if not content:
            raise BriefingError('A anotação não pode ser vazia.')

        if question_id is not None:
            snap = briefing.snapshot_question_by_id(question_id)
            if snap is None:
                raise BriefingError(
                    'Pergunta não encontrada no snapshot deste briefing.'
                )

        note = BriefingNote.objects.create(
            briefing=briefing,
            question_id=question_id,
            author=author,
            content=content,
            is_pinned=bool(is_pinned),
        )

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_NOTE_CREATED,
            user=author,
            question_id=question_id,
            content={
                'note_id': str(note.id),
                'content_length': len(content),
            },
        )
        return note

    @staticmethod
    @transaction.atomic
    def update_note(
        *,
        note: BriefingNote,
        author,
        content: str = None,
        is_pinned: bool = None,
    ) -> BriefingNote:
        """
        Atualiza `content` e/ou `is_pinned`.

        Emite `note.updated` SOMENTE se `content` mudou. Fixar/desafixar
        não emite evento de conteúdo.
        """
        fields = []
        previous_length = None
        new_length = None
        content_changed = False

        if content is not None:
            content = (content or '').strip()
            if not content:
                raise BriefingError('A anotação não pode ser vazia.')
            if content != (note.content or ''):
                previous_length = len(note.content or '')
                new_length = len(content)
                note.content = content
                note.author = author
                fields.extend(['content', 'author'])
                content_changed = True

        if is_pinned is not None:
            is_pinned = bool(is_pinned)
            if is_pinned != note.is_pinned:
                note.is_pinned = is_pinned
                fields.append('is_pinned')

        if not fields:
            return note

        fields.append('updated_at')
        note.save(update_fields=list(set(fields)))

        if content_changed:
            BriefingEventService.log(
                briefing=note.briefing,
                kind=BriefingEvent.KIND_NOTE_UPDATED,
                user=author,
                question_id=note.question_id,
                content={
                    'note_id': str(note.id),
                    'previous_content_length': previous_length,
                    'new_content_length': new_length,
                },
            )

        return note

    @staticmethod
    @transaction.atomic
    def set_pinned(
        *,
        note: BriefingNote,
        is_pinned: bool,
    ) -> BriefingNote:
        """
        Fixa/desafixa uma nota. Idempotente.
        """
        is_pinned = bool(is_pinned)
        if note.is_pinned == is_pinned:
            return note
        note.is_pinned = is_pinned
        note.save(update_fields=['is_pinned', 'updated_at'])
        return note

    @staticmethod
    @transaction.atomic
    def delete_note(*, note: BriefingNote, actor=None) -> None:
        briefing = note.briefing
        note_id = note.id
        question_id = note.question_id
        author = note.author

        note.delete()

        BriefingEventService.log(
            briefing=briefing,
            kind=BriefingEvent.KIND_NOTE_DELETED,
            user=(
                actor if (actor and getattr(actor, 'is_authenticated', False))
                else author
            ),
            question_id=question_id,
            content={'note_id': str(note_id)},
        )

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
            .order_by('-is_pinned', '-created_at')
        )

    @staticmethod
    def list_for_question(briefing: Briefing, question_id):
        return (
            BriefingNote.objects
            .filter(briefing=briefing, question_id=question_id)
            .select_related('author')
            .order_by('-is_pinned', '-created_at')
        )