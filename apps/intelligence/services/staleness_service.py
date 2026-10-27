"""
StalenessService — marca insights anteriores como stale quando uma
execução nova os substitui.

REGRA
-----
Quando um run novo conclui com sucesso, os insights de runs
anteriores do MESMO cliente E MESMO briefing que têm `kind` coberto
pelo run novo passam a `is_stale=True`.

NÃO apaga nada. O insight antigo continua consultável, mas sinalizado
como desatualizado. A interface pode exibi-lo com aviso ou ocultá-lo
por padrão.
"""

import logging

from django.db import transaction

from apps.intelligence.models import AnalysisRun, InsightItem

logger = logging.getLogger('intelligence')


class StalenessService:

    @staticmethod
    def mark_previous_runs_stale(new_run: AnalysisRun) -> int:
        """
        Marca como stale os insights de runs anteriores compatíveis.

        Compatibilidade: mesmo workspace, mesmo cliente, mesmo briefing
        (incluindo ambos NULL para análises de cliente sem briefing).

        Retorna a quantidade de insights marcados.
        """
        new_kinds = list(
            InsightItem.objects
            .filter(run=new_run)
            .values_list('kind', flat=True)
            .distinct()
        )
        if not new_kinds:
            return 0

        qs = (
            InsightItem.objects
            .filter(
                workspace=new_run.workspace,
                client=new_run.client,
                briefing=new_run.briefing,
                kind__in=new_kinds,
                is_stale=False,
            )
            .exclude(run=new_run)
        )
        count = qs.count()
        if count == 0:
            return 0

        with transaction.atomic():
            updated = qs.update(is_stale=True)

        logger.info(
            'StalenessService: %d insights marcados como stale '
            '(run=%s, kinds=%s)',
            updated, new_run.id, new_kinds,
        )
        return updated