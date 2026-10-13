"""
DocumentViewSet — CRUD + actions de negócio.

REGRA DE CONTEXTO
-----------------
Todos os serializers de leitura (List/Detail) recebem
`context={'request': request}`. Isso garante que `file_url` e
`preview_url` sejam devolvidos como URLs ABSOLUTAS, o que é
obrigatório quando o storage é local (`/media/...` seria relativo
ao path da página).
"""

import logging
import re
import unicodedata

from django.conf import settings
from django.core import signing
from django.http import FileResponse, Http404
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.documents.models import Document, DocumentFolder
from apps.documents.api.serializers import (
    DocumentListSerializer,
    DocumentDetailSerializer,
    DocumentUploadSerializer,
    DocumentUpdateSerializer,
    DocumentReplaceSerializer,
    DocumentAssociateClientSerializer,
    DocumentAssociateProjectSerializer,
    MoveDocumentSerializer,
    DocumentVisibilitySerializer,
    DocumentHistorySerializer,
    GDriveImportSerializer,
)
from apps.documents.services import (
    DocumentService,
    DocumentHistoryService,
    GDriveService,
    DocumentFolderService,
)
from apps.documents.exceptions import (
    DocumentError,
    DocumentNotFoundError,
    DocumentFileMissingError,
    DocumentInvalidUploadError,
    DocumentClientNotFoundError,
    DocumentProjectNotFoundError,
    DocumentFolderNotFoundError,
    DocumentStorageError,
)
from apps.clients.models import Client
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('documents')

PUBLIC_PREVIEW_SALT = 'documents.public-preview'
PUBLIC_PREVIEW_MAX_AGE = 60 * 30


def _ascii_filename(name: str) -> str:
    if not name:
        return 'arquivo'
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^\w\-\. ]+', '_', normalized).strip()
    return normalized or 'arquivo'


def _content_type_for(doc: Document) -> str:
    ct = (doc.mime_type or '').strip()
    if ct and ct != 'application/octet-stream':
        return ct
    ext = (doc.extension or '').lower()
    fallback = {
        'pdf':  'application/pdf',
        'png':  'image/png',
        'jpg':  'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif':  'image/gif',
        'webp': 'image/webp',
        'svg':  'image/svg+xml',
        'txt':  'text/plain; charset=utf-8',
        'md':   'text/plain; charset=utf-8',
        'csv':  'text/csv; charset=utf-8',
        'doc':  'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls':  'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'ppt':  'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    }.get(ext)
    return fallback or 'application/octet-stream'


