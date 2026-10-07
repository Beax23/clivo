"""
DocumentService — ciclo de vida completo do Document.
"""

import logging
import mimetypes
from typing import Optional

from django.db import transaction

from apps.documents.models import Document, DocumentHistory
from apps.documents.exceptions import (
    DocumentNotFoundError,
    DocumentFileMissingError,
    DocumentInvalidUploadError,
    DocumentClientNotFoundError,
    DocumentProjectNotFoundError,
    DocumentStorageError,
)
from apps.documents.queries import DocumentQueries
from apps.documents.services.history_service import DocumentHistoryService

logger = logging.getLogger('documents')


class DocumentService:

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def upload(
        *,
        workspace,
        uploaded_file,
        name: Optional[str] = None,
        client=None,
        project_id=None,
        created_by=None,
        source: str = Document.SOURCE_UPLOAD,
        source_url: str = '',
    ) -> Document:
        """
        Cria um novo Document a partir de um arquivo enviado.

        Parâmetros:
            workspace      → workspace de destino (obrigatório)
            uploaded_file  → InMemoryUploadedFile ou TemporaryUploadedFile
            name           → nome sem extensão. Se vazio, usa o do arquivo.
            client         → Client opcional
            project_id     → UUID opcional (projects.Project.id)
            created_by     → User opcional
            source         → origem (upload/gdrive/url)
            source_url     → URL original (quando aplicável)
        """
        DocumentService._validate_uploaded_file(uploaded_file)

        original_name = uploaded_file.name or ''
        resolved_name = (name or Document.extract_name(original_name)).strip()
        if not resolved_name:
            raise DocumentInvalidUploadError(
                'Não foi possível determinar o nome do arquivo.'
            )

        extension = Document.extract_extension(original_name)
        mime_type = (
            getattr(uploaded_file, 'content_type', None)
            or mimetypes.guess_type(original_name)[0]
            or ''
        )
        size = getattr(uploaded_file, 'size', 0) or 0

        if client is not None:
            DocumentService._validate_client(workspace, client)

        if source not in dict(Document.SOURCE_CHOICES):
            source = Document.SOURCE_UPLOAD

        document = Document(
            workspace=workspace,
            name=resolved_name,
            extension=extension,
            mime_type=mime_type,
            size=size,
            client=client,
            project_id=project_id,
            source=source,
            source_url=(source_url or '')[:1000],
            created_by=created_by,
            updated_by=created_by,
        )

        try:
            document.file.save(original_name, uploaded_file, save=False)
        except Exception as exc:
            logger.exception('Falha ao salvar arquivo no storage')
            raise DocumentStorageError(
                'Falha ao salvar o arquivo no storage.'
            ) from exc

        document.save()

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_CREATED,
            user=created_by,
            previous_value=None,
            new_value={
                'name': document.name,
                'extension': document.extension,
                'mime_type': document.mime_type,
                'size': document.size,
                'client_id': str(document.client_id) if document.client_id else None,
                'project_id': str(document.project_id) if document.project_id else None,
                'source': document.source,
                'source_url': document.source_url or None,
            },
        )

        logger.info(
            'Document criado: workspace=%s document=%s name=%s source=%s',
            workspace.pk, document.pk, document.full_name, document.source,
        )
        return document

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_raise(document_id, workspace) -> Document:
        document = DocumentQueries.get_by_id_in_workspace(document_id, workspace)
        if document is None:
            raise DocumentNotFoundError('Arquivo não encontrado.')
        return document

    # ------------------------------------------------------------------
    # RENOMEAR
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def rename(
        *,
        document: Document,
        new_name: str,
        actor=None,
    ) -> Document:
        new_name = (new_name or '').strip()
        if not new_name:
            raise DocumentInvalidUploadError('O nome não pode ser vazio.')

        if new_name == document.name:
            return document

        previous_name = document.name
        document.name = new_name
        document.updated_by = actor
        document.save(update_fields=['name', 'updated_by', 'updated_at'])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_RENAMED,
            user=actor,
            previous_value={'name': previous_name},
            new_value={'name': new_name},
        )
        return document

    # ------------------------------------------------------------------
    # SUBSTITUIR ARQUIVO FÍSICO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def replace_file(
        *,
        document: Document,
        uploaded_file,
        actor=None,
    ) -> Document:
        DocumentService._validate_uploaded_file(uploaded_file)

        original_name = uploaded_file.name or ''
        previous_extension = document.extension
        previous_mime = document.mime_type
        previous_size = document.size

        new_extension = Document.extract_extension(original_name)
        new_mime = (
            getattr(uploaded_file, 'content_type', None)
            or mimetypes.guess_type(original_name)[0]
            or ''
        )
        new_size = getattr(uploaded_file, 'size', 0) or 0

        try:
            if document.file:
                document.file.delete(save=False)
        except Exception:
            logger.warning(
                'Falha ao remover arquivo antigo do storage: document=%s',
                document.pk,
            )

        try:
            document.file.save(original_name, uploaded_file, save=False)
        except Exception as exc:
            logger.exception('Falha ao salvar arquivo substituto')
            raise DocumentStorageError(
                'Falha ao salvar o arquivo substituto no storage.'
            ) from exc

        document.extension = new_extension
        document.mime_type = new_mime
        document.size = new_size
        document.updated_by = actor
        # Substituição NÃO altera a origem: se veio do Drive, continua
        # sendo origem Drive (o conteúdo é que mudou).
        document.save(update_fields=[
            'file', 'extension', 'mime_type', 'size',
            'updated_by', 'updated_at',
        ])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_REPLACED,
            user=actor,
            previous_value={
                'extension': previous_extension,
                'mime_type': previous_mime,
                'size': previous_size,
            },
            new_value={
                'extension': new_extension,
                'mime_type': new_mime,
                'size': new_size,
            },
        )
        return document

    # ------------------------------------------------------------------
    # ASSOCIAÇÃO DE CLIENTE
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def associate_client(
        *,
        document: Document,
        client,
        actor=None,
    ) -> Document:
        DocumentService._validate_client(document.workspace, client)

        if document.client_id == client.id:
            return document

        previous_client_id = str(document.client_id) if document.client_id else None
        document.client = client
        document.updated_by = actor
        document.save(update_fields=['client', 'updated_by', 'updated_at'])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_CLIENT_ASSOCIATED,
            user=actor,
            previous_value={'client_id': previous_client_id},
            new_value={'client_id': str(client.id)},
        )
        return document

    @staticmethod
    @transaction.atomic
    def dissociate_client(
        *,
        document: Document,
        actor=None,
    ) -> Document:
        if document.client_id is None:
            return document

        previous_client_id = str(document.client_id)
        document.client = None
        document.updated_by = actor
        document.save(update_fields=['client', 'updated_by', 'updated_at'])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_CLIENT_REMOVED,
            user=actor,
            previous_value={'client_id': previous_client_id},
            new_value={'client_id': None},
        )
        return document

    # ------------------------------------------------------------------
    # ASSOCIAÇÃO DE PROJETO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def associate_project(
        *,
        document: Document,
        project_id,
        actor=None,
    ) -> Document:
        if project_id is None:
            raise DocumentInvalidUploadError(
                'project_id é obrigatório para associação.'
            )

        if document.project_id == project_id:
            return document

        previous = str(document.project_id) if document.project_id else None
        document.project_id = project_id
        document.updated_by = actor
        document.save(update_fields=['project_id', 'updated_by', 'updated_at'])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_PROJECT_ASSOCIATED,
            user=actor,
            previous_value={'project_id': previous},
            new_value={'project_id': str(project_id)},
        )
        return document

    @staticmethod
    @transaction.atomic
    def dissociate_project(
        *,
        document: Document,
        actor=None,
    ) -> Document:
        if document.project_id is None:
            return document

        previous = str(document.project_id)
        document.project_id = None
        document.updated_by = actor
        document.save(update_fields=['project_id', 'updated_by', 'updated_at'])

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_PROJECT_REMOVED,
            user=actor,
            previous_value={'project_id': previous},
            new_value={'project_id': None},
        )
        return document

    # ------------------------------------------------------------------
    # INTEGRIDADE DO ARQUIVO
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_file_present(document: Document) -> None:
        try:
            if not document.file or not document.file.storage.exists(document.file.name):
                raise DocumentFileMissingError(
                    'O arquivo físico não foi encontrado no storage.'
                )
        except DocumentFileMissingError:
            raise
        except Exception as exc:
            raise DocumentStorageError(
                'Falha ao verificar a presença do arquivo no storage.'
            ) from exc

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete(document: Document, actor=None) -> None:
        document_id = document.pk
        document_label = document.full_name
        workspace_id = document.workspace_id

        DocumentHistoryService.log(
            document=document,
            action=DocumentHistory.ACTION_DELETED,
            user=actor,
            previous_value={
                'name': document.name,
                'extension': document.extension,
                'mime_type': document.mime_type,
                'size': document.size,
                'source': document.source,
            },
            new_value=None,
        )

        try:
            if document.file:
                document.file.delete(save=False)
        except Exception as exc:
            logger.exception(
                'Falha ao remover arquivo físico do storage: document=%s',
                document_id,
            )
            raise DocumentStorageError(
                'Falha ao remover o arquivo físico do storage.'
            ) from exc

        document.delete()

        logger.info(
            'Document excluído: workspace=%s document=%s name=%s',
            workspace_id, document_id, document_label,
        )

    # ------------------------------------------------------------------
    # HELPERS INTERNOS
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_uploaded_file(uploaded_file) -> None:
        if uploaded_file is None:
            raise DocumentInvalidUploadError('Nenhum arquivo foi enviado.')

        name = getattr(uploaded_file, 'name', None)
        if not name:
            raise DocumentInvalidUploadError(
                'O arquivo enviado não possui nome.'
            )

        size = getattr(uploaded_file, 'size', None)
        if size is None or size <= 0:
            raise DocumentInvalidUploadError(
                'O arquivo enviado está vazio.'
            )

    @staticmethod
    def _validate_client(workspace, client) -> None:
        if client is None:
            return
        if getattr(client, 'workspace_id', None) != workspace.id:
            raise DocumentClientNotFoundError(
                'Cliente não encontrado neste workspace.'
            )