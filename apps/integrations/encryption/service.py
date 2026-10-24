"""
EncryptionService — cifra de credenciais em repouso.

ALGORITMO: Fernet (cryptography). Simétrico, autenticado, com envelope.
CHAVE: settings.INTEGRATIONS_ENCRYPTION_KEY (str base64-url de 32 bytes).

FORMATO DO PAYLOAD CIFRADO:
    O EncryptionService cifra um blob opaco. O formato do conteúdo
    é responsabilidade do chamador (WorkspaceIntegrationService).
    O blob inclui prefixo de versão de chave para permitir rotação.

SEGURANÇA:
    - Nunca loga o plaintext.
    - Nunca inclui plaintext em exceção.
    - Rotation: se a chave rotaciona, payloads antigos continuam
      decifráveis via chaves anteriores (INTEGRATIONS_ENCRYPTION_KEY_OLD_*).
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from apps.integrations.exceptions import (
    EncryptionDecryptError,
    EncryptionKeyMissingError,
)

logger = logging.getLogger('integrations')


# Chave primária das settings. Formato esperado: string base64-url de 32 bytes.
SETTINGS_KEY_PRIMARY = 'INTEGRATIONS_ENCRYPTION_KEY'


class EncryptionService:
    """
    Serviço de cifra simétrica com envelope e rotação de chaves.
    """

    # =====================================================================
    # CHAVES
    # =====================================================================

    @staticmethod
    def _load_keys() -> dict[str, Fernet]:
        """
        Carrega todas as chaves configuradas.

        Chave primária: INTEGRATIONS_ENCRYPTION_KEY (usada para cifrar).
        Chaves antigas: INTEGRATIONS_ENCRYPTION_KEY_OLD_1, _2, ... (usadas
        para decifrar dados legados durante rotação).

        Retorna dict {key_id: Fernet}. `key_id` é a string do atributo
        settings, sem o prefixo.
        """
        keys: dict[str, Fernet] = {}

        primary_raw = getattr(settings, SETTINGS_KEY_PRIMARY, None)
        if not primary_raw:
            raise EncryptionKeyMissingError(
                f'{SETTINGS_KEY_PRIMARY} não definida nas settings.'
            )

        keys['primary'] = EncryptionService._build_fernet(primary_raw)

        # Chaves antigas (rotação)
        i = 1
        while True:
            name = f'{SETTINGS_KEY_PRIMARY}_OLD_{i}'
            raw = getattr(settings, name, None)
            if not raw:
                break
            keys[f'old_{i}'] = EncryptionService._build_fernet(raw)
            i += 1

        return keys

    @staticmethod
    def _build_fernet(key: str) -> Fernet:
        """
        Constrói uma instância Fernet a partir da chave bruta.
        """
        try:
            return Fernet(key.encode('utf-8'))
        except Exception as exc:
            # A chave em si nunca aparece na mensagem.
            raise EncryptionKeyMissingError(
                'Formato de chave de criptografia inválido.'
            ) from exc

    # =====================================================================
    # CIFRA
    # =====================================================================

    @staticmethod
    def encrypt(plaintext: bytes) -> bytes:
        """
        Cifra um blob. Retorna o token Fernet (bytes).

        O token já é autenticado (Fernet) e contém timestamp.
        """
        keys = EncryptionService._load_keys()
        fernet = keys['primary']
        return fernet.encrypt(plaintext)

    @staticmethod
    def decrypt(ciphertext: bytes) -> bytes:
        """
        Decifra um blob. Tenta a chave primária, depois as antigas.

        Levanta EncryptionDecryptError se nenhuma chave funcionar.
        """
        keys = EncryptionService._load_keys()
        token = bytes(ciphertext)

        # Tenta primária
        try:
            return keys['primary'].decrypt(token)
        except InvalidToken:
            pass
        except Exception as exc:
            logger.warning(
                'Falha inesperada ao decifrar com chave primária: %s',
                type(exc).__name__,
            )

        # Tenta antigas
        for key_id, fernet in keys.items():
            if key_id == 'primary':
                continue
            try:
                return fernet.decrypt(token)
            except InvalidToken:
                continue
            except Exception as exc:
                logger.warning(
                    'Falha inesperada ao decifrar com %s: %s',
                    key_id, type(exc).__name__,
                )

        raise EncryptionDecryptError(
            'Não foi possível decifrar o payload com nenhuma chave configurada.'
        )