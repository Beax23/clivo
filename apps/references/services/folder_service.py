"""
ReferenceFolderService — ciclo de vida da pasta.
"""

import logging

from django.db import IntegrityError, transaction

from apps.references.models import Reference, ReferenceFolder
from apps.references.exceptions import (
    ReferenceFolderNotFoundError,
    ReferenceFolderNameConflictError,
    ReferenceFolderError,
)

logger = logging.getLogger('references')


class ReferenceFolderService:

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_workspace(workspace):
        from django.db.models import Count, Q

        return (
            ReferenceFolder.objects
            .filter(workspace=workspace)
            .annotate(
                reference_count_annotated=Count(
                    'references',
                    filter=Q(references__workspace=workspace),
                    distinct=True,
                )
            )
            .order_by('name')
        )

    @staticmethod
    def get_or_raise(folder_id, workspace) -> ReferenceFolder:
        folder = (
            ReferenceFolder.objects
            .filter(id=folder_id, workspace=workspace)
            .first()
        )
        if folder is None:
            raise ReferenceFolderNotFoundError('Pasta não encontrada.')
        return folder

    @staticmethod
    def count_unsorted(workspace) -> int:
        return (
            Reference.objects
            .filter(workspace=workspace, folder__isnull=True)
            .count()
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create(*, workspace, name: str, actor=None) -> ReferenceFolder:
        name = (name or '').strip()

        if not name:
            raise ReferenceFolderError('O nome da pasta não pode ser vazio.')

        if len(name) > 100:
            raise ReferenceFolderError(
                'O nome da pasta pode ter no máximo 100 caracteres.'
            )

        exists = ReferenceFolder.objects.filter(
            workspace=workspace, name__iexact=name
        ).exists()

        if exists:
            raise ReferenceFolderNameConflictError(
                f'Já existe uma pasta chamada "{name}" neste workspace.'
            )

        try:
            folder = ReferenceFolder.objects.create(
                workspace=workspace,
                name=name,
                created_by=actor,
            )
        except IntegrityError as exc:
            raise ReferenceFolderNameConflictError(
                f'Já existe uma pasta chamada "{name}" neste workspace.'
            ) from exc

        logger.info(
            'Pasta criada: workspace=%s folder=%s name=%s',
            workspace.pk, folder.pk, folder.name,
        )
        return folder

    # ------------------------------------------------------------------
    # RENOMEAR
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def rename(*, folder: ReferenceFolder, new_name: str, actor=None) -> ReferenceFolder:
        new_name = (new_name or '').strip()

        if not new_name:
            raise ReferenceFolderError('O nome da pasta não pode ser vazio.')

        if len(new_name) > 100:
            raise ReferenceFolderError(
                'O nome da pasta pode ter no máximo 100 caracteres.'
            )

        if new_name == folder.name:
            return folder

        conflict = (
            ReferenceFolder.objects
            .filter(workspace=folder.workspace, name__iexact=new_name)
            .exclude(id=folder.pk)
            .exists()
        )

        if conflict:
            raise ReferenceFolderNameConflictError(
                f'Já existe uma pasta chamada "{new_name}" neste workspace.'
            )

        folder.name = new_name
        folder.save(update_fields=['name', 'updated_at'])

        return folder

    # ------------------------------------------------------------------
    # CAPA
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def set_cover(*, folder: ReferenceFolder, uploaded_file) -> ReferenceFolder:
        """
        Define a capa da pasta. Substitui a anterior, se existir.
        Aceita qualquer imagem — validação básica de extensão.
        """
        if uploaded_file is None:
            raise ReferenceFolderError('Nenhuma imagem foi enviada.')

        name = getattr(uploaded_file, 'name', '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext not in {'jpg', 'jpeg', 'jfif', 'png', 'webp', 'gif'}:
            raise ReferenceFolderError(
                'Formato inválido. Envie JPG, PNG, WEBP ou GIF.'
            )

        # Remove a capa antiga do storage (best-effort)
        old_cover_name = None
        old_cover_storage = None
        if folder.cover:
            try:
                old_cover_name = folder.cover.name
                old_cover_storage = folder.cover.storage
            except Exception:
                pass

        try:
            folder.cover.save(name, uploaded_file, save=False)
        except Exception as exc:
            logger.exception('Falha ao salvar capa no storage')
            raise ReferenceFolderError('Falha ao salvar a capa no storage.') from exc

        folder.save(update_fields=['cover', 'updated_at'])

        if old_cover_name and old_cover_storage:
            try:
                old_cover_storage.delete(old_cover_name)
            except Exception:
                logger.warning(
                    'Não foi possível remover a capa antiga: %s',
                    old_cover_name,
                )

        return folder

    @staticmethod
    @transaction.atomic
    def clear_cover(*, folder: ReferenceFolder) -> ReferenceFolder:
        if not folder.cover:
            return folder

        old_cover_name = folder.cover.name
        old_cover_storage = folder.cover.storage

        folder.cover = None
        folder.save(update_fields=['cover', 'updated_at'])

        try:
            old_cover_storage.delete(old_cover_name)
        except Exception:
            logger.warning('Não foi possível remover a capa: %s', old_cover_name)

        return folder

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete(folder: ReferenceFolder) -> None:
        folder_id = folder.pk
        folder_name = folder.name
        workspace_id = folder.workspace_id

        # Remove a capa do storage (best-effort)
        if folder.cover:
            try:
                folder.cover.delete(save=False)
            except Exception:
                logger.warning('Não foi possível remover a capa ao excluir pasta')

        folder.delete()

        logger.info(
            'Pasta excluída: workspace=%s folder=%s name=%s',
            workspace_id, folder_id, folder_name,
        )