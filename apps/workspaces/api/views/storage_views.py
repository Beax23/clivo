"""
StorageView — endpoint de quota de armazenamento do Workspace.

Rota:
    GET /api/workspaces/<public_id>/storage/

Resolução multi-tenant:
    1. `decode_workspace_id(public_id)` → UUID interno
    2. `WorkspaceQueries.get_for_user(uuid, request.user)` → Workspace
       (retorna None se o usuário não é membro ou o workspace está inativo)
    3. `WorkspaceStorageService.get_storage_state(workspace)`

Permissão:
    Qualquer membro do workspace pode consultar. Não exige capability
    específica — consultar o consumo próprio do tenant é parte de
    operar o tenant.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.workspaces.api.serializers.storage_serializers import (
    WorkspaceStorageSerializer,
)
from apps.workspaces.public_id import decode_workspace_id
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.services.storage_service import WorkspaceStorageService

logger = logging.getLogger('workspaces')


class WorkspaceStorageView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, public_id):
        # 1. Resolve o UUID interno
        workspace_id = decode_workspace_id(public_id)
        if workspace_id is None:
            logger.warning(
                'public_id inválido em /storage/: %s', public_id,
            )
            return Response(
                {'error': 'Workspace não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. Resolve o workspace COM isolamento por usuário
        workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            logger.warning(
                'Usuário %s tentou acessar /storage/ de workspace sem '
                'acesso (public_id=%s)',
                request.user.email, public_id,
            )
            return Response(
                {'error': 'Workspace não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Estado de armazenamento
        state = WorkspaceStorageService.get_storage_state(workspace)

        serializer = WorkspaceStorageSerializer(state)
        return Response(serializer.data)