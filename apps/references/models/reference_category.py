"""
Modelo ReferenceCategory.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


DEFAULT_CATEGORIES = [
    ('Ambiente',     'ambiente',     '#3B82F6'),
    ('Material',     'material',     '#8B5CF6'),
    ('Iluminação',   'iluminacao',   '#F59E0B'),
    ('Mobiliário',   'mobiliario',   '#10B981'),
    ('Marcenaria',   'marcenaria',   '#A16207'),
    ('Revestimento', 'revestimento', '#EC4899'),
    ('Paisagismo',   'paisagismo',   '#22C55E'),
    ('Fachada',      'fachada',      '#0EA5E9'),
    ('Cores',        'cores',        '#EF4444'),
    ('Layout',       'layout',       '#6366F1'),
    ('Outro',        'outro',        '#64748B'),
]


class ReferenceCategory(models.Model):

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False,
    )

    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='reference_categories',
        help_text=_('Workspace ao qual a categoria pertence'),
    )

    name = models.CharField(
        max_length=60,
        help_text=_('Nome visível da categoria (ex: "Cozinhas")'),
    )

    slug = models.SlugField(
        max_length=80,
        help_text=_(
            'Identificador estável. Gerado a partir do nome.'
        ),
    )

    color = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text=_(
            'Cor da categoria em hex (#RRGGBB). Usada nos chips/balões.'
        ),
    )

    is_system = models.BooleanField(
        default=False,
        help_text=_(
            'Categorias de sistema não podem ser excluídas, '
            'apenas renomeadas.'
        ),
    )

    position = models.PositiveIntegerField(
        default=0,
        help_text=_('Ordem de exibição'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_reference_categories',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reference_category'
        verbose_name = _('Categoria de Referência')
        verbose_name_plural = _('Categorias de Referência')
        ordering = ['position', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'slug'],
                name='reference_category_unique_slug_per_workspace',
            ),
        ]
        indexes = [
            models.Index(fields=['workspace', 'position']),
            models.Index(fields=['workspace', 'name']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'categoria'
            self.slug = base
        super().save(*args, **kwargs)

    @classmethod
    def ensure_defaults(cls, workspace, actor=None):
        existing_slugs = set(
            cls.objects.filter(workspace=workspace).values_list('slug', flat=True)
        )
        to_create = []
        for i, (name, slug, color) in enumerate(DEFAULT_CATEGORIES):
            if slug in existing_slugs:
                continue
            to_create.append(cls(
                workspace=workspace,
                name=name,
                slug=slug,
                color=color,
                is_system=True,
                position=i,
                created_by=actor,
            ))
        if to_create:
            cls.objects.bulk_create(to_create, ignore_conflicts=True)