class DocumentViewSet(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'id'

    # ------------------------------------------------------------------
    # CONTEXTO
    # ------------------------------------------------------------------

    def _current_workspace(self):
        workspace_id = self.request.session.get('current_workspace_id')
        if not workspace_id:
            return None
        return WorkspaceQueries.get_for_user(workspace_id, self.request.user)

    def _require_capability(self, workspace, capability_code):
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=self.request.user,
        ).select_related('governance').first()

        if membership is None:
            return Response(
                {'error': 'Você não é membro deste Workspace'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if membership.governance.key == 'proprietario':
            return None

        has = ConsoleGovernanceCapability.objects.filter(
            governance=membership.governance,
            capability__code=capability_code,
            capability__is_active=True,
        ).exists()

        if not has:
            return Response(
                {'error': f'Sua governança não permite esta ação ({capability_code}).'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    # ------------------------------------------------------------------
    # QUERYSET
    # ------------------------------------------------------------------

    def get_queryset(self):
        workspace = self._current_workspace()
        if workspace is None:
            return Document.objects.none()

        qs = (
            Document.objects
            .filter(workspace=workspace)
            .select_related('client', 'created_by', 'updated_by', 'folder')
            .order_by('-created_at')
        )

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)

        visibility = self.request.query_params.get('visible_to_client')
        if visibility is not None and visibility != '':
            if visibility.lower() in ('1', 'true', 'yes'):
                qs = qs.filter(visible_to_client=True)
            elif visibility.lower() in ('0', 'false', 'no'):
                qs = qs.filter(visible_to_client=False)

        folder_param = self.request.query_params.get('folder')
        if folder_param == 'none':
            qs = qs.filter(folder__isnull=True)
        elif folder_param:
            qs = qs.filter(folder_id=folder_param)

        context = self.request.query_params.get('context')
        if context == 'with_client':
            qs = qs.filter(client__isnull=False)
        elif context == 'without_client':
            qs = qs.filter(client__isnull=True)
        elif context == 'with_project':
            qs = qs.filter(project_id__isnull=False)
        elif context == 'without_project':
            qs = qs.filter(project_id__isnull=True)
        elif context == 'without_any':
            qs = qs.filter(client__isnull=True, project_id__isnull=True)

        return qs

    def _get_document_or_404(self, document_id):
        workspace = self._current_workspace()
        if workspace is None:
            return None
        return Document.objects.filter(
            id=document_id, workspace=workspace
        ).select_related(
            'client', 'created_by', 'updated_by', 'workspace', 'folder'
        ).first()

    # ------------------------------------------------------------------
    # SERIALIZER
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == 'create':
            return DocumentUploadSerializer
        if self.action in ('update', 'partial_update'):
            return DocumentUpdateSerializer
        if self.action == 'replace':
            return DocumentReplaceSerializer
        if self.action == 'associate_client':
            return DocumentAssociateClientSerializer
        if self.action == 'associate_project':
            return DocumentAssociateProjectSerializer
        if self.action == 'move':
            return MoveDocumentSerializer
        if self.action == 'set_visibility':
            return DocumentVisibilitySerializer
        if self.action == 'gdrive_import':
            return GDriveImportSerializer
        if self.action == 'list':
            return DocumentListSerializer
        return DocumentDetailSerializer

    # ------------------------------------------------------------------
    # ERROS
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, DocumentNotFoundError):
            return Response({'error': str(exc) or 'Arquivo não encontrado.'}, status=404)
        if isinstance(exc, DocumentFolderNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, DocumentFileMissingError):
            return Response({'error': str(exc)}, status=410)
        if isinstance(exc, DocumentInvalidUploadError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, DocumentClientNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, DocumentProjectNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, DocumentStorageError):
            return Response({'error': str(exc)}, status=500)
        if isinstance(exc, DocumentError):
            return Response({'error': str(exc)}, status=400)
        return None

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    def list(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.document.view')
        if err is not None:
            return err

        qs = self.get_queryset()
        serializer = DocumentListSerializer(
            qs, many=True, context={'request': request},
        )
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.document.upload')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = None
        client_id = serializer.validated_data.get('client_id')
        if client_id:
            client = Client.objects.filter(id=client_id, workspace=workspace).first()
            if client is None:
                return Response(
                    {'error': 'Cliente não encontrado neste workspace.'},
                    status=400,
                )

        folder = None
        folder_id = serializer.validated_data.get('folder_id')
        if folder_id:
            folder = DocumentFolder.objects.filter(id=folder_id, workspace=workspace).first()
            if folder is None:
                return Response(
                    {'error': 'Pasta não encontrada neste workspace.'},
                    status=400,
                )

        try:
            document = DocumentService.upload(
                workspace=workspace,
                uploaded_file=serializer.validated_data['file'],
                name=serializer.validated_data.get('name', ''),
                client=client,
                project_id=serializer.validated_data.get('project_id'),
                folder=folder,
                created_by=request.user,
                source=serializer.validated_data.get('source', Document.SOURCE_UPLOAD),
                source_url=serializer.validated_data.get('source_url', ''),
                visible_to_client=serializer.validated_data.get('visible_to_client', False),
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao subir arquivo')
            return Response(
                {'error': 'Erro inesperado ao subir o arquivo.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data,
            status=201,
        )

    # ------------------------------------------------------------------
    # RETRIEVE
    # ------------------------------------------------------------------

    def retrieve(self, request, *args, **kwargs):
        document = self._get_document_or_404(kwargs.get('id'))
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.view')
        if err is not None:
            return err

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        document = self._get_document_or_404(kwargs.get('id'))
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.rename')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            if 'name' in serializer.validated_data:
                document = DocumentService.rename(
                    document=document,
                    new_name=serializer.validated_data['name'],
                    actor=request.user,
                )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao renomear arquivo')
            return Response(
                {'error': 'Erro inesperado ao renomear o arquivo.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # DESTROY
    # ------------------------------------------------------------------

    def destroy(self, request, *args, **kwargs):
        document = self._get_document_or_404(kwargs.get('id'))
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.delete')
        if err is not None:
            return err

        try:
            DocumentService.delete(document, actor=request.user)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao excluir arquivo')
            return Response(
                {'error': 'Erro inesperado ao excluir o arquivo.'},
                status=500,
            )

        return Response(status=204)

    # ------------------------------------------------------------------
    # ACTION: replace
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='replace')
    def replace(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.replace')
        if err is not None:
            return err

        serializer = DocumentReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            document = DocumentService.replace_file(
                document=document,
                uploaded_file=serializer.validated_data['file'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao substituir arquivo')
            return Response(
                {'error': 'Erro inesperado ao substituir o arquivo.'},
                status=500,
            )

        document.refresh_from_db()
        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # ACTION: move (mover para pasta)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='move')
    def move(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.move')
        if err is not None:
            return err

        serializer = MoveDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        folder_id = serializer.validated_data.get('folder_id')

        folder = None
        if folder_id:
            folder = DocumentFolder.objects.filter(
                id=folder_id, workspace=document.workspace
            ).first()
            if folder is None:
                return Response(
                    {'error': 'Pasta não encontrada neste workspace.'},
                    status=400,
                )

        try:
            document = DocumentService.move_to_folder(
                document=document,
                folder=folder,
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao mover arquivo')
            return Response(
                {'error': 'Erro inesperado ao mover o arquivo.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # ACTION: set_visibility
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='visibility')
    def set_visibility(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(
            document.workspace, 'documents.document.toggle_visibility'
        )
        if err is not None:
            return err

        serializer = DocumentVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            document = DocumentService.set_visibility(
                document=document,
                visible_to_client=serializer.validated_data['visible_to_client'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao alterar visibilidade')
            return Response(
                {'error': 'Erro inesperado ao alterar a visibilidade.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # ACTION: storage_usage
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='storage-usage')
    def storage_usage(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.document.view')
        if err is not None:
            return err

        try:
            stats = DocumentService.storage_usage(workspace)
        except Exception:
            logger.exception('Erro ao calcular uso de armazenamento')
            return Response(
                {'error': 'Erro ao calcular o uso de armazenamento.'},
                status=500,
            )

        return Response(stats)

    # ------------------------------------------------------------------
    # ACTION: associate_client
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='associate-client')
    def associate_client(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(
            document.workspace, 'documents.document.associate_client'
        )
        if err is not None:
            return err

        serializer = DocumentAssociateClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_id = serializer.validated_data.get('client_id')

        try:
            if client_id:
                client = Client.objects.filter(
                    id=client_id, workspace=document.workspace
                ).first()
                if client is None:
                    return Response(
                        {'error': 'Cliente não encontrado neste workspace.'},
                        status=400,
                    )
                document = DocumentService.associate_client(
                    document=document, client=client, actor=request.user,
                )
            else:
                document = DocumentService.dissociate_client(
                    document=document, actor=request.user,
                )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao associar cliente')
            return Response(
                {'error': 'Erro inesperado ao associar cliente.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # ACTION: associate_project
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='associate-project')
    def associate_project(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(
            document.workspace, 'documents.document.associate_project'
        )
        if err is not None:
            return err

        serializer = DocumentAssociateProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project_id = serializer.validated_data.get('project_id')

        try:
            if project_id:
                document = DocumentService.associate_project(
                    document=document, project_id=project_id, actor=request.user,
                )
            else:
                document = DocumentService.dissociate_project(
                    document=document, actor=request.user,
                )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao associar projeto')
            return Response(
                {'error': 'Erro inesperado ao associar projeto.'},
                status=500,
            )

        return Response(
            DocumentDetailSerializer(
                document, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # ACTION: download
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(
            document.workspace, 'documents.document.download'
        )
        if err is not None:
            return err

        try:
            DocumentService.ensure_file_present(document)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao verificar arquivo')
            return Response(
                {'error': 'Erro inesperado ao verificar o arquivo.'},
                status=500,
            )

        try:
            response = FileResponse(
                document.file.open('rb'),
                as_attachment=True,
                filename=document.full_name,
            )
            response['Content-Type'] = _content_type_for(document)
            return response
        except Exception:
            logger.exception('Erro inesperado ao servir arquivo')
            return Response(
                {'error': 'Erro inesperado ao servir o arquivo.'},
                status=500,
            )

    # ------------------------------------------------------------------
    # ACTION: preview
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='preview')
    @xframe_options_sameorigin
    def preview(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.view')
        if err is not None:
            return err

        try:
            DocumentService.ensure_file_present(document)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao verificar arquivo')
            return Response(
                {'error': 'Erro inesperado ao verificar o arquivo.'},
                status=500,
            )

        try:
            file_handle = document.file.open('rb')
            response = FileResponse(file_handle)
            response['Content-Type'] = _content_type_for(document)
            safe_name = _ascii_filename(document.full_name)
            response['Content-Disposition'] = f'inline; filename="{safe_name}"'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            response['Content-Security-Policy'] = "frame-ancestors 'self'"
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
        except Exception:
            logger.exception('Erro inesperado ao servir preview')
            return Response(
                {'error': 'Erro inesperado ao servir o preview.'},
                status=500,
            )

    # ------------------------------------------------------------------
    # ACTION: public_preview_link
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='public-preview-link')
    def public_preview_link(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.view')
        if err is not None:
            return err

        token = signing.dumps(
            {'doc_id': str(document.id)},
            salt=PUBLIC_PREVIEW_SALT,
        )

        path = f'/api/documents/public-preview/{token}/'

        base = getattr(settings, 'FRONTEND_URL', '') or ''
        base = base.rstrip('/')

        if base:
            absolute = base + path
        else:
            absolute = request.build_absolute_uri(path)

        if absolute.startswith('http://') and 'localhost' not in absolute and '127.0.0.1' not in absolute:
            absolute = 'https://' + absolute[len('http://'):]

        return Response({
            'url': absolute,
            'expires_in': PUBLIC_PREVIEW_MAX_AGE,
        })

    # ------------------------------------------------------------------
    # ACTION: history
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, id=None):
        document = self._get_document_or_404(id)
        if document is None:
            return Response({'error': 'Arquivo não encontrado'}, status=404)

        err = self._require_capability(document.workspace, 'documents.document.view')
        if err is not None:
            return err

        entries = DocumentHistoryService.list_for_document(document)
        serializer = DocumentHistorySerializer(entries, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # ACTION: gdrive_list
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='gdrive/list')
    def gdrive_list(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.document.upload')
        if err is not None:
            return err

        query = request.query_params.get('q', '').strip()

        try:
            files = GDriveService.list_files(request.user, query=query)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao listar arquivos do Drive')
            return Response(
                {'error': 'Erro ao listar arquivos do Google Drive.'},
                status=500,
            )

        return Response({'files': files})

    # ------------------------------------------------------------------
    # ACTION: gdrive_import
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='gdrive/import')
    def gdrive_import(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.document.upload')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = None
        client_id = serializer.validated_data.get('client_id')
        if client_id:
            client = Client.objects.filter(id=client_id, workspace=workspace).first()
            if client is None:
                return Response(
                    {'error': 'Cliente não encontrado neste workspace.'},
                    status=400,
                )

        folder = None
        folder_id = serializer.validated_data.get('folder_id')
        if folder_id:
            folder = DocumentFolder.objects.filter(id=folder_id, workspace=workspace).first()
            if folder is None:
                return Response(
                    {'error': 'Pasta não encontrada neste workspace.'},
                    status=400,
                )

        try:
            imported = []
            errors = []
            for meta in serializer.validated_data['files']:
                try:
                    doc = GDriveService.import_file(
                        workspace=workspace,
                        user=request.user,
                        file_meta=meta,
                        client=client,
                        project_id=serializer.validated_data.get('project_id'),
                    )
                    if folder is not None:
                        doc = DocumentService.move_to_folder(
                            document=doc, folder=folder, actor=request.user,
                        )
                    imported.append(doc)
                except Exception as e:
                    logger.exception('Falha ao importar arquivo do Drive')
                    errors.append({
                        'name': meta.get('name') or 'arquivo',
                        'error': str(e),
                    })
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao importar do Drive')
            return Response(
                {'error': 'Erro inesperado ao importar do Google Drive.'},
                status=500,
            )

        return Response({
            'imported': DocumentDetailSerializer(
                imported, many=True, context={'request': request},
            ).data,
            'errors': errors,
        }, status=201)

    # ------------------------------------------------------------------
    # ACTION: gdrive_status
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='gdrive/status')
    def gdrive_status(self, request):
        """
        Informa se o usuário tem conta Google conectada COM refresh token.
        """
        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            return Response({
                'connected': False,
                'has_refresh': False,
                'needs_reconnect': False,
                'user_email': None,
            })

        sa = SocialAccount.objects.filter(
            user=request.user, provider='google'
        ).first()

        if not sa:
            return Response({
                'connected': False,
                'has_refresh': False,
                'needs_reconnect': False,
                'user_email': None,
            })

        st = SocialToken.objects.filter(account=sa).first()
        has_token = bool(st and st.token)
        has_refresh = bool(st and st.token_secret)

        return Response({
            'connected': has_token and has_refresh,
            'has_refresh': has_refresh,
            'needs_reconnect': has_token and not has_refresh,
            'user_email': sa.user.email,
        })


# =========================================================================
# VIEW PÚBLICA
# =========================================================================

class DocumentPublicPreviewView(View):

    def get(self, request, token):
        try:
            data = signing.loads(
                token,
                salt=PUBLIC_PREVIEW_SALT,
                max_age=PUBLIC_PREVIEW_MAX_AGE,
            )
        except signing.SignatureExpired:
            raise Http404('Link expirado.')
        except signing.BadSignature:
            raise Http404('Link inválido.')

        doc_id = data.get('doc_id')
        if not doc_id:
            raise Http404('Link inválido.')

        try:
            document = Document.objects.select_related('workspace').get(id=doc_id)
        except Document.DoesNotExist:
            raise Http404('Arquivo não encontrado.')

        try:
            DocumentService.ensure_file_present(document)
        except Exception:
            raise Http404('Arquivo indisponível.')

        try:
            file_handle = document.file.open('rb')
            response = FileResponse(file_handle)
            response['Content-Type'] = _content_type_for(document)
            safe_name = _ascii_filename(document.full_name)
            response['Content-Disposition'] = f'inline; filename="{safe_name}"'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Access-Control-Allow-Origin'] = '*'
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return response
        except Exception:
            logger.exception('Erro ao servir public preview')
            raise Http404('Erro ao servir arquivo.')