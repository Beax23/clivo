"""
TagService — transição de estado de tags com histórico imutável.

REGRA ARQUITETURAL
------------------
Toda mudança em `InsightItem.review_state` para itens de kind='tag'
DEVE passar por este service. Ele grava uma linha em
`InsightTagHistory` a cada transição, preservando quem, quando e
qual era o estado anterior.

Insights de outros kinds podem usar `review_state` diretamente —
mas a diretriz de histórico só se aplica a tags.
"""

import logging
from typing import Optional

from django.db import transaction

from apps.intelligence.models import InsightItem, InsightTagHistory
from apps.intelligence.exceptions import IntelligenceError

logger = logging.getLogger('intelligence')


class InvalidTagTransitionError(IntelligenceError):
    """Transição de estado de tag inválida."""
    pass


class TagService:

    # Transições permitidas. A tag nasce em 'new'; pode ser confirmada
    # ou descartada; uma decisão pode ser revertida (revisão humana),
    # mas só com histórico explícito.
    ALLOWED = {
        (InsightTagHistory.STATE_NEW, InsightTagHistory.STATE_CONFIRMED),
        (InsightTagHistory.STATE_NEW, InsightTagHistory.STATE_DISCARDED),
        (InsightTagHistory.STATE_CONFIRMED, InsightTagHistory.STATE_DISCARDED),
        (InsightTagHistory.STATE_DISCARDED, InsightTagHistory.STATE_CONFIRMED),
    }

    @staticmethod
    @transaction.atomic
    def transition(
        *,
        insight: InsightItem,
        new_state: str,
        changed_by=None,
        reason: str = '',
    ) -> InsightItem:
        """
        Aplica uma transição de estado com histórico.

        Rejeita:
            - insights que não sejam kind='tag';
            - new_state fora de STATE_CHOICES;
            - transição não permitida (ex: confirmed → new);
            - no-op (mesmo estado).
        """
        if insight.kind != InsightItem.KIND_TAG:
            raise InvalidTagTransitionError(
                'Apenas itens de kind="tag" possuem histórico de estado.'
            )

        valid_states = {c[0] for c in InsightTagHistory.STATE_CHOICES}
        if new_state not in valid_states:
            raise InvalidTagTransitionError(
                f'Estado inválido: {new_state}.'
            )

        previous = insight.review_state
        if previous == new_state:
            raise InvalidTagTransitionError(
                f'A tag já está no estado "{new_state}".'
            )

        if (previous, new_state) not in TagService.ALLOWED:
            raise InvalidTagTransitionError(
                f'Transição não permitida: {previous} → {new_state}.'
            )

        InsightTagHistory.objects.create(
            insight=insight,
            previous_state=previous,
            new_state=new_state,
            changed_by=(
                changed_by
                if (changed_by and getattr(changed_by, 'is_authenticated', False))
                else None
            ),
            reason=reason or '',
        )

        insight.review_state = new_state
        insight.save(update_fields=['review_state', 'updated_at'])

        logger.info(
            'Tag transicionada: insight=%s %s→%s by=%s',
            insight.id, previous, new_state,
            getattr(changed_by, 'email', None) or 'system',
        )
        return insight

    # ------------------------------------------------------------------
    # CONSULTAS
    # ------------------------------------------------------------------

    @staticmethod
    def history_for(insight: InsightItem):
        """Histórico completo da tag, mais recente primeiro."""
        if insight.kind != InsightItem.KIND_TAG:
            return InsightTagHistory.objects.none()
        return (
            InsightTagHistory.objects
            .filter(insight=insight)
            .select_related('changed_by')
            .order_by('-created_at')
        )

    @staticmethod
    def list_tags(
        *,
        workspace,
        client=None,
        state: Optional[str] = None,
    ):
        """
        Lista tags do workspace (opcionalmente filtradas por cliente
        e/ou estado atual).
        """
        qs = (
            InsightItem.objects
            .filter(workspace=workspace, kind=InsightItem.KIND_TAG)
            .select_related('client', 'briefing')
            .order_by('-created_at')
        )
        if client is not None:
            qs = qs.filter(client=client)
        if state is not None:
            qs = qs.filter(review_state=state)
        return qs