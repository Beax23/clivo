"""
WorkspacePublicID — mapeia UUID ↔ token público ofuscado.

REGRA:
    O token NÃO é autorização. Ele só esconde o UUID.
    Quem garante acesso é o `WorkspaceMembership` do request.user.

    O salt DEVE vir do settings (nunca hardcoded). Trocar o salt
    invalida todos os tokens antigos.

USO:
    from apps.workspaces.public_id import (
        encode_workspace_id,
        decode_workspace_id,
    )

    token = encode_workspace_id(workspace.id)   # 'k9xPz3aQ'
    uid   = decode_workspace_id(token)           # '3b7a0fb5-...'
"""

from typing import Optional
from uuid import UUID

from django.conf import settings
from hashids import Hashids


# Tamanho mínimo do token.
# 8 caracteres é o sweet spot: curto o suficiente para URL,
# longo o suficiente para não colidir em bases de centenas de milhares.
_MIN_HASH_LENGTH = 8

# Alfabeto sem caracteres ambíguos (0/O, 1/l/I).
_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def _get_hasher() -> Hashids:
    salt = getattr(settings, 'WORKSPACE_PUBLIC_ID_SALT', None)
    if not salt:
        raise RuntimeError(
            'WORKSPACE_PUBLIC_ID_SALT não definido em settings. '
            'Defina uma string aleatória longa em .env.'
        )
    return Hashids(
        salt=salt,
        min_length=_MIN_HASH_LENGTH,
        alphabet=_ALPHABET,
    )


def encode_workspace_id(workspace_id) -> str:
    """
    Converte um UUID (ou string) em token público.

    O UUID é reduzido a um inteiro de 128 bits. O Hashids transforma
    esse inteiro em string usando o salt. Como UUID é determinístico,
    o mesmo workspace sempre gera o mesmo token.
    """
    uid = UUID(str(workspace_id))
    return _get_hasher().encode(uid.int)


def decode_workspace_id(token: str) -> Optional[str]:
    """
    Converte um token público em UUID (string), ou None se inválido.
    """
    if not token:
        return None
    try:
        numbers = _get_hasher().decode(token)
    except Exception:
        return None
    if not numbers:
        return None
    # Hashids devolve tupla de inteiros; usamos o primeiro (é um só).
    value = numbers[0]
    # Reconstroi o UUID de 128 bits
    if value < 0 or value >= (1 << 128):
        return None
    return str(UUID(int=value))