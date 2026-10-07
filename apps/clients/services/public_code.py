"""
Gerador do public_code do Client.

Formato: CLI-XXXXXX (6 chars do alfabeto sem ambíguos).
Humano-friendly: legível em voz alta, sem 0/O, 1/l/I.
"""

import re
import secrets

from apps.clients.models import Client


_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_PREFIX = 'CLI-'
_CODE_LENGTH = 6
_MAX_ATTEMPTS = 20


def _generate_raw_code() -> str:
    chars = ''.join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    return f'{_PREFIX}{chars}'


def generate_unique_public_code() -> str:
    for _ in range(_MAX_ATTEMPTS):
        code = _generate_raw_code()
        if not Client.objects.filter(public_code=code).exists():
            return code
    raise RuntimeError(
        'Não foi possível gerar um public_code único após '
        f'{_MAX_ATTEMPTS} tentativas.'
    )


def normalize_public_code(raw: str) -> str:
    if not raw:
        return ''
    raw = raw.strip().upper()
    if not raw.startswith(_PREFIX):
        raw = _PREFIX + re.sub(r'[^A-Z0-9]', '', raw)[:_CODE_LENGTH]
    return raw