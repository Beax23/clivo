"""
IngestService — porta de entrada para novos eventos de inteligência.

FRONTEIRA
---------
Este serviço recebe apenas IDs e metadados — nunca instâncias de
models de outros módulos. A resolução dos objetos é feita pelo
JobService, que por sua vez usa contratos públicos.

IDEMPOTÊNCIA
------------
A `dedupe_key` inclui `occurrence_id`, que distingue eventos atômicos
legítimos (ex: duas edições na mesma nota) de reentrância do mesmo
evento. Quem chama é responsável por fornecer um `occurrence_id`
estável para o fato (ex: UUID do evento de origem, updated_at).
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
        briefing_id=None,
        source_ref: str = '',
        data_version: str,
    ):
        """
        Registra um evento de mudança e agenda uma análise.

        Retorna (event, created).
        """
        from apps.workspaces.models import Workspace
        from apps.clients.models import Client
        from apps.briefings.models import Briefing

        try:
            workspace = Workspace.objects.get(id=workspace_id)
            client = Client.objects.get(id=client_id)
            briefing = Briefing.objects.get(id=briefing_id) if briefing_id else None
        except Exception as exc:
            logger.exception('Falha ao resolver objetos do evento de ingestão')
            return (None, False)

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
            logger.info("Evento duplicado ignorado (dedupe_key=%s)", dedupe_key)
            return (event, False)

        logger.info("Novo evento registrado: %s", source_kind)

        JobService.schedule_analysis_job(
            workspace_id=workspace.id,
            client_id=client.id,
            briefing_id=briefing.id if briefing else None,
            event=event,
            data_version=data_version,
        )

        return (event, True)