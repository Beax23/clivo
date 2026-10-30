"""
Signals do módulo briefings.

PUBLICAÇÃO PARA INTELLIGENCE
----------------------------
Quando um fato atômico é registrado em `BriefingEvent` (resposta,
nota, transcrição, etc.), o evento é publicado para `IngestService`
via `transaction.on_commit`. Isso garante que:

    1. O `IngestService` só é chamado APÓS o commit de `briefings`.
    2. O cliente recebe a resposta mesmo se o `intelligence` estiver
       fora do ar — a ingestão roda fora da transação do usuário.
    3. Se a ingestão falhar, o `BriefingEvent` já está persistido.

`occurrence_id` = `BriefingEvent.id`. É estável, único e imutável.
Não usar `created_at` (pode colidir em testes rápidos).

CAPTURA IMUTÁVEL ANTES DO COMMIT
--------------------------------
O `on_commit` roda DEPOIS que a transação fecha. Se o `BriefingEvent`
foi criado e o `Briefing` foi apagado em seguida (CASCADE), o objeto
`event` ainda existe em memória, mas `event.briefing` levanta
`RelatedObjectDoesNotExist` — o briefing já não existe no banco.

Por isso, capturamos `workspace_id`, `client_id`, `briefing_id` e
`source_kind` ANTES de registrar o `on_commit`. O callback usa
apenas esses valores imutáveis, nunca acessa `event.briefing`.

EVENTO DE CONCLUSÃO
-------------------
`KIND_COMPLETED` está em `_KINDS_INGESTED`. Quando o cliente
responde a última pergunta obrigatória, o briefing vira `completed`
e um segundo job é agendado com `data_version` novo — garantindo
que a análise final reflita o estado `completed` (não apenas o
estado `in_progress` capturado no `KIND_ANSWERED` anterior).

O `intelligence` não tem `SOURCE_KIND_BRIEFING_COMPLETED`; mapeamos
para `SOURCE_KIND_BRIEFING_ANSWER` — semanticamente, é uma resposta
que concluiu o briefing. Não inventamos um kind novo.

EXCLUSÃO DE BRIEFING
--------------------
Quando um `Briefing` é excluído, publicamos um evento de invalidação
via `pre_delete`, para que o `intelligence` possa:
    - marcar insights anteriores como stale;
    - reconciliar o conhecimento do cliente sem o briefing de origem.

O evento usa `source_kind='client.updated'` porque o `Intelligence`
não tem um kind `briefing.deleted` — e o efeito prático (reprocessar
o conhecimento do cliente) é o mesmo.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.briefings.models import BriefingEvent, Briefing

logger = logging.getLogger('briefings')


# Fatos que alimentam o conhecimento do cliente. Excluímos eventos
# operacionais (pause, resume, completion_email_sent) porque eles
# não mudam o conteúdo analisável.
#
# KIND_COMPLETED está incluído: dispara um segundo job após a
# conclusão, garantindo que a análise final reflita o estado
# `completed`.
_KINDS_INGESTED = frozenset({
    BriefingEvent.KIND_ANSWERED,
    BriefingEvent.KIND_CLARIFICATION_REQUESTED,
    BriefingEvent.KIND_REVIEW_REQUESTED,
    BriefingEvent.KIND_TRANSCRIPTION_GENERATED,
    BriefingEvent.KIND_NOTE_CREATED,
    BriefingEvent.KIND_NOTE_UPDATED,
    BriefingEvent.KIND_NOTE_DELETED,
    BriefingEvent.KIND_COMPLETED,
})


def _source_kind_for_event_kind(kind: str) -> str:
    """
    Traduz o `kind` de `BriefingEvent` para o `source_kind` de
    `InsightEvent`. Mapeamento explícito, sem heurística.

    Recebe a string `kind`, não o objeto `event` — o `on_commit`
    pode rodar depois que o `BriefingEvent` foi CASCADE-apagado,
    e acessar `event.kind` ainda funciona (está em memória), mas
    é mais seguro passar apenas o valor imutável.
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
        # Conclusão mapeada para answer: semanticamente, é uma
        # resposta que concluiu o briefing. Não inventamos kind novo.
        BriefingEvent.KIND_COMPLETED: InsightEvent.SOURCE_KIND_BRIEFING_ANSWER,
    }[kind]


@receiver(post_save, sender=BriefingEvent)
def publish_briefing_event_to_intelligence(
    sender, instance, created, **kwargs,
):
    """
    Publica o evento para `IngestService` via `on_commit`.

    O `on_commit` garante que a ingestão não roda dentro da
    transação de `briefings`. Se o processo cair entre commit e
    ingestão, o evento é perdido — aceitável, porque a resposta
    do cliente NÃO pode ser bloqueada pelo `intelligence`.

    IMPORTANTE: os dados são capturados ANTES do `on_commit`. O
    callback usa apenas valores imutáveis (`briefing_id`,
    `workspace_id`, `client_id`, `source_kind`, `source_ref`,
    `occurrence_id`). NUNCA acessa `event.briefing` — o briefing
    pode ter sido CASCADE-apagado antes do callback rodar.
    """
    if not created:
        return

    event = instance
    if event.kind not in _KINDS_INGESTED:
        return

    if event.briefing_id is None:
        return

    # Captura IMUTÁVEL antes do commit.
    briefing_id = event.briefing_id
    try:
        briefing = event.briefing
        if briefing is None:
            return
        workspace_id = briefing.workspace_id
        client_id = briefing.client_id
    except Exception:
        # Briefing já foi apagado em CASCADE — não publica.
        return

    source_kind = _source_kind_for_event_kind(event.kind)
    source_ref = (
        str(event.question_id) if event.question_id
        else str(event.content.get('note_id') or '')
    )
    occurrence_id = str(event.id)
    # `event.created_at` é imutável — diferente de
    # `briefing.updated_at`, que muda a cada save do briefing.
    data_version = str(event.created_at.timestamp())

    def _ingest():
        try:
            from apps.intelligence.services import IngestService

            IngestService.ingest_change_event(
                workspace_id=workspace_id,
                client_id=client_id,
                briefing_id=briefing_id,
                source_kind=source_kind,
                source_ref=source_ref,
                occurrence_id=occurrence_id,
                data_version=data_version,
            )
        except Exception:
            logger.exception(
                'Falha ao publicar BriefingEvent=%s para intelligence',
                occurrence_id,
            )

    transaction.on_commit(_ingest)


@receiver(pre_delete, sender=Briefing)
def publish_briefing_invalidation(sender, instance, **kwargs):
    """
    Publica um evento de invalidação quando um briefing é excluído.

    Executado ANTES do CASCADE. Como `IngestService` usa
    `on_commit`, a ingestão só roda DEPOIS do DELETE — quando o
    `Briefing` já não existe. O `intelligence` deve tratar isso:
    `ingest_change_event` aceita `briefing_id` e, se o briefing
    não existir mais, o `JobService` cria um job de cliente (sem
    briefing) para reconciliar o conhecimento acumulado.

    Captura os IDs antes do `on_commit` — o `instance` ainda existe
    em memória, mas o registro do banco será apagado pelo CASCADE.
    """
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