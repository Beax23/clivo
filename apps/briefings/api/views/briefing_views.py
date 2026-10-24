"""
BriefingViewSet — CRUD + ações do arquiteto sobre execuções.
"""

import logging

from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.briefings.api.serializers import (
    BriefingListSerializer,
    BriefingDetailSerializer,
    BriefingCreateSerializer,
    BriefingReopenSerializer,
    BriefingEventSerializer,
    BriefingNoteSerializer,
    BriefingNoteCreateSerializer,
    BriefingQuestionInstanceSerializer,
    BriefingQuestionInstanceCreateSerializer,
    BriefingQuestionInstanceUpdateSerializer,
    BriefingTemplateVersionSerializer,
)
from apps.briefings.services import (
    BriefingService,
    BriefingTemplateService,
    BriefingNoteService,
    BriefingSendService,
    BriefingQuestionInstanceService,
    BriefingTemplateVersionService,
)
from apps.briefings.services.export_service import BriefingExportService
from apps.briefings.exceptions import (
    BriefingError,
    BriefingNotFoundError,
    BriefingReopenError,
    BriefingClosedError,
    BriefingExpiredError,
    BriefingPausedError,
    BriefingNoteNotFoundError,
)
from apps.clients.models import Client
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('briefings')


class BriefingViewSet(viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

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

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, BriefingNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, BriefingReopenError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, BriefingClosedError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, BriefingExpiredError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, BriefingPausedError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, BriefingNoteNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, BriefingError):
            return Response({'error': str(exc)}, status=400)
        return None

    def list(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.view')
        if err is not None:
            return err

        status_filter = request.query_params.get('status')
        client_id = request.query_params.get('client')

        qs = workspace.briefings.select_related(
            'client', 'template', 'template_version',
        ).order_by('-created_at')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if client_id:
            qs = qs.filter(client_id=client_id)

        return Response(BriefingListSerializer(qs, many=True).data)

    def create(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.start')
        if err is not None:
            return err

        serializer = BriefingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            template = BriefingTemplateService.get_or_raise(
                serializer.validated_data['template_id'], workspace,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Template não encontrado'}, status=404)

        client_id = serializer.validated_data['client_id']
        client = Client.objects.filter(
            id=client_id, workspace=workspace,
        ).first()
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        try:
            briefing = BriefingService.create_briefing(
                template=template,
                client=client,
                workspace=workspace,
                actor=request.user,
                expires_at=serializer.validated_data.get('expires_at'),
                title=serializer.validated_data.get('title') or None,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar briefing')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingDetailSerializer(briefing).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.view')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        return Response(BriefingDetailSerializer(briefing).data)

    def destroy(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.delete')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        briefing.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='pause')
    def pause(self, request, id=None):
        return self._simple_action(id, request, 'pause')

    @action(detail=True, methods=['post'], url_path='resume')
    def resume(self, request, id=None):
        return self._simple_action(id, request, 'resume')

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, id=None):
        return self._simple_action(id, request, 'close')

    def _simple_action(self, briefing_id, request, name):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.review')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(briefing_id, workspace)
            method = getattr(BriefingService, name)
            briefing = method(briefing=briefing, actor=request.user)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro em ação %s', name)
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingDetailSerializer(briefing).data)

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.review')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = BriefingReopenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            briefing = BriefingService.reopen(
                briefing=briefing,
                actor=request.user,
                new_expires_at=serializer.validated_data.get('new_expires_at'),
                reason=serializer.validated_data.get('reason', ''),
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao reabrir briefing')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingDetailSerializer(briefing).data)

    @action(detail=True, methods=['get'], url_path='events')
    def events(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.view')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        qs = briefing.events.select_related(
            'user', 'portal_session',
        ).order_by('-created_at')[:500]
        return Response(BriefingEventSerializer(qs, many=True).data)

    @action(detail=True, methods=['get', 'post'], url_path='notes')
    def notes(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        if request.method == 'GET':
            err = self._require_capability(workspace, 'briefings.note.view')
            if err is not None:
                return err

            try:
                briefing = BriefingService.get_or_raise(id, workspace)
            except Exception as exc:
                handled = self._handle_domain_error(exc)
                if handled is not None:
                    return handled
                return Response({'error': 'Erro'}, status=500)

            qs = BriefingNoteService.list_for_briefing(briefing)
            return Response(BriefingNoteSerializer(qs, many=True).data)

        err = self._require_capability(workspace, 'briefings.note.manage')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = BriefingNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            note = BriefingNoteService.create_note(
                briefing=briefing,
                author=request.user,
                content=serializer.validated_data['content'],
                question_id=serializer.validated_data.get('question_id'),
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar anotação')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['patch', 'delete'],
        url_path=r'notes/(?P<note_id>[^/.]+)',
    )
    def note_detail(self, request, id=None, note_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.note.manage')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
            note = BriefingNoteService.get_or_raise(note_id, briefing)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        if request.method == 'DELETE':
            BriefingNoteService.delete_note(note=note)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = BriefingNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            note = BriefingNoteService.update_note(
                note=note,
                author=request.user,
                content=serializer.validated_data['content'],
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar anotação')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingNoteSerializer(note).data)

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='custom-questions',
    )
    def custom_questions(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        if request.method == 'GET':
            err = self._require_capability(workspace, 'briefings.briefing.view')
            if err is not None:
                return err
        else:
            err = self._require_capability(workspace, 'briefings.briefing.review')
            if err is not None:
                return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        if request.method == 'GET':
            qs = BriefingQuestionInstanceService.list_for_briefing(briefing)
            return Response(
                BriefingQuestionInstanceSerializer(qs, many=True).data
            )

        serializer = BriefingQuestionInstanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            instance = BriefingQuestionInstanceService.add_custom_question(
                briefing=briefing,
                section_ref=serializer.validated_data['section_ref'],
                text=serializer.validated_data['text'],
                instructions=serializer.validated_data.get('instructions', ''),
                question_type=serializer.validated_data.get(
                    'question_type', 'text',
                ),
                allowed_response_formats=serializer.validated_data.get(
                    'allowed_response_formats',
                ),
                options=serializer.validated_data.get('options'),
                is_required=serializer.validated_data.get('is_required', True),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar pergunta exclusiva')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingQuestionInstanceSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['patch', 'delete'],
        url_path=r'custom-questions/(?P<instance_id>[^/.]+)',
    )
    def custom_question_detail(self, request, id=None, instance_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.review')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        try:
            instance = BriefingQuestionInstanceService.get_or_raise(
                instance_id, briefing,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        if request.method == 'DELETE':
            try:
                BriefingQuestionInstanceService.remove_custom_question(
                    instance=instance, actor=request.user,
                )
            except Exception as exc:
                handled = self._handle_domain_error(exc)
                if handled is not None:
                    return handled
                logger.exception('Erro ao remover pergunta exclusiva')
                return Response({'error': 'Erro inesperado.'}, status=500)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = BriefingQuestionInstanceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            instance = BriefingQuestionInstanceService.update_custom_question(
                instance=instance,
                text=serializer.validated_data.get('text'),
                instructions=serializer.validated_data.get('instructions'),
                question_type=serializer.validated_data.get('question_type'),
                allowed_response_formats=serializer.validated_data.get(
                    'allowed_response_formats',
                ),
                options=serializer.validated_data.get('options'),
                is_required=serializer.validated_data.get('is_required'),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar pergunta exclusiva')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingQuestionInstanceSerializer(instance).data)

    @action(
        detail=True,
        methods=['post'],
        url_path='promote-to-template-version',
    )
    def promote_to_template_version(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        if briefing.template_id is None:
            return Response(
                {'error': 'Este briefing não tem modelo de origem. '
                          'Não é possível criar uma nova versão.'},
                status=400,
            )

        include_custom = request.data.get('include_custom_questions', True)

        try:
            version = (
                BriefingTemplateVersionService.create_draft_from_briefing(
                    briefing=briefing,
                    actor=request.user,
                    include_custom_questions=bool(include_custom),
                    template=briefing.template,
                )
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao promover briefing a versão')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.briefing.export')
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        try:
            pdf_bytes, filename = BriefingExportService.render_pdf(
                briefing, request=request, mode='architect',
            )
        except RuntimeError as exc:
            logger.warning(
                'Falha ao gerar PDF do arquiteto (briefing=%s): %s',
                briefing.id, exc,
            )
            return Response({'error': str(exc)}, status=500)
        except Exception as exc:
            logger.exception('Falha inesperada ao gerar PDF do arquiteto')
            return Response(
                {'error': f'Erro inesperado: {exc}'},
                status=500,
            )

        from io import BytesIO
        return FileResponse(
            BytesIO(pdf_bytes),
            as_attachment=True,
            filename=filename,
            content_type='application/pdf',
        )

    @action(detail=True, methods=['post'], url_path='send-to-client')
    def send_to_client(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(
            workspace, 'briefings.briefing.send_to_client',
        )
        if err is not None:
            return err

        try:
            briefing = BriefingService.get_or_raise(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        to_email = (request.data.get('to_email') or '').strip() or None
        message = (request.data.get('message') or '').strip()

        try:
            result = BriefingSendService.send_to_client(
                briefing=briefing,
                actor=request.user,
                to_email=to_email,
                message=message,
                request=request,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao enviar briefing manualmente')
            return Response(
                {'error': 'Falha ao enviar o briefing.'},
                status=500,
            )

        return Response(result, status=status.HTTP_200_OK)