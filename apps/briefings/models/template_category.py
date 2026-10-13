"""
Categoria estruturada de template de briefing.

Alternativa ao campo livre `BriefingTemplate.category`.
Quando a FK `category_fk` está preenchida, ela tem precedência
sobre o campo texto `category`.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class BriefingTemplateCategory(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='briefing_template_categories',
    )

    name = models.CharField(max_length=60)

    position = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'briefing_template_category'
        verbose_name = _('Categoria de Modelo de Briefing')
        verbose_name_plural = _('Categorias de Modelo de Briefing')
        ordering = ['position', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='briefing_template_category_unique_name_per_workspace',
            ),
        ]

    def __str__(self):
        return self.name