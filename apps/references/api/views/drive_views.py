"""
Google Drive views — listagem e importação de imagens.

CAPABILITIES
------------
    references.reference.upload  → DriveFilesView (listar é preparação
                                    para importar)
    references.reference.upload  → DriveImportView

O Drive é uma FONTE para `references.reference.upload`. Quem pode
importar do Drive pode subir arquivo do computador. Quem não pode
importar não deveria nem listar, já que o único uso da listagem é
selecionar para importar.
"""

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status

from apps.references.api.serializers import (
    GDriveImportSerializer,
    ReferenceDetailSerializer,
)
from apps.references.models import ReferenceFolder
from apps.references.services.gdrive_service import GDriveService
from apps.references.exceptions import (
    ReferenceError,
    ReferenceInvalidImageError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('references')


def _current_workspace(request):
    workspace_id = request.session.get('current_workspace_id')
    if not workspace_id:
        return None
    return WorkspaceQueries.get_for_user(workspace_id, request.user)


def _require_capability(request, workspace, capability_code):
    """
    Retorna None se ok, ou Response de erro (403/400).

    Mesmo padrão de ReferenceViewSet.
    """
    if workspace is None:
        return Response(
            {'error': 'Nenhum workspace ativo'},
            status=http_status.HTTP_400_BAD_REQUEST,
        )

    membership = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=request.user,
    ).select_related('governance').first()

    if membership is None:
        return Response(
            {'error': 'Você não é membro deste Workspace'},
            status=http_status.HTTP_403_FORBIDDEN,
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
            status=http_status.HTTP_403_FORBIDDEN,
        )
    return None


def _handle_domain_error(exc):
    if isinstance(exc, ReferenceInvalidImageError):
        return Response({'error': str(exc)}, status=400)
    if isinstance(exc, ReferenceError):
        return Response({'error': str(exc)}, status=400)
    return None


class DriveStatusView(APIView):
    """
    Informa o status da conexão Google do usuário.

    NÃO exige capability: é diagnóstico. O frontend precisa saber
    o status para decidir o que mostrar na interface. Não expõe
    dados de outro workspace.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(GDriveService.connection_status(request.user))


class DriveFilesView(APIView):
    """
    Lista imagens do Drive do usuário.

    Exige capability de upload — listar é o passo anterior a
    importar; quem não pode importar, não precisa listar.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = _current_workspace(request)
        err = _require_capability(request, workspace, 'references.reference.upload')
        if err is not None:
            return err

        query = request.query_params.get('q', '').strip()

        try:
            files = GDriveService.list_files(request.user, query=query)
        except Exception as exc:
            handled = _handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao listar arquivos do Drive')
            return Response(
                {'error': 'Erro ao listar arquivos do Google Drive.'},
                status=500,
            )

        return Response({'files': files})


class DriveImportView(APIView):
    """
    Importa arquivos do Drive como References.

    Exige capability de upload.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        workspace = _current_workspace(request)
        err = _require_capability(request, workspace, 'references.reference.upload')
        if err is not None:
            return err

        serializer = GDriveImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        folder = None
        folder_id = serializer.validated_data.get('folder_id')
        if folder_id:
            folder = ReferenceFolder.objects.filter(
                id=folder_id, workspace=workspace
            ).first()
            if folder is None:
                return Response(
                    {'error': 'Pasta não encontrada neste workspace.'},
                    status=400,
                )

        try:
            result = GDriveService.import_files(
                workspace=workspace,
                user=request.user,
                files_meta=serializer.validated_data['files'],
                folder=folder,
            )
        except Exception as exc:
            handled = _handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao importar do Drive')
            return Response(
                {'error': 'Erro inesperado ao importar do Google Drive.'},
                status=500,
            )

        return Response({
            'imported': ReferenceDetailSerializer(result['imported'], many=True).data,
            'errors': result['errors'],
        }, status=201)