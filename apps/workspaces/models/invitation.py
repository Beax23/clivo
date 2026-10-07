"""
Modelo WorkspaceInvitation.

Convite pendente para um email entrar em um Workspace com uma
Governança específica.

REGRA:
    O convite NÃO cria membership imediata. Ele fica `pending` até
    que alguém se cadastre (Google ou email/senha) com o email
    convidado. Quando isso acontece, o signal `user_logged_in` cria
    a membership e marca o convite como `accepted`.

    Se ninguém se cadastrar, o convite expira (default: 7 dias).
"""

import uuid
import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.workspaces.models.workspace import Workspace


def _generate_token():
    """Token URL-safe de 48 caracteres."""
    return secrets.token_urlsafe(36)


class WorkspaceInvitation(models.Model):

    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_ACCEPTED, 'Aceito'),
        (STATUS_EXPIRED, 'Expirado'),
        (STATUS_CANCELLED, 'Cancelado'),
    ]

    DEFAULT_TTL_DAYS = 7
    MAX_RESENDS = 5

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='invitations',
    )

    email = models.EmailField(
        db_index=True,
        help_text=_('Email do convidado'),
    )

    governance = models.ForeignKey(
        'console.ConsoleGovernance',
        on_delete=models.PROTECT,
        related_name='workspace_invitations',
        help_text=_('Governança a ser atribuída quando o convite for aceito'),
    )

    token = models.CharField(
        max_length=64,
        unique=True,
        default=_generate_token,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_workspace_invitations',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Data em que o convite deixa de ser válido'),
    )

    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Quando o convidado se cadastrou e a membership foi criada'),
    )

    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Último envio de email'),
    )

    send_count = models.PositiveIntegerField(
        default=0,
        help_text=_('Quantas vezes o email de convite foi enviado'),
    )

    class Meta:
        db_table = 'workspace_invitation'
        verbose_name = _('Convite de Workspace')
        verbose_name_plural = _('Convites de Workspace')
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['token']),
            models.Index(fields=['expires_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'email'],
                condition=models.Q(status='pending'),
                name='unique_pending_invitation_per_workspace_email',
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} → {self.workspace.name} ({self.status})"

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at

    def can_resend(self) -> bool:
        return (
            self.status == self.STATUS_PENDING
            and self.send_count < self.MAX_RESENDS
        )

    def mark_expired_if_needed(self) -> bool:
        """Se passou do prazo e ainda está pendente, marca como expirado."""
        if self.status == self.STATUS_PENDING and self.is_expired():
            self.status = self.STATUS_EXPIRED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                days=self.DEFAULT_TTL_DAYS
            )
        super().save(*args, **kwargs)