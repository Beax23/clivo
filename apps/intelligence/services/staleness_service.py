"""
StalenessService — marca insights anteriores como stale quando uma
execução nova os substitui.

REGRA
-----
Um run novo torna stale os insights de runs anteriores do MESMO
workspace e MESMO cliente cujos `kind` estão cobertos pelo run novo.
O escopo de comparação cobre:

    - briefing=X   (quando o run novo tem briefing)
    - briefing=None (para kinds de cliente que o run também produz)

Por quê os dois escopos: um run com briefing gera kinds de briefing
E kinds de cliente. Os kinds de cliente (preference.profile,
client.profile, how_to_conduct, knowledge.accumulated) têm
`briefing=None` no InsightItem, mesmo tendo sido produzidos por um
run com briefing. Comparar só pelo `briefing` do run novo deixaria
esses insights antigos "vivos" — o que mostraria duas versões
concorrentes nos containers do Cliente.

NÃO apaga nada. O insight antigo continua consultável, mas sinalizado
como desatualizado. A interface pode exibi-lo com aviso ou ocultá-lo
por padrão.
"""

import logging

from django.db import transaction
from django.db.models import Q

from apps.intelligence.models import AnalysisRun, InsightItem

logger = logging.getLogger('intelligence')


class StalenessService:

    @staticmethod
    def mark_previous_runs_stale(new_run: AnalysisRun) -> int:
        """
        Marca como stale os insights de runs anteriores compatíveis.

        Compatibilidade:
            - mesmo workspace
            - mesmo cliente
            - mesmo `briefing` do run (para kinds de briefing)
              OU `briefing=None` (para kinds de cliente que o run
              também produz)

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

        # Escopo do briefing: o `briefing` do run novo, se houver.
        # Insights de cliente têm `briefing=None` mesmo quando
        # produzidos por um run com briefing.
        scope_q = Q(briefing=new_run.briefing)
        if new_run.briefing_id is not None:
            scope_q |= Q(briefing__isnull=True)

        qs = (
            InsightItem.objects
            .filter(
                scope_q,
                workspace=new_run.workspace,
                client=new_run.client,
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
            '(run=%s, kinds=%s, briefing=%s)',
            updated, new_run.id, new_kinds, new_run.briefing_id,
        )
        return updated