"""
IntegrationResource — recurso oferecido por um IntegrationProvider.

Ex Google: "drive.file.read", "forms.body.read".

O catálogo NÃO armazena escopos OAuth. A tradução
recurso → escopo OAuth vive no adapter.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class IntegrationResource(models.Model):
    """
    Recurso concreto oferecido por um provider.

    Ex Google:
        - drive.file.read
        - drive.file.write
        - forms.body.read
        - forms.body.write
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    provider = models.ForeignKey(
        'integrations.IntegrationProvider',
        on_delete=models.CASCADE,
        related_name='resources',
        help_text=_('Provider ao qual o recurso pertence.'),
    )

    # Slug é o identificador canônico do recurso dentro do provider.
    #
    # Usamos CharField (não SlugField) porque o slug inclui pontos
    # para indicar hierarquia — ex: "drive.file.read".
    # O SlugField padrão do Django NÃO aceita pontos.
    #
    # A validação de formato (minúsculas, sem espaços) é feita no
    # método `clean()` abaixo.
    slug = models.CharField(
        max_length=100,
        help_text=_(
            'Identificador canônico do recurso dentro do provider '
            '(ex: "drive.file.read").'
        ),
    )

    name = models.CharField(
        max_length=150,
        help_text=_('Nome exibido ao usuário (ex: "Ler arquivos do Drive").'),
    )

    description = models.TextField(
        blank=True,
        help_text=_('Descrição do que o recurso permite.'),
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se False, o recurso não pode ser solicitado em novas conexões.'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'integration_resource'
        verbose_name = _('Integration Resource')
        verbose_name_plural = _('Integration Resources')
        ordering = ['provider__name', 'slug']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'slug'],
                name='unique_resource_per_provider',
            ),
        ]
        indexes = [
            models.Index(fields=['provider', 'slug']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.provider.key}:{self.slug}"

    def clean(self):
        """
        Valida o formato do slug.

        Regras:
            - Não pode ser vazio
            - Deve ser minúsculo
            - Não pode conter espaços
        """
        from django.core.exceptions import ValidationError

        if not self.slug:
            raise ValidationError({'slug': _('O slug é obrigatório')})

        if not self.slug.islower() or ' ' in self.slug:
            raise ValidationError({
                'slug': _(
                    'O slug deve ser em minúsculas, sem espaços '
                    '(ex: "drive.file.read").'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)