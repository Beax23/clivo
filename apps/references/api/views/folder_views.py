"""
ReferenceFolderViewSet — CRUD de pastas.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.references.models import ReferenceFolder
from apps.references.api.serializers import (
    ReferenceFolderSerializer,
    ReferenceFolderCreateSerializer,
    ReferenceFolderUpdateSerializer,
    ReferenceFolderCoverSerializer,
)
from apps.references.services import ReferenceFolderService
from apps.references.exceptions import (
    ReferenceError,
    ReferenceFolderNotFoundError,
    ReferenceFolderNameConflictError,
    ReferenceFolderError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('references')


class ReferenceFolderViewSet(viewsets.GenericViewSet):

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

    def get_serializer_class(self):
        if self.action == 'create':
            return ReferenceFolderCreateSerializer
        if self.action == 'partial_update':
            return ReferenceFolderUpdateSerializer
        if self.action == 'set_cover':
            return ReferenceFolderCoverSerializer
        return ReferenceFolderSerializer

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, ReferenceFolderNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, ReferenceFolderNameConflictError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, ReferenceFolderError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceError):
            return Response({'error': str(exc)}, status=400)
        return None

    def list(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.view')
        if err is not None:
            return err

        folders = ReferenceFolderService.list_for_workspace(workspace)
        serializer = ReferenceFolderSerializer(folders, many=True)
        unsorted = ReferenceFolderService.count_unsorted(workspace)

        if request.query_params.get('flat') in ('1', 'true', 'yes'):
            return Response(serializer.data)
        return Response({
            'folders': serializer.data,
            'results': serializer.data,
            'count': len(serializer.data),
            'unsorted_count': unsorted,
        })

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.create')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            folder = ReferenceFolderService.create(
                workspace=workspace,
                name=serializer.validated_data['name'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar pasta')
            return Response({'error': 'Erro inesperado ao criar a pasta.'}, status=500)

        return Response(
            ReferenceFolderSerializer(folder).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.view')
        if err is not None:
            return err
        try:
            folder = ReferenceFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)
        return Response(ReferenceFolderSerializer(folder).data)

    def partial_update(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.rename')
        if err is not None:
            return err
        try:
            folder = ReferenceFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            folder = ReferenceFolderService.rename(
                folder=folder,
                new_name=serializer.validated_data['name'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao renomear pasta')
            return Response({'error': 'Erro inesperado ao renomear a pasta.'}, status=500)
        return Response(ReferenceFolderSerializer(folder).data)

    # ------------------------------------------------------------------
    # ACTION: set_cover (POST /cover/)
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=['post'],
        url_path='cover',
        parser_classes=[MultiPartParser, FormParser],
    )
    def set_cover(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.rename')
        if err is not None:
            return err
        try:
            folder = ReferenceFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = ReferenceFolderCoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            folder = ReferenceFolderService.set_cover(
                folder=folder,
                uploaded_file=serializer.validated_data['cover'],
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao salvar capa')
            return Response({'error': 'Erro inesperado ao salvar a capa.'}, status=500)

        return Response(ReferenceFolderSerializer(folder).data)

    # ------------------------------------------------------------------
    # ACTION: clear_cover (DELETE /cover/clear/) — url_path DIFERENTE
    # ------------------------------------------------------------------

    @action(detail=True, methods=['delete'], url_path='cover/clear')
    def clear_cover(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.rename')
        if err is not None:
            return err
        try:
            folder = ReferenceFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        try:
            folder = ReferenceFolderService.clear_cover(folder=folder)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao remover capa')
            return Response({'error': 'Erro inesperado ao remover a capa.'}, status=500)
        return Response(ReferenceFolderSerializer(folder).data)

    def destroy(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.folder.delete')
        if err is not None:
            return err
        try:
            folder = ReferenceFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)
        try:
            ReferenceFolderService.delete(folder)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao excluir pasta')
            return Response({'error': 'Erro inesperado ao excluir a pasta.'}, status=500)
        return Response(status=status.HTTP_204_NO_CONTENT)