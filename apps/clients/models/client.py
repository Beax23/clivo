"""
Modelo Client.

Client é o contexto vivo do relacionamento entre o Workspace e um cliente.

NÃO é um cadastro. NÃO é CRM. NÃO é dono de briefings/intelligence.
É a âncora de identidade, Portal, notas, tarefas e timeline.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class Client(models.Model):

    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_SUSPENDED = 'suspended'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Ativo'),
        (STATUS_INACTIVE, 'Inativo'),
        (STATUS_SUSPENDED, 'Suspenso'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='clients',
        help_text=_('Workspace ao qual o cliente pertence'),
    )

    public_code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        help_text=_('Código público (ex: CLI-X7K92P). Imutável. NÃO é senha.'),
    )

    name = models.CharField(
        max_length=200,
        help_text=_('Nome principal (ex: "João & Maria")'),
    )

    email = models.EmailField(
        blank=True,
        help_text=_('Email principal de contato'),
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    context = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            'Contexto publicado/projeção. NÃO é fonte de verdade — '
            'é o que o arquiteto decidiu publicar sobre o cliente.'
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text=_('Estado comercial/relacional do cliente.'),
    )

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_clients',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client'
        verbose_name = _('Cliente')
        verbose_name_plural = _('Clientes')
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'email'],
                condition=models.Q(email__gt=''),
                name='unique_client_email_per_workspace',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['public_code']),
            models.Index(fields=['name']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.public_code})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.name or not self.name.strip():
            raise ValidationError({'name': _('O nome é obrigatório')})

        if not self.public_code:
            raise ValidationError({'public_code': _('O public_code é obrigatório')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)