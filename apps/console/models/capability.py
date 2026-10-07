"""
Modelo ConsoleCapability.

Catálogo de capabilities declaradas pelos apps.

REGRA ARQUITETURAL:
    Nenhuma capability nasce no Console.
    Toda capability nasce no domínio que a executa.

    O Console apenas cataloga, ativa/inativa e associa a governanças.

Ciclo de vida:
    - App declara em `apps/<app>/capabilities.py`
    - `sync_capabilities` cria/atualiza aqui com `is_active=True`
    - Se o app deixa de declarar, vira `is_active=False` (nunca é deletada)
    - Isso protege o histórico de `ConsoleGovernanceCapability`
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class ConsoleCapability(models.Model):
    """Capacidade da plataforma Clivo."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da capability')
    )

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text=_(
            'Código único da capability no formato '
            '"<app>.<recurso>.<ação>" (ex: "clients.client.view")'
        )
    )

    name = models.CharField(
        max_length=150,
        help_text=_('Nome exibido da capability')
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição da capability')
    )

    source_app = models.CharField(
        max_length=50,
        help_text=_(
            'Label do AppConfig que declarou esta capability. '
            'Derivado automaticamente pelo Console — nunca declarado pelo app.'
        )
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_(
            'Se a capability está atualmente declarada por algum app. '
            'Capabilities não declaradas viram inativas, mas nunca são deletadas.'
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    class Meta:
        db_table = 'console_capability'
        verbose_name = _('Capacidade do Console')
        verbose_name_plural = _('Capacidades do Console')
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['source_app']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['source_app', 'name']

    def __str__(self):
        suffix = '' if self.is_active else ' (inativa)'
        return f"{self.code} — {self.name}{suffix}"

    def clean(self):
        """
        Validações de domínio — aplicadas apenas quando `code` ou
        `source_app` estão sendo definidos/alterados.

        Updates parciais (ex: `save(update_fields=['is_active'])`) NÃO
        revalidam o formato, permitindo desativar capabilities legadas
        sem quebrar.
        """
        from django.core.exceptions import ValidationError

        # Se não é criação, verifica se `code`/`source_app` mudaram.
        if not self._state.adding:
            try:
                old = ConsoleCapability.objects.only(
                    'code', 'source_app'
                ).get(pk=self.pk)
                if old.code == self.code and old.source_app == self.source_app:
                    return
            except ConsoleCapability.DoesNotExist:
                pass

        if not self.code:
            raise ValidationError({
                'code': _('O código é obrigatório.')
            })

        parts = self.code.split('.')
        if len(parts) < 3:
            raise ValidationError({
                'code': _(
                    'O código deve estar no formato '
                    '"<app>.<recurso>.<ação>" (ex: "clients.client.view")'
                )
            })

        if not self.source_app:
            raise ValidationError({
                'source_app': _('O source_app é obrigatório')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)