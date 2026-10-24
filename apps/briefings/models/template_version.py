"""
Modelo BriefingTemplateVersion — versão concreta de um modelo.

REGRA ARQUITETURAL
------------------
Separação clara de três conceitos:

    BriefingTemplate          → modelo lógico (nome, categoria, capa)
    BriefingTemplateVersion   → versão concreta com estrutura editável
    Briefing                  → execução para um cliente

Uma versão pode ser:

    draft      → rascunho editável
    published  → versão imutável, usável em novas execuções
    archived   → versão descontinuada, mas preservada

`structure` é um JSONField que espelha o snapshot no momento da
publicação. Enquanto `status='draft'`, a estrutura "oficial" vive nas
tabelas `BriefingSection`/`BriefingQuestion` ligadas ao template
lógico. Ao publicar, `structure` é populado com o resultado.

Quando o modelo lógico (`BriefingTemplate`) é excluído, a versão
sobrevive com `template=NULL`. Isso é intencional: a versão é
histórica, não pode ser destruída pela exclusão do template.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingTemplateVersion(models.Model):

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Rascunho'),
        (STATUS_PUBLISHED, 'Publicado'),
        (STATUS_ARCHIVED, 'Arquivado'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    template = models.ForeignKey(
        'briefings.BriefingTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions',
        help_text=_(
            'Modelo lógico. NULL significa que o modelo foi excluído '
            'e esta versão sobreviveu como referência histórica.'
        ),
    )

    version_number = models.PositiveIntegerField(
        default=1,
        help_text=_('Número sequencial da versão dentro do template'),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    structure = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            'Estrutura congelada no momento da publicação. '
            'Vazio enquanto a versão está em rascunho.'
        ),
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Momento em que a versão foi publicada'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_template_versions',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_template_version'
        verbose_name = _('Versão de Modelo de Briefing')
        verbose_name_plural = _('Versões de Modelo de Briefing')
        ordering = ['template', '-version_number']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'version_number'],
                name='briefing_template_version_unique_number',
            ),
        ]
        indexes = [
            models.Index(fields=['template', 'status']),
        ]

    def __str__(self):
        tpl = self.template.name if self.template else '<sem modelo>'
        return f"{tpl} · v{self.version_number} ({self.status})"

    def is_editable(self) -> bool:
        return self.status == self.STATUS_DRAFT