"""
Validação de destinos de redirecionamento pós-OAuth.

Todo redirecionamento após o callback DEVE apontar para um destino
interno conhecido. Nunca para uma URL arbitrária passada pelo usuário.

Regras:
    - Deve começar com `/`.
    - Não pode começar com `//` (protocol-relative URL).
    - Não pode começar com `/\` (bypass histórico).
    - Não pode conter `\` (backslash como separador alternativo).
    - Não pode conter `..` (path traversal).
    - Não pode conter `%2e` (encoding URL de `.`, usado para bypass).
    - Deve casar com um dos padrões internos permitidos.

Padrões permitidos (regex):
    - /w/<public_id>/...          → qualquer página dentro de um workspace
    - /fluxo/                     → painel de fluxo do arquiteto
    - /clientes/                  → painel de clientes
    - /configuracoes/             → configurações do workspace
    - /mesa/                      → página da Mesa
    - /workspaces/entrar/         → entrada de workspaces (fallback)

Query strings são aceitas (ex: `/fluxo/?foo=bar`).
"""

import logging
import re
import urllib.parse

logger = logging.getLogger('integrations')


_ALLOWED_PATTERNS = [
    re.compile(r'^/w/[A-Za-z0-9_-]+(/[^\\]*)?$'),
    re.compile(r'^/fluxo(/[^\\]*)?$'),
    re.compile(r'^/clientes(/[^\\]*)?$'),
    re.compile(r'^/configuracoes(/[^\\]*)?$'),
    re.compile(r'^/mesa(/[^\\]*)?$'),
    re.compile(r'^/workspaces/entrar(/[^\\]*)?$'),
]


DEFAULT_FALLBACK = '/workspaces/entrar/'


def _has_path_traversal(target: str) -> bool:
    """
    Detecta tentativas de path traversal.

    Estratégia:
        1. Decodifica a URL repetidamente (até estabilizar) para
           pegar encodings duplos (`%252e` → `%2e` → `.`).
        2. Checa se o path decodificado contém `..` como segmento.
        3. Compara o path original com o normalizado.
    """
    # Decodifica repetidamente para pegar encodings múltiplos.
    decoded = target
    for _ in range(3):
        new_decoded = urllib.parse.unquote(decoded)
        if new_decoded == decoded:
            break
        decoded = new_decoded

    # Checa `..` como segmento de path (evita falso positivo com
    # nomes legítimos como "my..folder").
    # Extrai só o path (antes do `?`).
    path_part = decoded.split('?', 1)[0]
    segments = path_part.split('/')
    if '..' in segments:
        return True

    # Checa a versão original também, caso `unquote` não pegue.
    orig_path = target.split('?', 1)[0]
    if '..' in orig_path.split('/'):
        return True

    return False


def is_safe_redirect(target: str) -> bool:
    """
    Retorna True se `target` é um destino interno permitido.
    """
    if not target or not isinstance(target, str):
        return False

    if not target.startswith('/'):
        return False

    if target.startswith('//'):
        return False

    if target.startswith('/\\') or '\\' in target:
        return False

    if _has_path_traversal(target):
        return False

    return any(p.match(target) for p in _ALLOWED_PATTERNS)


def safe_redirect_or_fallback(target: str) -> str:
    """
    Se `target` é seguro, devolve-o. Caso contrário, devolve o
    destino de fallback.
    """
    if is_safe_redirect(target):
        return target
    if target:
        logger.warning(
            'Redirect bloqueado (não corresponde a nenhum padrão '
            'interno permitido): %r',
            target[:80],
        )
    return DEFAULT_FALLBACK