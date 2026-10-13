"""
ReferenceViewSet — CRUD + actions de negócio.
"""

import logging
import os
from urllib.parse import quote

from django.http import FileResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.references.models import Reference, ReferenceFolder
from apps.references.api.serializers import (
    ReferenceListSerializer,
    ReferenceDetailSerializer,
    ReferenceUploadSerializer,
    ReferenceUpdateSerializer,
    ReferenceSetCategoriesSerializer,
    ReferenceAssociateClientSerializer,
    ReferenceAssociateProjectSerializer,
    MoveReferenceSerializer,
    ReferenceVisibilitySerializer,
    ReferenceHistorySerializer,
)
from apps.references.services import (
    ReferenceService, ReferenceHistoryService,
)
from apps.references.exceptions import (
    ReferenceError,
    ReferenceNotFoundError,
    ReferenceInvalidImageError,
    ReferenceClientNotFoundError,
    ReferenceProjectNotFoundError,
    ReferenceFolderNotFoundError,
    ReferenceStorageError,
)
from apps.clients.models import Client
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('references')


CONTENT_TYPES_BY_EXT = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'jfif': 'image/jpeg',
    'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp',
    'bmp': 'image/bmp', 'tif': 'image/tiff', 'tiff': 'image/tiff',
    'svg': 'image/svg+xml',
}


def _extension_of(reference: Reference) -> str:
    ext = (reference.extension or '').strip().lower()
    if ext:
        return ext
    if reference.image and reference.image.name:
        name = reference.image.name
        if '.' in name:
            return name.rsplit('.', 1)[-1].lower()
    title = (reference.title or '').strip()
    if '.' in title:
        return title.rsplit('.', 1)[-1].lower()
    return ''


def _download_filename(reference: Reference) -> str:
    title = (reference.title or 'referencia').strip() or 'referencia'
    base = title.rsplit('.', 1)[0] if '.' in title else title
    base = base.replace('"', '').replace('\\', '').strip() or 'referencia'
    ext = _extension_of(reference)
    return f"{base}.{ext}" if ext else base


