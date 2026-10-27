"""
JobService — agenda e reivindica jobs de análise de forma atômica.

CONCORRÊNCIA
------------
`claim_next_job()` abre uma transação, seleciona UM job pendente com
`select_for_update(skip_locked=True)` e o marca como `processing` ANTES
de liberar o lock. Dois workers concorrentes nunca reivindicam o mesmo
job.
"""

import hashlib
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.intelligence.models import AnalysisJob, InsightEvent, InsightItem

logger = logging.getLogger('intelligence')


class JobService:

    @staticmethod
    @transaction.atomic
    def schedule_analysis_job(
        *,
        workspace_id,
        client_id,
        event: InsightEvent,
        data_version: str,
        briefing_id=None,
    ) -> AnalysisJob:
        from apps.workspaces.models import Workspace
        from apps.clients.models import Client
        from apps.briefings.models import Briefing

        workspace = Workspace.objects.get(id=workspace_id)
        client = Client.objects.get(id=client_id)
        briefing = Briefing.objects.get(id=briefing_id) if briefing_id else None

        if briefing:
            target_kinds = [
                InsightItem.KIND_SUMMARY_BRIEFING,
                InsightItem.KIND_DESIRE,
                InsightItem.KIND_ATTENTION,
                InsightItem.KIND_TAG,
                InsightItem.KIND_RECOMMENDED_QUESTION,
                InsightItem.KIND_GAP,
                InsightItem.KIND_INCONSISTENCY,
                InsightItem.KIND_CROSS_INSIGHT,
                InsightItem.KIND_SUCCESS_CRITERIA,
                InsightItem.KIND_REFERENCE_ANALYSIS,
                InsightItem.KIND_RESTRICTION,
                InsightItem.KIND_READINESS_ASSESSMENT,
            ]
        else:
            # Ingestão sem briefing: analisa o cliente como um todo.
            # `KIND_SUMMARY_CLIENT` não existe em InsightItem. O
            # equivalente semântico é `KIND_CLIENT_PROFILE`, que já
            # está na lista abaixo. Não duplicar.
            target_kinds = [
                InsightItem.KIND_KNOWLEDGE_ACCUMULATED,
                InsightItem.KIND_PREFERENCE_PROFILE,
                InsightItem.KIND_HOW_TO_CONDUCT,
                InsightItem.KIND_CLIENT_PROFILE,
            ]

        kinds_str = ','.join(sorted(target_kinds))
        kinds_hash = hashlib.sha256(kinds_str.encode('utf-8')).hexdigest()

        job_key = ':'.join([
            str(workspace.id),
            str(client.id),
            str(briefing.id) if briefing else '',
            kinds_hash,
            data_version,
        ])

        job, created = AnalysisJob.objects.get_or_create(
            job_key=job_key,
            defaults={
                'workspace': workspace,
                'client': client,
                'briefing': briefing,
                'target_kinds': target_kinds,
                'data_version': data_version,
            },
        )

        if created:
            logger.info("Novo job agendado (ID=%s)", job.id)
        else:
            logger.info("Job existente reutilizado (ID=%s)", job.id)
        return job

    @staticmethod
    def claim_next_job() -> Optional[AnalysisJob]:
        """
        Reivindica atomicamente um job pendente.

        O `select_for_update(skip_locked=True)` dentro da transação
        garante que dois workers não peguem o mesmo job. A atualização
        para `processing` acontece ANTES da transação fechar — o lock
        cobre a reivindicação.
        """
        with transaction.atomic():
            job = (
                AnalysisJob.objects
                .select_for_update(skip_locked=True)
                .filter(status=AnalysisJob.STATUS_PENDING)
                .order_by('created_at')
                .first()
            )
            if job is None:
                return None

            job.status = AnalysisJob.STATUS_PROCESSING
            job.attempt_count += 1
            job.processing_started_at = timezone.now()
            job.save(update_fields=[
                'status', 'attempt_count', 'processing_started_at', 'updated_at',
            ])
            return job

    @staticmethod
    def mark_as_completed(job: AnalysisJob):
        job.status = AnalysisJob.STATUS_COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at', 'updated_at'])

    @staticmethod
    def mark_as_failed(job: AnalysisJob, error_message: str):
        job.status = AnalysisJob.STATUS_FAILED
        job.failed_at = timezone.now()
        job.last_error_message = error_message
        job.save(update_fields=['status', 'failed_at', 'last_error_message', 'updated_at'])