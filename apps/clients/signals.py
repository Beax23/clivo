"""
Signals do módulo clients.

PUBLICAÇÃO PARA INTELLIGENCE
----------------------------
O `ClientEventEmitter` publica `client_event` (django.dispatch.Signal).
Este módulo escuta e encaminha os eventos relevantes para
`IngestService`, via `transaction.on_commit`.

Eventos operacionais (`portal.invitation_sent`, `portal.opened`,
`portal.feedback_received`) NÃO são encaminhados — não mudam o
conhecimento do cliente.

`occurrence_id` para `client.updated` = `signal_name:occurred_at`.
Para eventos de nota de CLIENTE = `note_id:occurred_at`. Para
`portal.context_edited` = `client_id:context_hash` (SEM occurred_at,
porque o `occurred_at` muda a cada save mesmo sem mudar o conteúdo
— sem essa correção, cada save do cliente gera um evento duplicado).

NOTAS DE CLIENTE vs NOTAS DE BRIEFING
-------------------------------------
`ClientNote` (este módulo) NÃO é `BriefingNote` (do app `briefings`).
Notas de cliente usam `SOURCE_KIND_CLIENT_NOTE_*` no `InsightEvent`.

EXCLUSÃO DE CLIENTE
-------------------
`Client` cascateia em `Briefing`, `ClientNote`, `ClientPortalSession`,
etc. O `InsightItem` do cliente tem `on_delete=CASCADE` no FK
`client` — excluir o cliente DESTRÓI os insights. Este signal
publica um evento de invalidação `pre_delete`, mas a preservação
histórica real exigiria mudar o FK em `intelligence`. Documentado
como pendência.

CAPTURA IMUTÁVEL ANTES DO COMMIT
--------------------------------
O `on_commit` roda DEPOIS que a transação fecha. Se o `Client` foi
apagado em CASCADE antes do callback rodar, `Client.objects.filter`
retorna `None` — o callback trata sem fazer nada. Os IDs
(`client_id`, `workspace_id`) são capturados ANTES do `on_commit`.
"""

import logging

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.clients.events import client_event
from apps.clients.models import Client

logger = logging.getLogger('clients')


# Eventos que alimentam o conhecimento do cliente.
_INGESTED_SIGNALS = frozenset({
    'client.updated',
    'note.created',
    'note.updated',
    'note.deleted',
    'portal.context_edited',
})


def _map_to_insight_source(signal_name: str) -> str:
    """
    Traduz o sinal de `clients` para `InsightEvent.SOURCE_KIND_*`.
    """
    from apps.intelligence.models import InsightEvent

    mapping = {
        'client.updated': InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
        'note.created': InsightEvent.SOURCE_KIND_CLIENT_NOTE_CREATED,
        'note.updated': InsightEvent.SOURCE_KIND_CLIENT_NOTE_UPDATED,
        'note.deleted': InsightEvent.SOURCE_KIND_CLIENT_NOTE_DELETED,
        'portal.context_edited': InsightEvent.SOURCE_KIND_CLIENT_CONTEXT_UPDATED,
    }
    return mapping.get(signal_name, '')


@receiver(client_event)
def forward_client_event_to_intelligence(
    sender, signal_name, client_id, client_name, actor_email,
    occurred_at, **kwargs,
):
    """
    Encaminha o evento de domínio para `IngestService`.

    Best-effort: falha de ingestão não derruba a operação de origem.
    """
    if signal_name not in _INGESTED_SIGNALS:
        return

    source_kind = _map_to_insight_source(signal_name)
    if not source_kind:
        return

    # occurrence_id: distinguir edições legítimas sucessivas.
    #
    #   - note.*: usa note_id + occurred_at. Cada edição da nota
    #     tem um occurred_at diferente — correto.
    #
    #   - portal.context_edited: usa client_id + context_hash,
    #     SEM occurred_at. O `occurred_at` muda a cada save, então
    #     incluí-lo geraria evento duplicado mesmo sem mudar o
    #     contexto. O hash muda apenas quando o conteúdo muda —
    #     que é o que queremos.
    #
    #   - demais (client.updated): usa signal_name + occurred_at.
    #     Cada save do cliente é um fato atômico legítimo.
    note_id = kwargs.get('note_id') or ''
    if signal_name.startswith('note.') and note_id:
        occurrence_id = (
            f'{note_id}:{occurred_at.isoformat() if occurred_at else ""}'
        )
        source_ref = str(note_id)
    elif signal_name == 'portal.context_edited':
        from apps.clients.public import get_client_context_hash
        context_hash = get_client_context_hash(client_id) or ''
        occurrence_id = f'{client_id}:{context_hash}'
        source_ref = ''
    else:
        occurrence_id = (
            f'{signal_name}:{occurred_at.isoformat() if occurred_at else ""}'
        )
        source_ref = ''

    def _ingest():
        try:
            from apps.clients.models import Client
            from apps.intelligence.services import IngestService

            client = Client.objects.filter(id=client_id).first()
            if client is None:
                return

            IngestService.ingest_change_event(
                workspace_id=client.workspace_id,
                client_id=client.id,
                briefing_id=None,  # cliente é transversal a briefings
                source_kind=source_kind,
                source_ref=source_ref,
                occurrence_id=occurrence_id,
                data_version=client.updated_at.isoformat(),
            )
        except Exception:
            logger.exception(
                'Falha ao publicar client_event=%s (client=%s) '
                'para intelligence',
                signal_name, client_id,
            )

    transaction.on_commit(_ingest)


@receiver(pre_delete, sender=Client)
def publish_client_deletion_invalidation(sender, instance, **kwargs):
    """
    Publica um evento de invalidação quando um cliente é excluído.

    Executado ANTES do CASCADE. Como `IngestService` usa
    `on_commit`, a ingestão só roda DEPOIS do DELETE.

    AVISO: o `InsightItem.client` FK é `on_delete=CASCADE`. Neste
    momento, excluir o `Client` DESTRÓI os insights do cliente.
    Este evento serve para o `intelligence` reagir (se um dia o FK
    virar PROTECT ou SET_NULL), mas não previne a perda.
    """
    client_id = instance.id
    workspace_id = instance.workspace_id
    updated_at = instance.updated_at.isoformat() if instance.updated_at else ''

    def _ingest():
        try:
            from apps.intelligence.services import IngestService
            from apps.intelligence.models import InsightEvent

            IngestService.ingest_change_event(
                workspace_id=workspace_id,
                client_id=client_id,
                briefing_id=None,
                source_kind=InsightEvent.SOURCE_KIND_CLIENT_UPDATED,
                source_ref=f'client.deleted:{client_id}',
                occurrence_id=(
                    f'client.deleted:{client_id}:'
                    f'{updated_at or "unknown"}'
                ),
                data_version=updated_at,
            )
        except Exception:
            logger.exception(
                'Falha ao publicar invalidação de client=%s',
                client_id,
            )

    transaction.on_commit(_ingest)