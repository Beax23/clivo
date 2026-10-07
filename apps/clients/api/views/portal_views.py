"""
ClientPortalViewSet — endpoints consumidos pelo PRÓPRIO cliente.

Autenticação:
    ClientPortalSession (via middleware), NÃO Workspace login.

Capabilities:
    NÃO usa capability de arquiteto. O token do Portal é a autorização.
    O middleware já validou a sessão; a view só confia em
    `request.portal_client`.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.clients.permissions import IsPortalSessionAuthenticated
from apps.clients.api.serializers.portal_serializers import (
    PortalContextSerializer,
    PortalFeedbackSerializer,
    PortalFeedbackCreateSerializer,
)
from apps.clients.services import PortalService


class ClientPortalViewSet(viewsets.ViewSet):
    """
    Endpoints do Portal do Cliente.

    Todas as rotas exigem `request.portal_session` válido
    (populado pelo ClientPortalMiddleware).
    """

    permission_classes = [IsPortalSessionAuthenticated]

    # ------------------------------------------------------------------
    # CONTEXTO
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Retorna o contexto público do cliente."""
        client = request.portal_client
        data = {
            'public_code': client.public_code,
            'name': client.name,
            'context': client.context or {},
        }
        return Response(PortalContextSerializer(data).data)

    # ------------------------------------------------------------------
    # FEEDBACK
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='feedback')
    def submit_feedback(self, request):
        """
        Cliente envia feedback de experiência do Portal.

        Autenticação: ClientPortalSession.
        NÃO exige capability de arquiteto.
        """
        client = request.portal_client

        serializer = PortalFeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feedback = PortalService.submit_feedback(
            client=client,
            kind=serializer.validated_data['kind'],
            rating=serializer.validated_data.get('rating', ''),
            message=serializer.validated_data.get('message', ''),
            page=serializer.validated_data.get('page', ''),
            request=request,
        )

        return Response(
            PortalFeedbackSerializer(feedback).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # CONFIRMAÇÃO / EDIÇÃO DE CONTEXTO
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='context/confirm')
    def context_confirm(self, request):
        """Cliente confirma que o contexto publicado está correto."""
        client = request.portal_client
        from apps.clients.events import ClientEventEmitter
        ClientEventEmitter.portal_context_confirmed(
            client=client, request=request,
        )
        return Response({'detail': 'Contexto confirmado'})

    @action(detail=False, methods=['post'], url_path='context/edit')
    def context_edit(self, request):
        """
        Cliente propõe uma correção ao contexto publicado.

        V1: registra apenas o evento (a correção real pertence a
        Intelligence). Não sobrescreve `Client.context` diretamente.
        """
        client = request.portal_client
        from apps.clients.events import ClientEventEmitter
        ClientEventEmitter.portal_context_edited(
            client=client, request=request,
        )
        return Response({'detail': 'Correção registrada'})