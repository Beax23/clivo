"""
Modelo ClientPortalSession.

Sessão temporária de autenticação do Portal.

REGRA:
    public_code identifica o cliente.
    public_code NÃO autentica.
    A autenticação do Portal é feita por um token temporário,
    armazenado HASHED neste modelo.

Fluxo:
    1. Arquiteto envia acesso por email.
    2. ClientPortalInvitationService gera token (raw, não armazenado).
    3. Armazena apenas hash(token) com expiração.
    4. Email contém link com token.
    5. Cliente abre link, backend valida hash + expiração.
    6. Cria ClientPortalSession (cookie) e ClientPortalAccess (log).
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


def _generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class ClientPortalSession(models.Model):

    DEFAULT_TTL_MINUTES = 30

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='portal_sessions',
    )

    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_('SHA-256 do token de sessão. O token cru NUNCA é armazenado.'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'client_portal_session'
        verbose_name = _('Sessão de Portal')
        verbose_name_plural = _('Sessões de Portal')
        indexes = [
            models.Index(fields=['client', '-created_at']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Sessão {self.client.name} — expira {self.expires_at}"

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    @classmethod
    def issue(cls, client: Client, ttl_minutes: int | None = None) -> tuple['ClientPortalSession', str]:
        """
        Cria uma sessão e retorna (instância, token_cru).

        O token_cru só é retornado UMA vez. Nunca é recuperável depois.
        """
        ttl = ttl_minutes or cls.DEFAULT_TTL_MINUTES
        raw = _generate_raw_token()
        session = cls.objects.create(
            client=client,
            token_hash=_hash_token(raw),
            expires_at=timezone.now() + timedelta(minutes=ttl),
        )
        return session, raw

    def is_valid(self) -> bool:
        if self.revoked_at:
            return False
        return timezone.now() < self.expires_at

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=['revoked_at'])

    @classmethod
    def find_by_raw_token(cls, raw: str) -> 'ClientPortalSession | None':
        if not raw:
            return None
        h = _hash_token(raw)
        try:
            return cls.objects.select_related('client').get(token_hash=h)
        except cls.DoesNotExist:
            return None