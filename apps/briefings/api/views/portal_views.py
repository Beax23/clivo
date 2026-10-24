"""
Views do Portal do Cliente.

Autenticação: ClientPortalSession (via ClientPortalMiddleware).
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefings.api.serializers import (
    PortalBriefingSerializer,
    PortalBriefingListSerializer,
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


class IsPortalSessionAuthenticated(BasePermission):
    def has_permission(self, request, view):
        session = getattr(request, 'portal_session', None)
        if session is None:
            return False
        return session.is_valid()


def _resolve_briefing_or_404(briefing_id, request):
    client = getattr(request, 'portal_client', None)
    if client is None:
        return None
    return BriefingQueries.get_for_client(client, briefing_id)


def _handle_error(exc, briefing=None):
    if isinstance(exc, BriefingNotFoundError):
        return Response(
            {'error': str(exc), 'code': 'not_found'}, status=404,
        )
    if isinstance(exc, BriefingPausedError):
        return Response(
            {'error': str(exc), 'code': 'paused'}, status=409,
        )
    if isinstance(exc, BriefingClosedError):
        return Response(
            {'error': str(exc), 'code': 'cancelled'}, status=409,
        )
    if isinstance(exc, BriefingExpiredError):
        return Response(
            {'error': str(exc), 'code': 'cancelled'}, status=409,
        )
    if isinstance(exc, InvalidQuestionSequenceError):
        expected_id = None
        if briefing is not None:
            try:
                next_q = BriefingService.get_next_eligible_question(briefing)
                if next_q:
                    expected_id = str(next_q['id'])
            except Exception:
                pass
        return Response(
            {
                'error': str(exc),
                'code': 'out_of_sequence',
                'expected_question_id': expected_id,
            },
            status=409,
        )
    if isinstance(exc, InvalidResponseFormatError):
        return Response(
            {'error': str(exc), 'code': 'invalid_format'}, status=400,
        )
    if isinstance(exc, BriefingError):
        return Response(
            {'error': str(exc), 'code': 'briefing_error'}, status=400,
        )
    return None


def _absolute_url(request, url):
    if not url:
        return ''
    if url.startswith(('http://', 'https://')):
        return url
    if request is not None:
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url
    return url


def _briefing_cover_url(briefing, request):
    template = briefing.template
    if template is None:
        return ''
    if not template.cover:
        return ''
    try:
        url = template.cover.url
    except Exception:
        return ''
    return _absolute_url(request, url)


def _serialize(briefing, request):
    return PortalBriefingSerializer(
        context={'request': request},
    ).to_representation(briefing)


class PortalBriefingListView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def get(self, request):
        client = getattr(request, 'portal_client', None)
        if client is None:
            return Response({'error': 'Sessão inválida'}, status=401)

        qs = BriefingQueries.list_for_client(client)
        for b in qs:
            b.mark_expired_if_needed()
        qs = BriefingQueries.list_for_client(client)

        data = []
        for b in qs:
            item = PortalBriefingListSerializer().to_representation(b)
            item['cover_url'] = _briefing_cover_url(b, request)
            data.append(item)
        return Response(data)


class PortalBriefingView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def get(self, request, briefing_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

        briefing.mark_expired_if_needed()

        try:
            BriefingService.sync_snapshot_references(briefing)
        except Exception:
            logger.exception(
                'Falha ao sincronizar referências do snapshot '
                '(briefing=%s)', briefing.id,
            )

        if briefing.first_opened_at is None:
            briefing.first_opened_at = timezone.now()
            briefing.save(update_fields=[
                'first_opened_at', 'updated_at',
            ])

        return Response(_serialize(briefing, request))


class PortalBriefingStartView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

        try:
            BriefingService.mark_intro_seen(briefing)
        except Exception:
            logger.exception(
                'Falha ao marcar intro como vista (briefing=%s)',
                briefing.id,
            )

        briefing.refresh_from_db()
        return Response(_serialize(briefing, request))


class PortalBriefingAnswerView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

        if briefing.first_opened_at is None:
            briefing.first_opened_at = timezone.now()
            briefing.save(update_fields=[
                'first_opened_at', 'updated_at',
            ])

        try:
            BriefingService.sync_snapshot_references(briefing)
        except Exception:
            logger.exception(
                'Falha ao sincronizar referências antes de responder '
                '(briefing=%s)', briefing.id,
            )

        serializer = PortalAnswerSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        audio_document = None
        audio_document_id = serializer.validated_data.get('audio_document_id')
        if audio_document_id:
            audio_document = Document.objects.filter(
                id=audio_document_id,
                workspace=briefing.workspace,
            ).first()
            if audio_document is None:
                return Response(
                    {
                        'error': 'Áudio não encontrado',
                        'code': 'audio_not_found',
                    },
                    status=400,
                )
            mime = getattr(audio_document, 'mime_type', '') or ''
            if mime and not mime.startswith('audio/'):
                return Response(
                    {
                        'error': 'O arquivo enviado não é um áudio.',
                        'code': 'not_audio',
                    },
                    status=400,
                )

        attachments = []
        attachment_ids = serializer.validated_data.get('attachment_ids') or []
        if attachment_ids:
            attachments = list(Document.objects.filter(
                id__in=attachment_ids,
                workspace=briefing.workspace,
            ))
            expected = set(str(a) for a in attachment_ids)
            found = set(str(a.id) for a in attachments)
            if expected != found:
                return Response(
                    {
                        'error': 'Uma ou mais imagens não foram encontradas.',
                        'code': 'attachments_not_found',
                    },
                    status=400,
                )
            for doc in attachments:
                mime = getattr(doc, 'mime_type', '') or ''
                if mime and not mime.startswith('image/'):
                    return Response(
                        {
                            'error': 'Um dos arquivos não é uma imagem.',
                            'code': 'not_image',
                        },
                        status=400,
                    )

        try:
            BriefingService.submit_answer(
                briefing_id=briefing.id,
                portal_session=request.portal_session,
                question_id=question_id,
                content_text=serializer.validated_data.get('text', ''),
                audio_document=audio_document,
                attachment_documents=attachments,
            )
        except Exception as exc:
            handled = _handle_error(exc, briefing=briefing)
            if handled is not None:
                return handled
            logger.exception('Erro inesperado ao submeter resposta')
            return Response(
                {'error': 'Erro inesperado.', 'code': 'internal'},
                status=500,
            )

        briefing.refresh_from_db()
        return Response(_serialize(briefing, request))


class PortalBriefingClarificationView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

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
            handled = _handle_error(exc, briefing=briefing)
            if handled is not None:
                return handled
            logger.exception('Erro ao registrar dúvida')
            return Response(
                {'error': 'Erro inesperado.', 'code': 'internal'},
                status=500,
            )

        briefing.refresh_from_db()
        return Response(_serialize(briefing, request))


class PortalBriefingReviewView(APIView):
    permission_classes = [IsPortalSessionAuthenticated]

    def post(self, request, briefing_id=None, question_id=None):
        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

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
            handled = _handle_error(exc, briefing=briefing)
            if handled is not None:
                return handled
            logger.exception('Erro ao solicitar revisão')
            return Response(
                {'error': 'Erro inesperado.', 'code': 'internal'},
                status=500,
            )

        briefing.refresh_from_db()
        return Response(_serialize(briefing, request))


class PortalBriefingExportPdfView(APIView):
    """
    GET /api/portal/briefings/<id>/export-pdf/

    Gera o PDF BRUTO do briefing na visão do CLIENTE.
    Devolve a mensagem real de erro se o WeasyPrint falhar.
    """
    permission_classes = [IsPortalSessionAuthenticated]

    def get(self, request, briefing_id=None):
        from io import BytesIO
        from django.http import FileResponse
        from apps.briefings.services.export_service import (
            BriefingExportService,
        )

        briefing = _resolve_briefing_or_404(briefing_id, request)
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado', 'code': 'not_found'},
                status=404,
            )

        try:
            pdf_bytes, filename = BriefingExportService.render_pdf(
                briefing, request=request, mode='client',
            )
        except RuntimeError as exc:
            logger.warning(
                'Falha ao gerar PDF do cliente (briefing=%s): %s',
                briefing.id, exc,
            )
            return Response(
                {'error': str(exc)},
                status=500,
            )
        except Exception as exc:
            logger.exception(
                'Falha inesperada ao gerar PDF do cliente '
                '(briefing=%s)', briefing.id,
            )
            return Response(
                {'error': f'Erro inesperado: {exc}'},
                status=500,
            )

        return FileResponse(
            BytesIO(pdf_bytes),
            as_attachment=True,
            filename=filename,
            content_type='application/pdf',
        )