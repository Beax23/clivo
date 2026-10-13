"""
DocumentFolderViewSet — CRUD de pastas.

CAPABILITIES
------------
    documents.folder.view    → list
    documents.folder.create  → create
    documents.folder.rename  → partial_update
    documents.folder.delete  → destroy
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.documents.models import DocumentFolder
from apps.documents.api.serializers import (
    DocumentFolderSerializer,
    DocumentFolderCreateSerializer,
    DocumentFolderUpdateSerializer,
)
from apps.documents.services import DocumentFolderService
from apps.documents.exceptions import (
    DocumentError,
    DocumentFolderNotFoundError,
    DocumentFolderNameConflictError,
    DocumentFolderError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('documents')


class DocumentFolderViewSet(viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
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
    # SERIALIZER
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == 'create':
            return DocumentFolderCreateSerializer
        if self.action == 'partial_update':
            return DocumentFolderUpdateSerializer
        return DocumentFolderSerializer

    # ------------------------------------------------------------------
    # ERROS
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, DocumentFolderNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, DocumentFolderNameConflictError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, DocumentFolderError):
            return Response({'error': str(exc)}, status=400)
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

        err = self._require_capability(workspace, 'documents.folder.view')
        if err is not None:
            return err

        folders = DocumentFolderService.list_for_workspace(workspace)
        serializer = DocumentFolderSerializer(folders, many=True)

        unsorted_count = DocumentFolderService.count_unsorted(workspace)

        return Response({
            'folders': serializer.data,
            'unsorted_count': unsorted_count,
        })

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.folder.create')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            folder = DocumentFolderService.create(
                workspace=workspace,
                name=serializer.validated_data['name'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao criar pasta')
            return Response(
                {'error': 'Erro inesperado ao criar a pasta.'},
                status=500,
            )

        return Response(
            DocumentFolderSerializer(folder).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # RETRIEVE
    # ------------------------------------------------------------------

    def retrieve(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.folder.view')
        if err is not None:
            return err

        try:
            folder = DocumentFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        return Response(DocumentFolderSerializer(folder).data)

    # ------------------------------------------------------------------
    # PARTIAL UPDATE (rename)
    # ------------------------------------------------------------------

    def partial_update(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.folder.rename')
        if err is not None:
            return err

        try:
            folder = DocumentFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            folder = DocumentFolderService.rename(
                folder=folder,
                new_name=serializer.validated_data['name'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao renomear pasta')
            return Response(
                {'error': 'Erro inesperado ao renomear a pasta.'},
                status=500,
            )

        return Response(DocumentFolderSerializer(folder).data)

    # ------------------------------------------------------------------
    # DESTROY
    # ------------------------------------------------------------------

    def destroy(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'documents.folder.delete')
        if err is not None:
            return err

        try:
            folder = DocumentFolderService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        try:
            DocumentFolderService.delete(folder)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao excluir pasta')
            return Response(
                {'error': 'Erro inesperado ao excluir a pasta.'},
                status=500,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)