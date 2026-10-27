"""
Views HTML do módulo intelligence.

Placeholder — nenhuma página exposta ainda.

A Inteligência é consumida pelos containers fixos definidos em
`InsightItem.CONTAINER_KINDS` (mesa / cliente / relatorio). As views
que servem esses containers serão escritas quando houver decisão
explícita sobre:

    1. Autenticação (session de Workspace? capability?).
    2. Se o resultado é HTML renderizado ou JSON via DRF.
    3. Se há revisão humana (`review_state`) exposta por endpoint.
    4. Paginação e ordenação dos insights por container.

Não adicione views antes dessas decisões.
"""

from django.shortcuts import render  # noqa: F401