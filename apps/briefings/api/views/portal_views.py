"""
Views do Portal do Cliente.

Autenticação: ClientPortalSession (via ClientPortalMiddleware).

REGRA
-----
Toda requisição aqui é feita por um cliente autenticado no portal.
`request.portal_client` é populado pelo middleware. A view precisa
validar que o briefing pertence a esse cliente.
"""

import logging

from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefings.api.serializers import (
    PortalBriefingSerializer,
    PortalAnswerSubmitSerializer,
    PortalClarificationSerializer,
    PortalReviewRequestSerializer,
)
from apps.briefings.services import BriefingService
from apps.briefings.exceptions import (
    BriefingError,
    BriefingNotFoundError,
    BriefingClosedError,
    BriefingExpiredError,
    BriefingPausedError,
    InvalidQuestionSequenceError,
    InvalidResponseFormatError,
)
from apps.briefings.queries import BriefingQueries
from apps.documents.models import Document

logger = logging.getLogger('briefings')


# =========================================================================
# PERMISSÃO
# =========================================================================

class IsPortalSessionAuthenticated(BasePermission):
    """
    Autoriza requisições do Portal do Cliente.

    Exige que `request.portal_session` exista e seja válida.
    O `ClientPortalMiddleware` do app `clients` a popula.
    """

    def has_permission(self, request, view):
        session = getattr(request, 'portal_session', None)
        if session is None:
            return False
        return session.is_valid()


# =========================================================================
# HELPERS
# =========================================================================

def _resolve_briefing_or_404(briefing_id, request):
    client = getattr(request, 'portal_client', None)
    if client is None:
        return None
    return BriefingQueries.get_for_client(client, briefing_id)


def _handle_error(exc):
    if isinstance(exc, BriefingNotFoundError):
        return Response({'error': str(exc)}, status=404)
    if isinstance(exc, BriefingPausedError):
        return Response({'error': str(exc)}, status=409)
    if isinstance(exc, BriefingClosedError):
        return Response({'error': str(exc)}, status=409)
    if isinstance(exc, BriefingExpiredError):
        return Response({'error': str(exc)}, status=409)
    if isinstance(exc, InvalidQuestionSequenceError):
        return Response({'error': str(exc)}, status=409)
    if isinstance(exc, InvalidResponseFormatError):
        return Response({'error': str(exc)}, status=400)
    if isinstance(exc, BriefingError):
        return Response({'error': str(exc)}, status=400)
    return None


# =========================================================================
# VIEWS
# =========================================================================

class PortalBriefingView(APIView):

    permission_classes = [IsPortalSessionAuthenticated]

    def get(self, request, briefing_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response({'error': 'Briefing não encontrado'}, status=404)

        # Autoexpira se necessário
        briefing.mark_expired_if_needed()

        return Response(PortalBriefingSerializer().to_representation(briefing))


class PortalBriefingAnswerView(APIView):

    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response({'error': 'Briefing não encontrado'}, status=404)

        serializer = PortalAnswerSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolve áudio e anexos como Documents do workspace
        audio_document = None
        if serializer.validated_data.get('audio_document_id'):
            audio_document = Document.objects.filter(
                id=serializer.validated_data['audio_document_id'],
                workspace=briefing.workspace,
            ).first()
            if audio_document is None:
                return Response({'error': 'Áudio não encontrado'}, status=400)

        attachments = []
        attachment_ids = serializer.validated_data.get('attachment_ids') or []
        if attachment_ids:
            attachments = list(Document.objects.filter(
                id__in=attachment_ids,
                workspace=briefing.workspace,
            ))
            if len(attachments) != len(set(str(a) for a in attachment_ids)):
                return Response(
                    {'error': 'Um ou mais anexos não foram encontrados'},
                    status=400,
                )

        try:
            answer = BriefingService.submit_answer(
                briefing_id=briefing.id,
                portal_session=request.portal_session,
                question_id=question_id,
                content_text=serializer.validated_data.get('text', ''),
                audio_document=audio_document,
                attachment_documents=attachments,
            )
        except Exception as exc:
            handled = _handle_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao submeter resposta')
            return Response({'error': 'Erro inesperado.'}, status=500)

        # Recarrega o briefing para refletir progresso
        briefing.refresh_from_db()
        return Response(PortalBriefingSerializer().to_representation(briefing))


class PortalBriefingClarificationView(APIView):

    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response({'error': 'Briefing não encontrado'}, status=404)

        serializer = PortalClarificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BriefingService.request_clarification(
                briefing=briefing,
                portal_session=request.portal_session,
                question_id=question_id,
                message=serializer.validated_data['message'],
            )
        except Exception as exc:
            handled = _handle_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao registrar dúvida')
            return Response({'error': 'Erro inesperado.'}, status=500)

        briefing.refresh_from_db()
        return Response(PortalBriefingSerializer().to_representation(briefing))


class PortalBriefingReviewView(APIView):

    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response({'error': 'Briefing não encontrado'}, status=404)

        serializer = PortalReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BriefingService.request_review(
                briefing=briefing,
                portal_session=request.portal_session,
                question_id=question_id,
                message=serializer.validated_data.get('message', ''),
            )
        except Exception as exc:
            handled = _handle_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao solicitar revisão')
            return Response({'error': 'Erro inesperado.'}, status=500)

        briefing.refresh_from_db()
        return Response(PortalBriefingSerializer().to_representation(briefing))