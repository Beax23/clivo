"""
Carregador do system prompt da Inteligência.

Fonte: settings.INTELLIGENCE_SYSTEM_PROMPT, com fallback mínimo.
"""

from django.conf import settings


_DEFAULT_PROMPT = (
    "Você é um analista que produz insights estruturados em JSON. "
    "Responda apenas com um objeto JSON contendo a chave 'insights'."
)


def get_prompt() -> str:
    return getattr(settings, 'INTELLIGENCE_SYSTEM_PROMPT', _DEFAULT_PROMPT)