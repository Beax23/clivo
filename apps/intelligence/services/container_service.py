"""
ContainerService — monta a resposta dos containers fixos.

REGRA ARQUITETURAL
------------------
Os containers são estruturas FIXAS (Mesa, Cliente, Relatório). Este
service é a ÚNICA fonte de verdade para montar o payload de cada um.
Views e serializers delegam aqui — nunca inventam um container novo.

Filtragem:
    - Por `kind` válido do container.
    - Por cliente/workspace/briefing quando aplicável.
    - Ignora insights `is_stale=True` por padrão (a interface pode
      pedir para incluir).
"""

import logging
from typing import Dict, List, Optional

from apps.intelligence.models import InsightItem

logger = logging.getLogger('intelligence')


class ContainerService:

    @staticmethod
    def build_mesa(
        *,
        workspace,
        client=None,
        briefing=None,
        include_stale: bool = False,
    ) -> Dict:
        """
        Monta os cinco containers da Mesa.

        Retorna:
            {
                'containers': {
                    '01_desejos_prioridades': [insight, ...],
                    '02_pontos_atencao': [...],
                    '03_mudancas': [...],
                    '04_novidades': [...],
                    '05_resumo': [...],
                },
                'counts': {slot: int, ...},
            }
        """
        return ContainerService._build(
            container=InsightItem.CONTAINER_MESA,
            workspace=workspace,
            client=client,
            briefing=briefing,
            include_stale=include_stale,
        )

    @staticmethod
    def build_cliente(
        *,
        workspace,
        client,
        include_stale: bool = False,
    ) -> Dict:
        """Monta os cinco containers do Cliente."""
        return ContainerService._build(
            container=InsightItem.CONTAINER_CLIENTE,
            workspace=workspace,
            client=client,
            briefing=None,  # conhecimento do cliente é transversal a briefings
            include_stale=include_stale,
        )

    @staticmethod
    def build_relatorio(
        *,
        workspace,
        briefing,
        include_stale: bool = False,
    ) -> Dict:
        """Monta o relatório do briefing (8 containers fixos)."""
        return ContainerService._build(
            container=InsightItem.CONTAINER_RELATORIO,
            workspace=workspace,
            client=briefing.client,
            briefing=briefing,
            include_stale=include_stale,
        )

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    @staticmethod
    def _build(
        *,
        container: str,
        workspace,
        client,
        briefing,
        include_stale: bool,
    ) -> Dict:
        slots = InsightItem.CONTAINER_KINDS[container]
        all_kinds = InsightItem.kinds_for_container(container)

        qs = (
            InsightItem.objects
            .filter(workspace=workspace, kind__in=all_kinds)
            .select_related('client', 'briefing', 'run')
            .order_by('-created_at')
        )
        if client is not None:
            qs = qs.filter(client=client)
        if briefing is not None:
            qs = qs.filter(briefing=briefing)
        if not include_stale:
            qs = qs.filter(is_stale=False)

        by_kind = {}
        for item in qs:
            by_kind.setdefault(item.kind, []).append(item)

        containers = {}
        counts = {}
        for slot_name, slot_kinds in slots.items():
            collected = []
            for kind in slot_kinds:
                collected.extend(by_kind.get(kind, []))
            collected.sort(key=lambda i: i.created_at, reverse=True)
            containers[slot_name] = collected
            counts[slot_name] = len(collected)

        return {'containers': containers, 'counts': counts}