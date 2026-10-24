"""
OAuthStateService — armazenamento e consumo do `state` OAuth.

O `state` do OAuth é uma string anti-CSRF. Deve ser:
    1. Imprevisível (nonce criptograficamente seguro).
    2. Vinculado ao usuário e ao workspace que iniciaram a conexão.
    3. Consumido UMA ÚNICA VEZ (DELETE atômico).
    4. Com expiração curta (TTL 5 minutos).

O `state` em si é o nonce. O contexto vive no Redis, indexado por ele.

Armazenamento:
    Redis, chave: integrations:oauth_state:<nonce>
    Valor: JSON com o contexto.
    TTL: 300 segundos.

SOBRE `next_path`
-----------------
`next_path` é o caminho INTERNO para onde o callback deve redirecionar
o usuário depois de conectar com sucesso.

    final_redirect  → onde redirecionar quando o callback FALHA
                      (erro do Google, state inválido, escopo recusado).
                      Tipicamente é a página onde o usuário começou.

    next_path       → onde redirecionar quando o callback TIVER SUCESSO.
                      Mesmo lugar, mas o frontend recebe um sinal
                      (`?google_connected=1`) para reabrir o que estava
                      fazendo.

Ambos passam por `safe_redirect_or_fallback` no callback.
"""

import json
import logging
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger('integrations')


# Prefixo das chaves no cache. Nunca colidir com outras chaves do Redis.
CACHE_KEY_PREFIX = 'integrations:oauth_state:'

# TTL do state. Após isso, o state expira.
STATE_TTL_SECONDS = 300


@dataclass(frozen=True)
class OAuthStateContext:
    """
    Contexto associado a um state OAuth em andamento.
    """
    nonce: str
    user_id: str
    workspace_id: str
    provider_key: str
    resources: list
    redirect_uri: str
    final_redirect: str
    next_path: str
    created_at: str  # ISO 8601


class OAuthStateService:
    """
    Gerencia o ciclo de vida do `state` OAuth.
    """

    @staticmethod
    def issue(
        *,
        user_id: str,
        workspace_id: str,
        provider_key: str,
        resources: list,
        redirect_uri: str,
        final_redirect: str,
        next_path: str = '',
    ) -> str:
        """
        Cria um novo state, persiste o contexto no Redis, e devolve
        o nonce que deve ser enviado ao Google.

        Retorna: o nonce (string imprevisível).
        """
        nonce = secrets.token_urlsafe(32)

        context = OAuthStateContext(
            nonce=nonce,
            user_id=str(user_id),
            workspace_id=str(workspace_id),
            provider_key=provider_key,
            resources=list(resources),
            redirect_uri=redirect_uri,
            final_redirect=final_redirect,
            next_path=next_path or '',
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        cache.set(
            f'{CACHE_KEY_PREFIX}{nonce}',
            json.dumps(asdict(context)),
            timeout=STATE_TTL_SECONDS,
        )

        logger.debug(
            'OAuth state emitido | user=%s workspace=%s provider=%s '
            'next=%s',
            user_id, workspace_id, provider_key, next_path or '—',
        )

        return nonce

    @staticmethod
    def consume(nonce: str) -> Optional[OAuthStateContext]:
        """
        Consome (lê e apaga) um state.

        Retorna o contexto, ou None se:
            - o nonce é vazio,
            - o state não existe (expirado ou nunca existiu).

        Após esta chamada, o nonce é inválido para sempre.
        """
        if not nonce:
            return None

        key = f'{CACHE_KEY_PREFIX}{nonce}'
        raw = cache.get(key)

        if raw is None:
            logger.warning(
                'OAuth state não encontrado (expirado ou forjado): %s',
                nonce[:8] if nonce else '',
            )
            return None

        # Apaga ANTES de decodificar, para garantir consumo único
        # mesmo se o decode falhar.
        cache.delete(key)

        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                'OAuth state malformado no Redis: %s', nonce[:8],
            )
            return None

        # Compatibilidade retroativa: states antigos não têm `next_path`.
        data.setdefault('next_path', '')

        try:
            return OAuthStateContext(**data)
        except TypeError as exc:
            logger.warning(
                'OAuth state com schema inválido: %s', exc,
            )
            return None