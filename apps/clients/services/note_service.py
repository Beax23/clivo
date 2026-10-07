"""
NoteService — CRUD de anotações.
"""

from typing import List, Optional

from apps.clients.models import Client, ClientNote
from apps.clients.exceptions import NoteNotFoundError
from apps.clients.events import ClientEventEmitter


class NoteService:

    @staticmethod
    def list_for_client(client: Client) -> List[ClientNote]:
        return list(
            ClientNote.objects
            .filter(client=client)
            .select_related('author')
            .order_by('-is_pinned', '-created_at')
        )

    @staticmethod
    def get_for_client(client: Client, note_id) -> ClientNote:
        try:
            return ClientNote.objects.get(id=note_id, client=client)
        except (ClientNote.DoesNotExist, ValueError):
            raise NoteNotFoundError('Nota não encontrada')

    @staticmethod
    def create_note(
        client: Client,
        author,
        content: str,
        is_pinned: bool = False,
        request=None,
    ) -> ClientNote:
        content = (content or '').strip()
        if not content:
            raise ValueError('O conteúdo da anotação é obrigatório')

        note = ClientNote.objects.create(
            client=client,
            author=author,
            content=content,
            is_pinned=is_pinned,
        )
        ClientEventEmitter.note_created(
            client=client, note=note, actor=author, request=request,
        )
        return note

    @staticmethod
    def update_note(
        note: ClientNote,
        actor,
        content: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        request=None,
    ) -> ClientNote:
        fields = []

        if content is not None:
            content = content.strip()
            if not content:
                raise ValueError('O conteúdo da anotação é obrigatório')
            note.content = content
            fields.append('content')

        if is_pinned is not None:
            note.is_pinned = is_pinned
            fields.append('is_pinned')

        if fields:
            note.save(update_fields=fields + ['updated_at'])
            ClientEventEmitter.note_updated(
                client=note.client, note=note, actor=actor, request=request,
            )

        return note

    @staticmethod
    def delete_note(note: ClientNote, actor=None, request=None) -> None:
        client = note.client
        note_id = note.id
        note.delete()
        ClientEventEmitter.note_deleted(
            client=client, note_id=note_id, actor=actor, request=request,
        )