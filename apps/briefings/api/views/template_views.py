"""
BriefingTemplateViewSet — CRUD + actions estruturais.

Capabilities:
    briefings.template.view    → list, retrieve, history
    briefings.template.manage  → create, update, delete, cover,
                                 publish, archive, set_active,
                                 sections & questions CRUD/reorder

NOTAS SOBRE PATHS:
    - COVER usa paths distintos para POST e DELETE (evita colisão
      no DefaultRouter):
          POST   /api/briefing-templates/{id}/cover/
          DELETE /api/briefing-templates/{id}/cover/clear/
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import (
    MultiPartParser, FormParser, JSONParser,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.briefings.models import (
    BriefingSection, BriefingQuestion, BriefingTemplateEvent,
)
from apps.briefings.api.serializers import (
    BriefingTemplateListSerializer,
    BriefingTemplateDetailSerializer,
    BriefingTemplateCreateSerializer,
    BriefingTemplateUpdateSerializer,
    BriefingTemplateSetActiveSerializer,
    BriefingSectionSerializer,
    BriefingSectionCreateSerializer,
    BriefingSectionUpdateSerializer,
    BriefingQuestionSerializer,
    BriefingQuestionCreateSerializer,
    BriefingQuestionUpdateSerializer,
    BriefingTemplateEventSerializer,
    ReorderSerializer,
)
from apps.briefings.services import BriefingTemplateService
from apps.briefings.exceptions import (
    BriefingError,
    BriefingTemplateNotFoundError,
    BriefingTemplateNotDraftError,
    BriefingSectionNotFoundError,
    BriefingQuestionNotFoundError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('briefings')


class BriefingTemplateViewSet(viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
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

    def _get_template_or_404(self, template_id, workspace):
        return BriefingTemplateService.get_or_raise(template_id, workspace)

    @staticmethod
    def _handle_domain_error(exc):
        if isinstance(exc, BriefingTemplateNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, BriefingSectionNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, BriefingQuestionNotFoundError):
            return Response({'error': str(exc)}, status=404)
        if isinstance(exc, BriefingTemplateNotDraftError):
            return Response({'error': str(exc)}, status=409)
        if isinstance(exc, BriefingError):
            return Response({'error': str(exc)}, status=400)
        return None

    # ------------------------------------------------------------------
    # TEMPLATE — CRUD
    # ------------------------------------------------------------------

    def list(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.view')
        if err is not None:
            return err

        qs = workspace.briefing_templates.all().order_by('position', '-created_at')

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        category_id = request.query_params.get('category_id')
        if category_id:
            qs = qs.filter(category_fk_id=category_id)

        is_active = request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif is_active in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return Response(
            BriefingTemplateListSerializer(
                qs, many=True, context={'request': request},
            ).data
        )

    def create(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        serializer = BriefingTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            template = BriefingTemplateService.create_template(
                workspace=workspace,
                name=serializer.validated_data['name'],
                description=serializer.validated_data.get('description', ''),
                category=serializer.validated_data.get('category', ''),
                actor=request.user,
            )
            category_id = serializer.validated_data.get('category_id')
            if category_id:
                template.category_fk_id = category_id
                template.save(update_fields=['category_fk', 'updated_at'])
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao criar template')
            return Response(
                {'error': 'Erro inesperado ao criar o template.'},
                status=500,
            )

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.view')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    def partial_update(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = BriefingTemplateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            template = BriefingTemplateService.update_template(
                template=template,
                name=serializer.validated_data.get('name'),
                description=serializer.validated_data.get('description'),
                category=serializer.validated_data.get('category'),
                actor=request.user,
            )
            if 'category_id' in request.data:
                category_id = serializer.validated_data.get('category_id') or None
                template.category_fk_id = category_id
                template.save(update_fields=['category_fk', 'updated_at'])
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar template')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    def destroy(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
            BriefingTemplateService.delete_template(
                template=template, actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao excluir template')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------------
    # REORDER — TEMPLATES
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BriefingTemplateService.reorder_templates(
                workspace=workspace,
                ordered_ids=serializer.validated_data['ordered_ids'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao reordenar templates')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response({'ok': True})

    # ------------------------------------------------------------------
    # COVER — POST define / DELETE remove (paths distintos)
    #
    # Importante: dois @action com o MESMO url_path colidem no
    # DefaultRouter — o Django registra duas rotas idênticas e
    # resolve para a primeira declarada. Por isso o DELETE usa
    # `cover/clear/`, garantindo paths únicos.
    # ------------------------------------------------------------------

    @action(
        detail=True,
        methods=['post'],
        url_path='cover',
        url_name='template-cover-set',
        parser_classes=[MultiPartParser, FormParser],
    )
    def set_cover(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        uploaded = request.FILES.get('cover') or request.FILES.get('file')
        if uploaded is None:
            return Response({'error': 'Nenhuma imagem enviada'}, status=400)

        try:
            template = BriefingTemplateService.set_cover(
                template=template,
                uploaded_file=uploaded,
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao salvar capa')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    @action(
        detail=True,
        methods=['delete'],
        url_path='cover/clear',
        url_name='template-cover-clear',
    )
    def clear_cover(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
            template = BriefingTemplateService.clear_cover(
                template=template, actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao remover capa')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # TEMPLATE — publish / archive / active
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
            template = BriefingTemplateService.publish_template(
                template=template, actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao publicar template')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
            template = BriefingTemplateService.archive_template(
                template=template, actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao arquivar template')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    @action(detail=True, methods=['post'], url_path='set-active')
    def set_active(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = BriefingTemplateSetActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            template = BriefingTemplateService.set_active(
                template=template,
                is_active=serializer.validated_data['is_active'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao alterar ativo/inativo')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # TEMPLATE — histórico
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.view')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        qs = (
            BriefingTemplateEvent.objects
            .filter(template=template)
            .select_related('user')
            .order_by('-created_at')[:200]
        )
        return Response(BriefingTemplateEventSerializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # SECTIONS
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='sections')
    def add_section(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = BriefingSectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            section = BriefingTemplateService.add_section(
                template=template,
                title=serializer.validated_data['title'],
                description=serializer.validated_data.get('description', ''),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao adicionar sessão')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingSectionSerializer(section).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['patch', 'delete'],
        url_path=r'sections/(?P<section_id>[^/.]+)',
    )
    def section_detail(self, request, id=None, section_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        section = BriefingSection.objects.filter(
            id=section_id, template=template,
        ).first()
        if section is None:
            return Response({'error': 'Sessão não encontrada'}, status=404)

        if request.method == 'DELETE':
            try:
                BriefingTemplateService.delete_section(
                    section=section, actor=request.user,
                )
            except Exception as exc:
                handled = self._handle_domain_error(exc)
                if handled is not None:
                    return handled
                logger.exception('Erro ao excluir sessão')
                return Response({'error': 'Erro inesperado.'}, status=500)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = BriefingSectionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            section = BriefingTemplateService.update_section(
                section=section,
                title=serializer.validated_data.get('title'),
                description=serializer.validated_data.get('description'),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar sessão')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingSectionSerializer(section).data)

    @action(detail=True, methods=['post'], url_path='sections/reorder')
    def reorder_sections(self, request, id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BriefingTemplateService.reorder_sections(
                template=template,
                ordered_ids=serializer.validated_data['ordered_ids'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao reordenar sessões')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingTemplateDetailSerializer(
                template, context={'request': request},
            ).data
        )

    # ------------------------------------------------------------------
    # QUESTIONS
    # ------------------------------------------------------------------

    @action(
        detail=True, methods=['post'],
        url_path=r'sections/(?P<section_id>[^/.]+)/questions',
    )
    def add_question(self, request, id=None, section_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        section = BriefingSection.objects.filter(
            id=section_id, template=template,
        ).first()
        if section is None:
            return Response({'error': 'Sessão não encontrada'}, status=404)

        serializer = BriefingQuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            question = BriefingTemplateService.add_question(
                section=section,
                text=serializer.validated_data['text'],
                instructions=serializer.validated_data.get('instructions', ''),
                question_type=serializer.validated_data.get(
                    'question_type', BriefingQuestion.QUESTION_TYPE_TEXT,
                ),
                allowed_response_formats=serializer.validated_data.get(
                    'allowed_response_formats',
                ),
                options=serializer.validated_data.get('options'),
                is_required=serializer.validated_data.get('is_required', True),
                reference_document_ids=serializer.validated_data.get(
                    'reference_document_ids', [],
                ),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao adicionar pergunta')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingQuestionSerializer(
                question, context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['patch', 'delete'],
        url_path=r'questions/(?P<question_id>[^/.]+)',
    )
    def question_detail(self, request, id=None, question_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        question = BriefingQuestion.objects.filter(
            id=question_id, section__template=template,
        ).first()
        if question is None:
            return Response({'error': 'Pergunta não encontrada'}, status=404)

        if request.method == 'DELETE':
            try:
                BriefingTemplateService.delete_question(
                    question=question, actor=request.user,
                )
            except Exception as exc:
                handled = self._handle_domain_error(exc)
                if handled is not None:
                    return handled
                logger.exception('Erro ao excluir pergunta')
                return Response({'error': 'Erro inesperado.'}, status=500)
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = BriefingQuestionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            question = BriefingTemplateService.update_question(
                question=question,
                text=serializer.validated_data.get('text'),
                instructions=serializer.validated_data.get('instructions'),
                question_type=serializer.validated_data.get('question_type'),
                allowed_response_formats=serializer.validated_data.get(
                    'allowed_response_formats',
                ),
                options=serializer.validated_data.get('options'),
                is_required=serializer.validated_data.get('is_required'),
                reference_document_ids=serializer.validated_data.get(
                    'reference_document_ids',
                ),
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao editar pergunta')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(
            BriefingQuestionSerializer(
                question, context={'request': request},
            ).data
        )

    @action(
        detail=True, methods=['post'],
        url_path=r'sections/(?P<section_id>[^/.]+)/questions/reorder',
    )
    def reorder_questions(self, request, id=None, section_id=None):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)
        err = self._require_capability(workspace, 'briefings.template.manage')
        if err is not None:
            return err

        try:
            template = self._get_template_or_404(id, workspace)
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            return Response({'error': 'Erro'}, status=500)

        section = BriefingSection.objects.filter(
            id=section_id, template=template,
        ).first()
        if section is None:
            return Response({'error': 'Sessão não encontrada'}, status=404)

        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            BriefingTemplateService.reorder_questions(
                section=section,
                ordered_ids=serializer.validated_data['ordered_ids'],
                actor=request.user,
            )
        except Exception as exc:
            handled = self._handle_domain_error(exc)
            if handled is not None:
                return handled
            logger.exception('Erro ao reordenar perguntas')
            return Response({'error': 'Erro inesperado.'}, status=500)

        return Response(BriefingSectionSerializer(section).data)