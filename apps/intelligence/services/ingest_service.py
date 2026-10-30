"""
IngestService — porta de entrada para novos eventos de inteligência.

FRONTEIRA
---------
Este serviço recebe apenas IDs e metadados — nunca instâncias de
models de outros módulos. A resolução dos objetos é feita aqui,
via imports diretos dos models (mesmo padrão já usado no arquivo
original).

IDEMPOTÊNCIA
------------
A `dedupe_key` inclui `occurrence_id`, que distingue eventos atômicos
legítimos (ex: duas edições na mesma nota) de reentrância do mesmo
evento. Quem chama é responsável por fornecer um `occurrence_id`
estável para o fato (ex: UUID do evento de origem, updated_at).

RETORNO
-------
Passou a devolver `(event, job, created)` em vez de `(event, created)`.
O `job` é o `AnalysisJob` agendado (ou reutilizado) para o evento.
Isso permite que a view de `reanalyze` devolva o `job_id` ao
frontend sem precisar buscar o "job mais recente" por heurística.
"""

import logging

from django.db import transaction

from apps.intelligence.models import InsightEvent
from apps.intelligence.services.job_service import JobService

logger = logging.getLogger('intelligence')


class IngestService:

    @staticmethod
    @transaction.atomic
    def ingest_change_event(
        *,
        workspace_id,
        client_id,
        source_kind: str,
        occurrence_id: str,
        data_version: str,
        briefing_id=None,
        source_ref: str = '',
    ):
        """
        Registra um evento de mudança e agenda uma análise.

        Retorna (event, job, created).

        `job` é o AnalysisJob agendado (novo ou já existente para o
        mesmo job_key). Nunca é None em caso de sucesso.
        """
        from apps.workspaces.models import Workspace
        from apps.clients.models import Client
        from apps.briefings.models import Briefing

        try:
            workspace = Workspace.objects.get(id=workspace_id)
            client = Client.objects.get(id=client_id)
            briefing = Briefing.objects.get(id=briefing_id) if briefing_id else None
        except Exception:
            logger.exception('Falha ao resolver objetos do evento de ingestão')
            return (None, None, False)

        dedupe_key = ':'.join([
            str(workspace.id),
            str(client.id),
            str(briefing.id) if briefing else '',
            source_kind,
            source_ref or '',
            occurrence_id,
        ])

        event, created = InsightEvent.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                'workspace': workspace,
                'client': client,
                'briefing': briefing,
                'source_kind': source_kind,
                'source_ref': source_ref,
                'occurrence_id': occurrence_id,
            },
        )

        if not created:
            logger.info(
                'Evento duplicado ignorado (dedupe_key=%s)', dedupe_key,
            )
            # Mesmo quando o evento é duplicado, o job correspondente
            # já existe. Recupera-o para devolver ao chamador.
            job = JobService.find_job_for_event(
                workspace_id=workspace.id,
                client_id=client.id,
                briefing_id=briefing.id if briefing else None,
                data_version=data_version,
            )
            return (event, job, False)

        logger.info('Novo evento registrado: %s', source_kind)

        job = JobService.schedule_analysis_job(
            workspace_id=workspace.id,
            client_id=client.id,
            briefing_id=briefing.id if briefing else None,
            event=event,
            data_version=data_version,
        )

        return (event, job, True)