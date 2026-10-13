"""
ReferenceCategoryViewSet — CRUD de categorias.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.references.api.serializers import (
    ReferenceCategorySerializer,
    ReferenceCategoryCreateSerializer,
    ReferenceCategoryUpdateSerializer,
)
from apps.references.services import ReferenceCategoryService
from apps.references.exceptions import (
    ReferenceError,
    ReferenceCategoryNotFoundError,
    ReferenceCategoryNameConflictError,
    ReferenceCategoryError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('references')


class ReferenceCategoryViewSet(viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
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
            return ReferenceCategoryCreateSerializer
        if self.action == 'partial_update':
            return ReferenceCategoryUpdateSerializer
        return ReferenceCategorySerializer

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, ReferenceCategoryNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, ReferenceCategoryNameConflictError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, ReferenceCategoryError):
            return Response({'error': str(exc)}, status=400)
        if isinstance(exc, ReferenceError):
            return Response({'error': str(exc)}, status=400)
        return None

    def list(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.category.view')
        if err is not None:
            return err

        cats = ReferenceCategoryService.list_for_workspace(workspace)
        serializer = ReferenceCategorySerializer(cats, many=True)

        if request.query_params.get('flat') in ('1', 'true', 'yes'):
            return Response(serializer.data)
        return Response({
            'categories': serializer.data,
            'results': serializer.data,
            'count': len(serializer.data),
        })

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.category.create')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cat = ReferenceCategoryService.create(
                workspace=workspace,
                name=serializer.validated_data['name'],
                color=serializer.validated_data.get('color', ''),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar categoria')
            return Response({'error': 'Erro inesperado ao criar a categoria.'}, status=500)

        return Response(ReferenceCategorySerializer(cat).data, status=201)

    def retrieve(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.category.view')
        if err is not None:
            return err
        try:
            cat = ReferenceCategoryService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)
        return Response(ReferenceCategorySerializer(cat).data)

    def partial_update(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.category.rename')
        if err is not None:
            return err
        try:
            cat = ReferenceCategoryService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cat = ReferenceCategoryService.rename(
                category=cat,
                new_name=serializer.validated_data.get('name'),
                color=serializer.validated_data.get('color'),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao renomear categoria')
            return Response({'error': 'Erro inesperado ao renomear a categoria.'}, status=500)
        return Response(ReferenceCategorySerializer(cat).data)

    def destroy(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'references.category.delete')
        if err is not None:
            return err
        try:
            cat = ReferenceCategoryService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)
        try:
            ReferenceCategoryService.delete(cat)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao excluir categoria')
            return Response({'error': 'Erro inesperado ao excluir a categoria.'}, status=500)
        return Response(status=204)