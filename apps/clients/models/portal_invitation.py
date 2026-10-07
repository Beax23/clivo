"""
Modelo ClientPortalInvitation.

Registro do envio de acesso do Portal por email.

Guarda evidência de que um email foi enviado, para quem, quando
e por qual usuário. O token cru NUNCA é armazenado.

Ciclo:
    1. Cria `pending`.
    2. Tenta envio.
    3. Sucesso  → `sent`.
       Falha    → `failed` (e a sessão associada é revogada).
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


class ClientPortalInvitation(models.Model):

    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_SENT, 'Enviado'),
        (STATUS_FAILED, 'Falhou'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='portal_invitations',
    )

    session = models.ForeignKey(
        'clients.ClientPortalSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitations',
    )

    email = models.EmailField(
        help_text=_('Email para o qual o acesso foi enviado'),
    )

    sent_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_client_portal_invitations',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    error_message = models.TextField(blank=True)

    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'client_portal_invitation'
        verbose_name = _('Convite de Portal')
        verbose_name_plural = _('Convites de Portal')
        indexes = [
            models.Index(fields=['client', '-sent_at']),
            models.Index(fields=['status']),
        ]
        ordering = ['-sent_at']

    def __str__(self):
        return f"Convite {self.client.name} → {self.email} ({self.status})"