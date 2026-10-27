"""
Contrato público do módulo `clients` para consumidores externos.

REGRA
-----
Consumidores externos (ex.: `intelligence`) NÃO importam models de
`clients` diretamente. Toda leitura passa por funções deste módulo,
que devolvem estruturas serializáveis.

ESCOPO E PERMISSÃO
------------------
Funções que retornam dados de notas recebem `workspace` explicitamente.
Notas de outro workspace são descartadas.
"""

import hashlib
import json
from typing import Optional, Dict, List, Any

from django.core.exceptions import ValidationError

from apps.clients.models import Client


# =========================================================================
# SNAPSHOT DO CLIENTE
# =========================================================================

def get_client_snapshot(client_id) -> Optional[Dict[str, Any]]:
    """
    Devolve um snapshot serializável do cliente. Apenas dados brutos.

    Retorna None para UUID inválido (ValidationError do Django, que
    acontece na construção da query), para ID que não existe, ou
    para qualquer valor que não converta em UUID.
    """
    try:
        client = Client.objects.filter(id=client_id).first()
    except (ValueError, TypeError, ValidationError):
        return None
    if client is None:
        return None

    return {
        'id': str(client.id),
        'workspace_id': str(client.workspace_id),
        'name': client.name,
        'email': client.email or '',
        'phone': client.phone or '',
        'status': client.status,
        'context': client.context or {},
        'updated_at': client.updated_at.isoformat(),
    }


def get_client_event_occurrence_id(client) -> str:
    """
    Gera uma occurrence_id estável a partir do updated_at do cliente.
    Usado pelo IngestService para distinguir atualizações legítimas.

    Mantido por compatibilidade. Para o contexto especificamente,
    `get_client_context_hash` é semanticamente mais preciso (só muda
    quando o CONTEÚDO muda, não a cada save).
    """
    return client.updated_at.isoformat()


# =========================================================================
# NOTAS
# =========================================================================

def get_client_notes_snapshot(
    client_id,
    workspace,
) -> List[Dict[str, Any]]:
    """
    Lista notas do cliente no workspace, em formato serializável.

    Retorna lista de:
        {
            'id': str,
            'author_email': str | None,
            'content': str,
            'is_pinned': bool,
            'created_at': str (ISO),
            'updated_at': str (ISO),
        }

    Regras:
        - Se o cliente não pertence ao workspace, retorna [].
        - Nunca levanta para cliente inexistente ou UUID inválido.
        - Não inclui notas de outros workspaces.
    """
    if workspace is None or not client_id:
        return []

    try:
        client_ok = Client.objects.filter(
            id=client_id, workspace=workspace,
        ).exists()
    except (ValueError, TypeError, ValidationError):
        return []
    if not client_ok:
        return []

    from apps.clients.models import ClientNote

    try:
        notes = (
            ClientNote.objects
            .filter(client_id=client_id)
            .select_related('author')
            .order_by('created_at')
        )
    except (ValueError, TypeError, ValidationError):
        return []

    return [
        {
            'id': str(n.id),
            'author_email': n.author.email if n.author else None,
            'content': n.content,
            'is_pinned': bool(n.is_pinned),
            'created_at': n.created_at.isoformat(),
            'updated_at': n.updated_at.isoformat(),
        }
        for n in notes
    ]


# =========================================================================
# HASH DE CONTEXTO
# =========================================================================

def get_client_context_hash(client_id) -> str:
    """
    Gera um hash SHA-256 estável do `Client.context`.

    Retorna '' se o cliente não existe, se o UUID é inválido, ou se
    `context` é vazio. Nesse caso o chamador usa o `updated_at` como
    fallback.

    Usado como parte do `occurrence_id` para `portal.context_edited`:
    só muda quando o CONTEÚDO do contexto muda, não em qualquer save.
    """
    try:
        client = Client.objects.filter(id=client_id).only('context').first()
    except (ValueError, TypeError, ValidationError):
        return ''
    if client is None:
        return ''

    context = client.context or {}
    if not context:
        return ''

    try:
        serialized = json.dumps(
            context, sort_keys=True, default=str,
        ).encode('utf-8')
    except (TypeError, ValueError):
        return ''

    return hashlib.sha256(serialized).hexdigest()