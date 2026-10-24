"""
WorkspaceIntegration — conta externa autorizada por um workspace.

Armazena credenciais cifradas e a identidade da conta externa.
Múltiplas contas do mesmo provider são suportadas no mesmo workspace.

SELEÇÃO DE CONTA:
    - Uma conta pode ser marcada como preferida
      (`is_preferred=True`).
    - Regra determinística em WorkspaceIntegrationService.get_for_workspace.
    - Proibido `.first()` arbitrário.

SEGURANÇA:
    - `encrypted_payload` é a única fonte de access_token/refresh_token.
    - Nunca em plaintext, nunca em log, nunca em exceção.
    - Formato do envelope: ver apps/integrations/encryption/service.py.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkspaceIntegration(models.Model):

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_REVOKED = 'revoked'
    STATUS_ERROR = 'error'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, _('Ativa')),
        (STATUS_EXPIRED, _('Expirada')),
        (STATUS_REVOKED, _('Revogada')),
        (STATUS_ERROR, _('Erro')),
    ]

    # ------------------------------------------------------------------
    # IDENTIDADE
    # ------------------------------------------------------------------

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='integrations',
        help_text=_('Workspace ao qual esta integração pertence.'),
    )

    provider = models.ForeignKey(
        'integrations.IntegrationProvider',
        on_delete=models.PROTECT,
        related_name='connections',
        help_text=_(
            'Provider externo. PROTECT: provider com conexões não pode '
            'ser apagado.'
        ),
    )

    external_account_id = models.CharField(
        max_length=255,
        help_text=_(
            'Identificador da conta no provider. '
            'Ex Google: sub do ID token.'
        ),
    )

    external_account_email = models.EmailField(
        help_text=_('Email da conta externa (exibido ao usuário).'),
    )

    external_account_display_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Nome amigável da conta externa.'),
    )

    external_account_avatar_url = models.URLField(
        max_length=500,
        blank=True,
        help_text=_('URL do avatar da conta externa (opcional).'),
    )

    # ------------------------------------------------------------------
    # CREDENCIAIS
    # ------------------------------------------------------------------

    encrypted_payload = models.BinaryField(
        help_text=_(
            'Payload cifrado contendo access_token, refresh_token, '
            'expires_at e scopes. Formato definido por EncryptionService.'
        ),
    )

    granted_scopes = models.JSONField(
        default=list,
        help_text=_(
            'Escopos OAuth efetivamente concedidos pelo usuário. '
            'Não confundir com escopos solicitados.'
        ),
    )

    # ------------------------------------------------------------------
    # ESTADO
    # ------------------------------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )

    last_refresh_at = models.DateTimeField(null=True, blank=True)

    last_error_at = models.DateTimeField(null=True, blank=True)

    last_error_code = models.CharField(
        max_length=50,
        blank=True,
        help_text=_(
            'Código normalizado do último erro (não mensagem livre). '
            'Ex: "decrypt_failed", "revoked_remotely".'
        ),
    )

    # ------------------------------------------------------------------
    # PREFERÊNCIA
    # ------------------------------------------------------------------

    is_preferred = models.BooleanField(
        default=False,
        help_text=_(
            'Se True, é a conta usada por padrão quando o chamador '
            'não passa integration_id explícito.'
        ),
    )

    # ------------------------------------------------------------------
    # RASTREABILIDADE
    # ------------------------------------------------------------------

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_workspace_integrations',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # META
    # ------------------------------------------------------------------

    class Meta:
        db_table = 'integration_workspace_integration'
        verbose_name = _('Workspace Integration')
        verbose_name_plural = _('Workspace Integrations')
        ordering = ['-created_at']
        constraints = [
            # Uma conta externa por workspace por provider.
            models.UniqueConstraint(
                fields=['workspace', 'provider', 'external_account_id'],
                name='unique_external_account_per_workspace_provider',
            ),
            # No máximo UMA conta preferida por (workspace, provider).
            models.UniqueConstraint(
                fields=['workspace', 'provider'],
                condition=models.Q(is_preferred=True, status='active'),
                name='unique_preferred_integration_per_workspace_provider',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'provider', 'status']),
            models.Index(fields=['workspace', 'provider', 'is_preferred']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return (
            f"{self.workspace.name} → {self.provider.name} "
            f"({self.external_account_email})"
        )

    # ------------------------------------------------------------------
    # HELPERS DE ESTADO
    # ------------------------------------------------------------------

    def is_usable(self) -> bool:
        """Se True, a integração pode ser usada em operações."""
        return self.status == self.STATUS_ACTIVE