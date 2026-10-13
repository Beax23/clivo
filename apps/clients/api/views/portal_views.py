"""
ClientPortalViewSet — endpoints consumidos pelo PRÓPRIO cliente.

Autenticação:
    Cliente abre /portal/ e digita o `public_code`.
    POST /api/portal/login/ valida e cria uma ClientPortalSession.
    O cookie `clivo_portal` guarda o token cru da sessão.
    O middleware `ClientPortalMiddleware` resolve a sessão nas
    requisições seguintes.

Endpoints:
    POST   /api/portal/login/         → autentica por código
    POST   /api/portal/logout/        → encerra a sessão
    GET    /api/portal/me/            → dados do cliente
    POST   /api/portal/feedback/      → feedback do cliente
    POST   /api/portal/context/confirm
    POST   /api/portal/context/edit
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.clients.permissions import IsPortalSessionAuthenticated
from apps.clients.api.serializers.portal_serializers import (
    PortalContextSerializer,
    PortalFeedbackSerializer,
    PortalFeedbackCreateSerializer,
)
from apps.clients.services import PortalService
from apps.clients.models import Client, ClientPortalSession
from apps.clients.exceptions import (
    PortalSessionError,
    PortalSessionExpiredError,
)

logger = logging.getLogger('clients')

PORTAL_COOKIE_NAME = 'clivo_portal'
PORTAL_SESSION_TTL_HOURS = 8


class ClientPortalLoginView(APIView):
    """
    Autentica o cliente com o `public_code`.

    POST /api/portal/login/
        body: { "code": "CLI-X7K92P" }

    Resposta de sucesso:
        {
            "public_code": "CLI-X7K92P",
            "name": "...",
            "context": {...}
        }

    Efeito colateral:
        Seta o cookie `clivo_portal` (HttpOnly) com o token cru
        da sessão. Esse cookie é resolvido pelo ClientPortalMiddleware.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        raw_code = (request.data.get('code') or '').strip().upper()
        if not raw_code:
            return Response(
                {'error': 'Informe o código de acesso.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Aceita com ou sem prefixo
        if not raw_code.startswith('CLI-'):
            raw_code = 'CLI-' + raw_code.lstrip('CLI-')

        try:
            client = Client.objects.select_related('workspace').get(
                public_code=raw_code
            )
        except Client.DoesNotExist:
            return Response(
                {'error': 'Código não encontrado. Verifique e tente novamente.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if client.status != Client.STATUS_ACTIVE:
            return Response(
                {'error': 'Este acesso está inativo.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Cria a sessão e retorna o token cru para o cookie
        session, raw_token = ClientPortalSession.issue(
            client=client,
            ttl_minutes=PORTAL_SESSION_TTL_HOURS * 60,
        )

        # Registra o acesso
        PortalService._register_access(session, request)

        response = Response({
            'public_code': client.public_code,
            'name': client.name,
            'context': client.context or {},
        })

        secure = not settings.DEBUG
        response.set_cookie(
            key=PORTAL_COOKIE_NAME,
            value=raw_token,
            max_age=PORTAL_SESSION_TTL_HOURS * 60 * 60,
            httponly=True,
            secure=secure,
            samesite='Lax',
            path='/',
        )
        return response


class ClientPortalViewSet(viewsets.ViewSet):
    """
    Endpoints do Portal (exigem cookie de sessão válida).
    """

    permission_classes = [IsPortalSessionAuthenticated]

    # ------------------------------------------------------------------
    # LOGOUT
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='logout')
    def logout(self, request):
        session = getattr(request, 'portal_session', None)
        if session:
            session.revoke()

        response = Response({'detail': 'Sessão encerrada.'})
        response.delete_cookie(PORTAL_COOKIE_NAME, path='/')
        return response

    # ------------------------------------------------------------------
    # ME
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
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
    # CONTEXTO
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='context/confirm')
    def context_confirm(self, request):
        client = request.portal_client
        from apps.clients.events import ClientEventEmitter
        ClientEventEmitter.portal_context_confirmed(
            client=client, request=request,
        )
        return Response({'detail': 'Contexto confirmado'})

    @action(detail=False, methods=['post'], url_path='context/edit')
    def context_edit(self, request):
        client = request.portal_client
        from apps.clients.events import ClientEventEmitter
        ClientEventEmitter.portal_context_edited(
            client=client, request=request,
        )
        return Response({'detail': 'Correção registrada'})