"""
DocumentFolderService — ciclo de vida da pasta.

REGRA ARQUITETURAL
------------------
Único ponto autorizado a:

    - criar pasta
    - renomear pasta
    - excluir pasta

Excluir pasta NÃO exclui documentos. O FK `Document.folder` tem
`on_delete=SET_NULL`, então ao apagar a pasta os documentos voltam
a ficar soltos automaticamente.

Não há histórico de pasta no P0. Pasta é agrupamento visual, não
é objeto auditável.
"""

import logging
from typing import Optional

from django.db import IntegrityError, transaction

from apps.documents.models import Document, DocumentFolder
from apps.documents.exceptions import (
    DocumentFolderNotFoundError,
    DocumentFolderNameConflictError,
    DocumentFolderError,
)

logger = logging.getLogger('documents')


class DocumentFolderService:

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def list_for_workspace(workspace):
        """
        Lista pastas do workspace ordenadas por nome.

        Anota `document_count` para o frontend mostrar a contagem.
        """
        from django.db.models import Count, Q

        return (
            DocumentFolder.objects
            .filter(workspace=workspace)
            .annotate(
                document_count_annotated=Count(
                    'documents',
                    filter=Q(documents__workspace=workspace),
                )
            )
            .order_by('name')
        )

    @staticmethod
    def get_or_raise(folder_id, workspace) -> DocumentFolder:
        folder = (
            DocumentFolder.objects
            .filter(id=folder_id, workspace=workspace)
            .first()
        )
        if folder is None:
            raise DocumentFolderNotFoundError('Pasta não encontrada.')
        return folder

    @staticmethod
    def count_unsorted(workspace) -> int:
        """Quantos documentos estão sem pasta."""
        return (
            Document.objects
            .filter(workspace=workspace, folder__isnull=True)
            .count()
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create(
        *,
        workspace,
        name: str,
        actor=None,
    ) -> DocumentFolder:
        name = (name or '').strip()

        if not name:
            raise DocumentFolderError('O nome da pasta não pode ser vazio.')

        if len(name) > 100:
            raise DocumentFolderError(
                'O nome da pasta pode ter no máximo 100 caracteres.'
            )

        exists = DocumentFolder.objects.filter(
            workspace=workspace, name__iexact=name
        ).exists()

        if exists:
            raise DocumentFolderNameConflictError(
                f'Já existe uma pasta chamada "{name}" neste workspace.'
            )

        try:
            folder = DocumentFolder.objects.create(
                workspace=workspace,
                name=name,
                created_by=actor,
            )
        except IntegrityError as exc:
            logger.warning(
                'Conflito ao criar pasta: workspace=%s name=%s',
                workspace.pk, name,
            )
            raise DocumentFolderNameConflictError(
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
    def rename(
        *,
        folder: DocumentFolder,
        new_name: str,
        actor=None,
    ) -> DocumentFolder:
        new_name = (new_name or '').strip()

        if not new_name:
            raise DocumentFolderError('O nome da pasta não pode ser vazio.')

        if len(new_name) > 100:
            raise DocumentFolderError(
                'O nome da pasta pode ter no máximo 100 caracteres.'
            )

        if new_name == folder.name:
            return folder

        conflict = (
            DocumentFolder.objects
            .filter(workspace=folder.workspace, name__iexact=new_name)
            .exclude(id=folder.pk)
            .exists()
        )

        if conflict:
            raise DocumentFolderNameConflictError(
                f'Já existe uma pasta chamada "{new_name}" neste workspace.'
            )

        previous_name = folder.name
        folder.name = new_name
        folder.save(update_fields=['name', 'updated_at'])

        logger.info(
            'Pasta renomeada: folder=%s %s → %s',
            folder.pk, previous_name, new_name,
        )
        return folder

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete(folder: DocumentFolder) -> None:
        """
        Exclui a pasta.

        Os documentos NÃO são excluídos. O FK `folder` recebe SET_NULL
        automaticamente pelo Django e os documentos voltam a ficar soltos
        na biblioteca.
        """
        folder_id = folder.pk
        folder_name = folder.name
        workspace_id = folder.workspace_id

        folder.delete()

        logger.info(
            'Pasta excluída: workspace=%s folder=%s name=%s '
            '(documentos voltaram a ficar soltos)',
            workspace_id, folder_id, folder_name,
        )