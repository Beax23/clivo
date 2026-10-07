"""
Modelo Feature.

Feature é um pacote comercial que o plano pode oferecer.

Uma Feature responde:
    "O que o produto oferece comercialmente?"

Exemplos:
    - Briefings
    - Intelligence
    - Documents
    - Client Portal

REGRA ARQUITETURAL:
    Feature NÃO é permissão.
    Feature NÃO é autorização de usuário.
    Feature NÃO agrupa capabilities.
    Feature é apenas um item comercial.

    Limites de uso NÃO vivem na Feature.
    Vivem em PlanFeatureLimit.

    Feature é criada 100% pelo operador via Console UI.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class Feature(models.Model):
    """Item comercial do Clivo."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da feature')
    )

    key = models.SlugField(
        max_length=50,
        unique=True,
        help_text=_(
            'Chave técnica estável (gerada do nome). '
            'Não é exibida ao operador.'
        )
    )

    name = models.CharField(
        max_length=100,
        help_text=_('Nome exibido (ex: "Intelligence")')
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição comercial da feature')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se a feature pode ser associada a planos')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'console_feature'
        verbose_name = _('Feature')
        verbose_name_plural = _('Features')
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name

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