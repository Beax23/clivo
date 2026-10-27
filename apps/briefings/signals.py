"""
Signals do módulo briefings.

PUBLICAÇÃO PARA INTELLIGENCE
----------------------------
Quando um fato atômico é registrado em `BriefingEvent` (resposta,
nota, transcrição, pergunta complementar, etc.), o evento é publicado
para `IngestService` via `transaction.on_commit`.

`occurrence_id` = `BriefingEvent.id`. É estável, único e imutável.

PERGUNTAS COMPLEMENTARES
------------------------
Eventos `custom_question_added`, `custom_question_removed` e
`supplementary_completed` são publicados para `intelligence` como
`InsightEvent` com `source_kind` próprio. Isso permite que a
inteligência reanalise o briefing quando o arquiteto continua a
conversa após a conclusão do bloco original.

EXCLUSÃO DE BRIEFING
--------------------
Quando um `Briefing` é excluído, publicamos um evento de invalidação
via `pre_delete`, para que o `intelligence` possa marcar insights
anteriores como stale e reconciliar o conhecimento do cliente.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.briefings.models import BriefingEvent, Briefing

logger = logging.getLogger('briefings')


_KINDS_INGESTED = frozenset({
    BriefingEvent.KIND_ANSWERED,
    BriefingEvent.KIND_CLARIFICATION_REQUESTED,
    BriefingEvent.KIND_REVIEW_REQUESTED,
    BriefingEvent.KIND_TRANSCRIPTION_GENERATED,
    BriefingEvent.KIND_NOTE_CREATED,
    BriefingEvent.KIND_NOTE_UPDATED,
    BriefingEvent.KIND_NOTE_DELETED,
    BriefingEvent.KIND_CUSTOM_QUESTION_ADDED,
    BriefingEvent.KIND_CUSTOM_QUESTION_REMOVED,
    BriefingEvent.KIND_SUPPLEMENTARY_COMPLETED,
})


def _source_kind_for_event(event: BriefingEvent) -> str:
    """
    Traduz o `kind` de `BriefingEvent` para o `source_kind` de
    `InsightEvent`. Mapeamento explícito, sem heurística.
    """
    from apps.intelligence.models import InsightEvent

    return {
        BriefingEvent.KIND_ANSWERED: InsightEvent.SOURCE_KIND_BRIEFING_ANSWER,
        BriefingEvent.KIND_CLARIFICATION_REQUESTED: InsightEvent.SOURCE_KIND_BRIEFING_ANSWER,
        BriefingEvent.KIND_REVIEW_REQUESTED: InsightEvent.SOURCE_KIND_BRIEFING_ANSWER,
        BriefingEvent.KIND_TRANSCRIPTION_GENERATED: InsightEvent.SOURCE_KIND_BRIEFING_ANSWER,
        BriefingEvent.KIND_NOTE_CREATED: InsightEvent.SOURCE_KIND_BRIEFING_NOTE_CREATED,
        BriefingEvent.KIND_NOTE_UPDATED: InsightEvent.SOURCE_KIND_BRIEFING_NOTE_UPDATED,
        BriefingEvent.KIND_NOTE_DELETED: InsightEvent.SOURCE_KIND_BRIEFING_NOTE_DELETED,
        BriefingEvent.KIND_CUSTOM_QUESTION_ADDED: (
            InsightEvent.SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_ADDED
        ),
        BriefingEvent.KIND_CUSTOM_QUESTION_REMOVED: (
            InsightEvent.SOURCE_KIND_BRIEFING_SUPPLEMENTARY_QUESTION_REMOVED
        ),
        BriefingEvent.KIND_SUPPLEMENTARY_COMPLETED: (
            InsightEvent.SOURCE_KIND_BRIEFING_SUPPLEMENTARY_COMPLETED
        ),
    }[event.kind]


@receiver(post_save, sender=BriefingEvent)
def publish_briefing_event_to_intelligence(
    sender, instance, created, **kwargs,
):
    if not created:
        return

    event = instance
    if event.kind not in _KINDS_INGESTED:
        return

    if event.briefing_id is None:
        return

    def _ingest():
        try:
            from apps.intelligence.services import IngestService

            briefing = event.briefing
            if briefing is None:
                return

            IngestService.ingest_change_event(
                workspace_id=briefing.workspace_id,
                client_id=briefing.client_id,
                briefing_id=briefing.id,
                source_kind=_source_kind_for_event(event),
                source_ref=(
                    str(event.question_id) if event.question_id
                    else str(event.content.get('note_id') or '')
                ),
                occurrence_id=str(event.id),
                data_version=str(briefing.updated_at.timestamp()),
            )
        except Exception:
            logger.exception(
                'Falha ao publicar BriefingEvent=%s para intelligence',
                event.id,
            )

    transaction.on_commit(_ingest)


@receiver(pre_delete, sender=Briefing)
def publish_briefing_invalidation(sender, instance, **kwargs):
    briefing_id = instance.id
    workspace_id = instance.workspace_id
    client_id = instance.client_id
    updated_at = instance.updated_at.isoformat() if instance.updated_at else ''

    def _ingest():
        try:
            from apps.intelligence.services import IngestService
            from apps.intelligence.models import InsightEvent

            IngestService.ingest_change_event(
                workspace_id=workspace_id,
                client_id=client_id,
                briefing_id=briefing_id,
                source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
                source_ref=f'briefing.deleted:{briefing_id}',
                occurrence_id=(
                    f'briefing.deleted:{briefing_id}:{timezone.now().isoformat()}'
                ),
                data_version=updated_at,
            )
        except Exception:
            logger.exception(
                'Falha ao publicar invalidação de briefing=%s',
                briefing_id,
            )

    transaction.on_commit(_ingest)