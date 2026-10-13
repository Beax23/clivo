"""
ReferenceCategoryService — ciclo de vida de ReferenceCategory.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils.text import slugify

from apps.references.models import Reference, ReferenceCategory
from apps.references.exceptions import (
    ReferenceCategoryNotFoundError,
    ReferenceCategoryNameConflictError,
    ReferenceCategoryError,
)

logger = logging.getLogger('references')


class ReferenceCategoryService:

    @staticmethod
    def list_for_workspace(workspace):
        ReferenceCategory.ensure_defaults(workspace)
        return (
            ReferenceCategory.objects
            .filter(workspace=workspace)
            .annotate(
                reference_count_annotated=Count('references', distinct=True),
            )
            .order_by('position', 'name')
        )

    @staticmethod
    def get_or_raise(category_id, workspace) -> ReferenceCategory:
        cat = (
            ReferenceCategory.objects
            .filter(id=category_id, workspace=workspace)
            .first()
        )
        if cat is None:
            raise ReferenceCategoryNotFoundError('Categoria não encontrada.')
        return cat

    @staticmethod
    @transaction.atomic
    def create(*, workspace, name: str, color: str = '', actor=None) -> ReferenceCategory:
        name = (name or '').strip()
        if not name:
            raise ReferenceCategoryError('O nome da categoria não pode ser vazio.')
        if len(name) > 60:
            raise ReferenceCategoryError(
                'O nome da categoria pode ter no máximo 60 caracteres.'
            )

        base_slug = slugify(name) or 'categoria'
        slug = base_slug
        counter = 1
        while ReferenceCategory.objects.filter(
            workspace=workspace, slug=slug
        ).exists():
            counter += 1
            slug = f'{base_slug}-{counter}'

        max_pos = (
            ReferenceCategory.objects
            .filter(workspace=workspace)
            .order_by('-position')
            .values_list('position', flat=True)
            .first()
        ) or 0

        try:
            cat = ReferenceCategory.objects.create(
                workspace=workspace,
                name=name,
                slug=slug,
                color=(color or '').strip()[:20],
                is_system=False,
                position=max_pos + 1,
                created_by=actor,
            )
        except IntegrityError as exc:
            raise ReferenceCategoryNameConflictError(
                f'Já existe uma categoria chamada "{name}" neste workspace.'
            ) from exc

        return cat

    @staticmethod
    @transaction.atomic
    def rename(*, category, new_name: str = None, color: str = None, actor=None):
        if new_name is not None:
            new_name = new_name.strip()
            if not new_name:
                raise ReferenceCategoryError(
                    'O nome da categoria não pode ser vazio.'
                )
            if len(new_name) > 60:
                raise ReferenceCategoryError(
                    'O nome da categoria pode ter no máximo 60 caracteres.'
                )
            conflict = (
                ReferenceCategory.objects
                .filter(workspace=category.workspace, name__iexact=new_name)
                .exclude(pk=category.pk)
                .exists()
            )
            if conflict:
                raise ReferenceCategoryNameConflictError(
                    f'Já existe uma categoria chamada "{new_name}".'
                )
            category.name = new_name

        if color is not None:
            category.color = (color or '').strip()[:20]

        category.save(update_fields=['name', 'color', 'updated_at'])
        return category

    @staticmethod
    @transaction.atomic
    def delete(category):
        if category.is_system:
            raise ReferenceCategoryError(
                'Categorias do sistema não podem ser excluídas.'
            )
        category_id = category.pk
        category.delete()
        return {'deleted': True, 'id': str(category_id)}

    @staticmethod
    def ensure_defaults(workspace, actor=None):
        ReferenceCategory.ensure_defaults(workspace, actor=actor)