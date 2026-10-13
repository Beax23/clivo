"""
Pinterest views — placeholder para integração futura.

COMPORTAMENTO
-------------
Enquanto `PinterestService.is_available()` for False, os endpoints
de pins e import respondem **503 Service Unavailable** com uma
mensagem clara. Isso evita que o frontend interprete uma lista vazia
como "conectado, sem pins" — o que seria enganoso.

O endpoint de status continua respondendo 200 normalmente, para que
a UI possa decidir o que mostrar (por exemplo, ocultar o botão).
"""

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status

from apps.references.api.serializers import (
    PinterestImportSerializer,
    ReferenceDetailSerializer,
)
from apps.references.models import ReferenceFolder
from apps.references.services.pinterest_service import (
    PinterestService,
    MSG_NOT_IMPLEMENTED,
)
from apps.references.exceptions import (
    ReferenceError,
    ReferenceInvalidImageError,
)
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('references')


def _current_workspace(request):
    workspace_id = request.session.get('current_workspace_id')
    if not workspace_id:
        return None
    return WorkspaceQueries.get_for_user(workspace_id, request.user)


def _handle_domain_error(exc):
    if isinstance(exc, ReferenceInvalidImageError):
        return Response({'error': str(exc)}, status=400)
    if isinstance(exc, ReferenceError):
        return Response({'error': str(exc)}, status=400)
    return None


class PinterestStatusView(APIView):
    """
    Informa se o usuário tem conta Pinterest conectada e se a
    integração está disponível.

    `connected` reflete apenas o vínculo OAuth (se existir).
    `available` reflete se a integração está implementada.
    O frontend deve usar `available` para decidir se mostra o botão.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        connected = PinterestService.is_connected(request.user)
        available = PinterestService.is_available()

        return Response({
            'connected': connected,
            'available': available,
            'needs_reconnect': False,
            'user_email': None,
            'message': None if available else MSG_NOT_IMPLEMENTED,
        })


class PinterestPinsView(APIView):
    """
    Lista pins do usuário.

    Responde 503 enquanto a integração não estiver disponível.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not PinterestService.is_available():
            return Response(
                {'error': MSG_NOT_IMPLEMENTED, 'available': False},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        workspace = _current_workspace(request)
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        query = request.query_params.get('q', '').strip()
        board_id = request.query_params.get('board_id', '').strip()

        pins = PinterestService.list_pins(
            request.user, query=query, board_id=board_id,
        )
        return Response({'pins': pins, 'boards': []})


class PinterestImportView(APIView):
    """
    Importa pins do Pinterest como References.

    Responde 503 enquanto a integração não estiver disponível.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not PinterestService.is_available():
            return Response(
                {'error': MSG_NOT_IMPLEMENTED, 'available': False},
                status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        workspace = _current_workspace(request)
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        serializer = PinterestImportSerializer(data=request.data)
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

        result = PinterestService.import_pins(
            workspace=workspace,
            user=request.user,
            pins_meta=serializer.validated_data['pins'],
            folder=folder,
        )

        return Response({
            'imported': ReferenceDetailSerializer(result['imported'], many=True).data,
            'errors': result['errors'],
        }, status=201)