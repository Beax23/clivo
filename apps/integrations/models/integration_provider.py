"""
IntegrationProvider — catálogo de serviços externos conectáveis.

Um IntegrationProvider descreve UM serviço externo (ex: Google).
Ele NÃO armazena tokens, contas autorizadas ou escopos OAuth.

FRONTEIRA:
    Não confundir com console.Provider (infraestrutura da Clivo).
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class IntegrationProvider(models.Model):
    """
    Catálogo de serviços externos que o escritório pode conectar.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text=_(
            'Identificador canônico do provider (ex: "google").'
        ),
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome exibido (ex: "Google").'),
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição do que o provider oferece.'),
    )

    category = models.SlugField(
        max_length=50,
        blank=True,
        help_text=_(
            'Categoria informativa para a UI '
            '(ex: "productivity", "storage").'
        ),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_(
            'Se False, NÃO aceita novas conexões. '
            'Conexões existentes continuam válidas.'
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'integration_provider'
        verbose_name = _('Integration Provider')
        verbose_name_plural = _('Integration Providers')
        ordering = ['name']
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        suffix = '' if self.is_active else ' (inativo)'
        return f"{self.name} ({self.key}){suffix}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.key:
            raise ValidationError({'key': _('A chave é obrigatória')})

        if not self.key.islower():
            raise ValidationError({
                'key': _('A chave deve ser em minúsculas')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)