"""
Testes do EncryptionService.
"""

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.integrations.encryption.service import EncryptionService
from apps.integrations.exceptions import (
    EncryptionDecryptError,
    EncryptionKeyMissingError,
)


def _gen_key() -> str:
    return Fernet.generate_key().decode('utf-8')


@pytest.mark.encryption
class TestEncryptionService:

    def test_roundtrip(self):
        key = _gen_key()
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key):
            plaintext = b'{"access_token": "abc", "refresh_token": "xyz"}'
            ciphertext = EncryptionService.encrypt(plaintext)
            decrypted = EncryptionService.decrypt(ciphertext)
            assert decrypted == plaintext

    def test_ciphertext_is_not_plaintext(self):
        key = _gen_key()
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key):
            plaintext = b'secret'
            ciphertext = EncryptionService.encrypt(plaintext)
            assert plaintext not in ciphertext

    def test_decrypt_with_wrong_key_fails(self):
        key1 = _gen_key()
        key2 = _gen_key()
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key1):
            ciphertext = EncryptionService.encrypt(b'secret')
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=key2):
            with pytest.raises(EncryptionDecryptError):
                EncryptionService.decrypt(ciphertext)

    def test_key_missing_raises(self):
        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=None):
            with pytest.raises(EncryptionKeyMissingError):
                EncryptionService.encrypt(b'secret')

    def test_rotation_old_key_decrypts(self):
        old_key = _gen_key()
        new_key = _gen_key()

        with override_settings(INTEGRATIONS_ENCRYPTION_KEY=old_key):
            old_ciphertext = EncryptionService.encrypt(b'legacy')

        with override_settings(
            INTEGRATIONS_ENCRYPTION_KEY=new_key,
            INTEGRATIONS_ENCRYPTION_KEY_OLD_1=old_key,
        ):
            assert EncryptionService.decrypt(old_ciphertext) == b'legacy'