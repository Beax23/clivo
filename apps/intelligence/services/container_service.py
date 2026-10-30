"""
ContainerService — monta a resposta dos containers fixos.

REGRA ARQUITETURAL
------------------
Os containers são estruturas FIXAS (Mesa, Cliente, Relatório). Este
service é a ÚNICA fonte de verdade para montar o payload de cada um.

NORMALIZAÇÃO DE `content`
-------------------------
O `content` de cada `InsightItem` deve seguir o contrato do
`prompt_loader.py`:

    - desire / attention / demais bullets:
        "afirmação — motivo", máx ~140 chars.
    - summary.briefing:
        texto analítico MÁXIMO 500 caracteres (truncado aqui, no
        service), sempre terminando em ponto final.
    - executive.summary:
        texto corrido, preservado na íntegra.

O truncamento do resumo em 500 caracteres acontece AQUI, para que
o CSS nunca precise cortar por linhas. O texto sempre termina em
ponto final (ou "…" se não houver ponto próximo do limite).
"""

import logging
import re
from typing import Dict, List, Optional

from apps.intelligence.models import InsightItem

logger = logging.getLogger('intelligence')


_SUBJECT_PREFIXES = [
    re.compile(r'^o\s+cliente\s+', re.IGNORECASE),
    re.compile(r'^a\s+cliente\s+', re.IGNORECASE),
    re.compile(r'^os\s+clientes\s+', re.IGNORECASE),
    re.compile(r'^as\s+clientes\s+', re.IGNORECASE),
    re.compile(r'^ele\s+', re.IGNORECASE),
    re.compile(r'^ela\s+', re.IGNORECASE),
    re.compile(r'^eles\s+', re.IGNORECASE),
    re.compile(r'^elas\s+', re.IGNORECASE),
    re.compile(r'^o\s+briefing\s+', re.IGNORECASE),
    re.compile(r'^a\s+briefing\s+', re.IGNORECASE),
    re.compile(r'^o\s+projeto\s+', re.IGNORECASE),
    re.compile(r'^a\s+análise\s+', re.IGNORECASE),
]

_TRAILING_NOISE = [
    re.compile(r'\s*\.\s*$'),
    re.compile(r'\s*\.\.\.\s*$'),
    re.compile(r'\s*…\s*$'),
    re.compile(r',?\s*etc\.?\s*$', re.IGNORECASE),
    re.compile(r',?\s*e\s+outros\.?\s*$', re.IGNORECASE),
    re.compile(r',?\s*entre\s+outros\.?\s*$', re.IGNORECASE),
]

# Tamanho máximo de um bullet curto na saída.
_MAX_BULLET_LENGTH = 140

# Tamanho máximo do resumo. Garante que o texto SEMPRE fecha e caiba
# no container sem corte no frontend.
_RESUMO_MAX_CHARS = 400


def _normalize_bullet(raw: str) -> str:
    """
    Normaliza um bullet curto (desire, attention, etc.).

    Idempotente. Aplica remoção de prefixos/sufixos e truncamento
    em ~140 chars.

    NÃO é usado para summary.briefing nem executive.summary.
    """
    if not raw:
        return ''

    text = raw.strip()

    changed = True
    while changed:
        changed = False
        for pat in _SUBJECT_PREFIXES:
            new_text = pat.sub('', text)
            if new_text != text:
                text = new_text.strip()
                changed = True

    changed = True
    while changed:
        changed = False
        for pat in _TRAILING_NOISE:
            new_text = pat.sub('', text)
            if new_text != text:
                text = new_text.strip()
                changed = True

    if text and text[0].isalpha() and text[0].islower():
        text = text[0].upper() + text[1:]

    if len(text) > _MAX_BULLET_LENGTH:
        text = text[: _MAX_BULLET_LENGTH - 1].rstrip() + '…'

    return text


def _truncate_resumo(raw: str) -> str:
    """
    Trunca o resumo em `_RESUMO_MAX_CHARS` caracteres.

    Regras:
        - Se já cabe → devolve como veio (só strip).
        - Se precisa cortar → tenta cortar no último ponto final
          antes do limite (para o texto terminar de forma natural).
        - Se não houver ponto nos últimos 30% do texto → corta no
          limite e adiciona "…".

    Idempotente: rodar duas vezes dá o mesmo resultado.
    """
    if not raw:
        return ''

    text = raw.strip()

    if len(text) <= _RESUMO_MAX_CHARS:
        return text

    head = text[:_RESUMO_MAX_CHARS]

    # Procura o último ponto final nos últimos 30% do head.
    safe_floor = int(_RESUMO_MAX_CHARS * 0.7)
    last_dot = head.rfind('.')

    if last_dot >= safe_floor:
        return head[: last_dot + 1].rstrip()

    return head[: _RESUMO_MAX_CHARS - 1].rstrip() + '…'


def _normalize_content(raw: str, kind: str) -> str:
    """
    Decide a normalização com base no kind.

    - summary.briefing → trunca em 500 chars, termina em ponto.
    - executive.summary → preserva (texto corrido, sem truncar).
    - demais           → normaliza como bullet curto.
    """
    if not raw:
        return ''

    if kind == InsightItem.KIND_SUMMARY_BRIEFING:
        return _truncate_resumo(raw)

    if kind == InsightItem.KIND_EXECUTIVE_SUMMARY:
        return raw.strip()

    return _normalize_bullet(raw)


def _serialize_item(item: InsightItem) -> Dict:
    return {
        'id': str(item.id),
        'kind': item.kind,
        'kind_display': item.get_kind_display(),
        'confidence': item.confidence,
        'confidence_display': item.get_confidence_display(),
        'content': _normalize_content(item.content, item.kind),
        'metadata': item.metadata or {},
        'review_state': item.review_state,
        'is_stale': item.is_stale,
        'created_at': item.created_at.isoformat(),
    }


class ContainerService:

    @staticmethod
    def build_mesa(
        *,
        workspace,
        client=None,
        briefing=None,
        include_stale: bool = False,
    ) -> Dict:
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
        return ContainerService._build(
            container=InsightItem.CONTAINER_CLIENTE,
            workspace=workspace,
            client=client,
            briefing=None,
            include_stale=include_stale,
        )

    @staticmethod
    def build_relatorio(
        *,
        workspace,
        briefing,
        include_stale: bool = False,
    ) -> Dict:
        return ContainerService._build(
            container=InsightItem.CONTAINER_RELATORIO,
            workspace=workspace,
            client=briefing.client,
            briefing=briefing,
            include_stale=include_stale,
        )

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
            containers[slot_name] = [_serialize_item(i) for i in collected]
            counts[slot_name] = len(collected)

        return {'containers': containers, 'counts': counts}