class ReferenceViewSet(viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'id'

    def _current_workspace(self):
        workspace_id = self.request.session.get('current_workspace_id')
        if not workspace_id:
            return None
        return WorkspaceQueries.get_for_user(workspace_id, self.request.user)

    def _require_capability(self, workspace, capability_code):
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace, user=self.request.user,
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

    def get_queryset(self):
        workspace = self._current_workspace()
        if workspace is None:
            return Reference.objects.none()

        qs = (
            Reference.objects
            .filter(workspace=workspace)
            .select_related('client', 'folder', 'created_by', 'updated_by')
            .prefetch_related('categories')
            .order_by('-created_at')
        )

        search = (
            self.request.query_params.get('search')
            or self.request.query_params.get('q')
        )
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(categories__name__icontains=search)
                | Q(client__name__icontains=search)
                | Q(folder__name__icontains=search)
                | Q(source__icontains=search)
                | Q(source_url__icontains=search)
            ).distinct()

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        project_id = self.request.query_params.get('project')
        if project_id:
            qs = qs.filter(project_id=project_id)

        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(categories__id=category_id)

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

        return qs

    def _get_reference_or_404(self, reference_id):
        workspace = self._current_workspace()
        if workspace is None:
            return None
        return (
            Reference.objects
            .filter(id=reference_id, workspace=workspace)
            .select_related('client', 'folder', 'created_by', 'updated_by', 'workspace')
            .prefetch_related('categories')
            .first()
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return ReferenceUploadSerializer
        if self.action in ('update', 'partial_update'):
            return ReferenceUpdateSerializer
        if self.action == 'set_categories':
            return ReferenceSetCategoriesSerializer
        if self.action == 'associate_client':
            return ReferenceAssociateClientSerializer
        if self.action == 'associate_project':
            return ReferenceAssociateProjectSerializer
        if self.action == 'move':
            return MoveReferenceSerializer
        if self.action == 'set_visibility':
            return ReferenceVisibilitySerializer
        if self.action == 'list':
            return ReferenceListSerializer
        return ReferenceDetailSerializer

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, ReferenceNotFoundError):
            return Response({'error': str(exc) or 'Referência não encontrada.'}, status=404)
        if isinstance(exc, ReferenceFolderNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceInvalidImageError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceClientNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceProjectNotFoundError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceStorageError):
            return Response({'error': str(exc)}, status=500)
        if isinstance(exc, ReferenceError):
            return Response({'error': str(exc)}, status=400)
        return None

    def list(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.reference.view')
        if err is not None:
            return err

        qs = self.get_queryset()
        page_param = request.query_params.get('page')
        page_size_param = request.query_params.get('page_size')
        total = qs.count()

        if page_param or page_size_param:
            try:
                page = max(1, int(page_param or 1))
            except (TypeError, ValueError):
                page = 1
            try:
                page_size = min(200, max(1, int(page_size_param or 24)))
            except (TypeError, ValueError):
                page_size = 24
            qs_page = qs[(page - 1) * page_size : (page - 1) * page_size + page_size]
        else:
            qs_page = qs

        serializer = ReferenceListSerializer(qs_page, many=True)
        return Response({'count': total, 'results': serializer.data})

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.reference.upload')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = None
        client_id = serializer.validated_data.get('client_id')
        if client_id:
            client = Client.objects.filter(id=client_id, workspace=workspace).first()
            if client is None:
                return Response({'error': 'Cliente não encontrado neste workspace.'}, status=400)

        folder = None
        folder_id = serializer.validated_data.get('folder_id')
        if folder_id:
            folder = ReferenceFolder.objects.filter(id=folder_id, workspace=workspace).first()
            if folder is None:
                return Response({'error': 'Pasta não encontrada neste workspace.'}, status=400)

        try:
            reference = ReferenceService.upload(
                workspace=workspace,
                uploaded_file=serializer.validated_data['image'],
                title=serializer.validated_data['title'],
                description=serializer.validated_data.get('description', ''),
                category_ids=serializer.validated_data.get('category_ids', []),
                client=client,
                project_id=serializer.validated_data.get('project_id'),
                folder=folder,
                created_by=request.user,
                source=serializer.validated_data.get('source', Reference.SOURCE_UPLOAD),
                source_url=serializer.validated_data.get('source_url', ''),
                visible_to_client=serializer.validated_data.get('visible_to_client', False),
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao subir referência')
            return Response({'error': 'Erro inesperado ao subir a referência.'}, status=500)

        return Response(ReferenceDetailSerializer(reference).data, status=201)

    def retrieve(self, request, *args, **kwargs):
        ref = self._get_reference_or_404(kwargs.get('id'))
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.view')
        if err is not None:
            return err
        return Response(ReferenceDetailSerializer(ref).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        ref = self._get_reference_or_404(kwargs.get('id'))
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.edit')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            ref = ReferenceService.edit(
                reference=ref,
                title=serializer.validated_data.get('title'),
                description=serializer.validated_data.get('description'),
                category_ids=serializer.validated_data.get('category_ids'),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar referência')
            return Response({'error': 'Erro inesperado ao editar a referência.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    def destroy(self, request, *args, **kwargs):
        ref = self._get_reference_or_404(kwargs.get('id'))
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.delete')
        if err is not None:
            return err
        try:
            ReferenceService.delete(ref, actor=request.user)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao excluir referência')
            return Response({'error': 'Erro inesperado ao excluir a referência.'}, status=500)
        return Response(status=204)

    # ------------------------------------------------------------------
    # ACTION: set_categories
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='categories')
    def set_categories(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.edit')
        if err is not None:
            return err

        serializer = ReferenceSetCategoriesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            ref = ReferenceService.set_categories(
                reference=ref,
                category_ids=serializer.validated_data['category_ids'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao definir categorias')
            return Response({'error': 'Erro inesperado.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    @action(detail=True, methods=['post'], url_path='move')
    def move(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.move')
        if err is not None:
            return err

        serializer = MoveReferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        folder_id = serializer.validated_data.get('folder_id')
        folder = None
        if folder_id:
            folder = ReferenceFolder.objects.filter(
                id=folder_id, workspace=ref.workspace
            ).first()
            if folder is None:
                return Response({'error': 'Pasta não encontrada neste workspace.'}, status=400)
        try:
            ref = ReferenceService.move_to_folder(
                reference=ref, folder=folder, actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao mover referência')
            return Response({'error': 'Erro inesperado ao mover a referência.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    @action(detail=True, methods=['post'], url_path='visibility')
    def set_visibility(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(
            ref.workspace, 'references.reference.toggle_visibility'
        )
        if err is not None:
            return err
        serializer = ReferenceVisibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ref = ReferenceService.set_visibility(
                reference=ref,
                visible_to_client=serializer.validated_data['visible_to_client'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao alterar visibilidade')
            return Response({'error': 'Erro inesperado.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    @action(detail=False, methods=['get'], url_path='storage-usage')
    def storage_usage(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.reference.view')
        if err is not None:
            return err
        try:
            stats = ReferenceService.storage_usage(workspace)
        except Exception:
            logger.exception('Erro ao calcular uso de armazenamento')
            return Response({'error': 'Erro ao calcular o uso.'}, status=500)
        return Response(stats)

    @action(detail=True, methods=['post'], url_path='associate-client')
    def associate_client(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(
            ref.workspace, 'references.reference.associate_client'
        )
        if err is not None:
            return err
        serializer = ReferenceAssociateClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client_id = serializer.validated_data.get('client_id')
        try:
            if client_id:
                client = Client.objects.filter(
                    id=client_id, workspace=ref.workspace
                ).first()
                if client is None:
                    return Response({'error': 'Cliente não encontrado.'}, status=400)
                ref = ReferenceService.associate_client(
                    reference=ref, client=client, actor=request.user,
                )
            else:
                ref = ReferenceService.dissociate_client(
                    reference=ref, actor=request.user,
                )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao associar cliente')
            return Response({'error': 'Erro inesperado.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    @action(detail=True, methods=['post'], url_path='associate-project')
    def associate_project(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(
            ref.workspace, 'references.reference.associate_project'
        )
        if err is not None:
            return err
        serializer = ReferenceAssociateProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project_id = serializer.validated_data.get('project_id')
        try:
            if project_id:
                ref = ReferenceService.associate_project(
                    reference=ref, project_id=project_id, actor=request.user,
                )
            else:
                ref = ReferenceService.dissociate_project(
                    reference=ref, actor=request.user,
                )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao associar projeto')
            return Response({'error': 'Erro inesperado.'}, status=500)
        return Response(ReferenceDetailSerializer(ref).data)

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(
            ref.workspace, 'references.reference.download'
        )
        if err is not None:
            return err
        try:
            ReferenceService.ensure_image_present(ref)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao verificar imagem')
            return Response({'error': 'Erro inesperado.'}, status=500)
        try:
            filename = _download_filename(ref)
            ext = _extension_of(ref)
            response = FileResponse(
                ref.image.open('rb'),
                as_attachment=True,
                filename=filename,
            )
            response['Content-Type'] = CONTENT_TYPES_BY_EXT.get(
                ext, 'application/octet-stream'
            )
            response['Content-Disposition'] = (
                f"attachment; filename=\"{filename}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
            return response
        except Exception:
            logger.exception('Erro ao servir imagem')
            return Response({'error': 'Erro inesperado.'}, status=500)

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, id=None):
        ref = self._get_reference_or_404(id)
        if ref is None:
            return Response({'error': 'Referência não encontrada'}, status=404)
        err = self._require_capability(ref.workspace, 'references.reference.view')
        if err is not None:
            return err
        entries = ReferenceHistoryService.list_for_reference(ref)
        serializer = ReferenceHistorySerializer(entries, many=True)
        return Response(serializer.data)