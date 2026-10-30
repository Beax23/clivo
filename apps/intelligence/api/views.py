"""
Views da API de Inteligência.

Endpoints:
    GET  /api/intelligence/mesa/
    GET  /api/intelligence/clientes/<client_id>/
    GET  /api/intelligence/briefings/<briefing_id>/relatorio/
    GET  /api/intelligence/tags/
    GET  /api/intelligence/tags/<id>/
    PATCH /api/intelligence/tags/<id>/
    POST /api/intelligence/briefings/<id>/reanalyze/
    POST /api/intelligence/clients/<id>/reanalyze/
    GET  /api/intelligence/jobs/<job_id>/status/

Autorização:
    - Usuário autenticado.
    - Membro do workspace (via `user_has_capability` do módulo
      `workspaces`, que é o único ponto de autorização cross-app).
    - Capability necessária: `intelligence.insight.view` para leitura
      e reanálise; `intelligence.tag.manage` para transição de tag.
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.intelligence.api.serializers import (
    ContainerPayloadSerializer,
    InsightItemSerializer,
    InsightTagHistorySerializer,
    TagTransitionSerializer,
)
from apps.intelligence.models import (
    AnalysisJob, InsightEvent, InsightItem,
)
from apps.intelligence.services import (
    ContainerService,
    IngestService,
    TagService,
    InvalidTagTransitionError,
)
from apps.workspaces.permissions.workspace_permissions import (
    user_has_capability,
)
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('intelligence')


def _resolve_workspace(request):
    ws_id = request.session.get('current_workspace_id')
    if not ws_id:
        return None
    return WorkspaceQueries.get_for_user(ws_id, request.user)


def _require(workspace, user, capability: str):
    if workspace is None:
        return False, Response(
            {'error': 'Nenhum workspace ativo'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user_has_capability(workspace, user, capability):
        return False, Response(
            {'error': f'Capability necessária: {capability}'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return True, None


class MesaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        client = None
        client_id = request.query_params.get('client')
        if client_id:
            from apps.clients.models import Client
            client = Client.objects.filter(
                id=client_id, workspace=workspace,
            ).first()
            if client is None:
                return Response(
                    {'error': 'Cliente não encontrado'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        include_stale = request.query_params.get('include_stale') == '1'
        payload = ContainerService.build_mesa(
            workspace=workspace,
            client=client,
            include_stale=include_stale,
        )
        serializer = ContainerPayloadSerializer(payload)
        return Response(serializer.data)


class ClienteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, client_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        from apps.clients.models import Client
        client = Client.objects.filter(
            id=client_id, workspace=workspace,
        ).first()
        if client is None:
            return Response(
                {'error': 'Cliente não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        include_stale = request.query_params.get('include_stale') == '1'
        payload = ContainerService.build_cliente(
            workspace=workspace, client=client, include_stale=include_stale,
        )
        serializer = ContainerPayloadSerializer(payload)
        return Response(serializer.data)


class RelatorioView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, briefing_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        from apps.briefings.models import Briefing
        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).first()
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        include_stale = request.query_params.get('include_stale') == '1'
        payload = ContainerService.build_relatorio(
            workspace=workspace,
            briefing=briefing,
            include_stale=include_stale,
        )
        serializer = ContainerPayloadSerializer(payload)
        return Response(serializer.data)


class TagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        client = None
        client_id = request.query_params.get('client')
        if client_id:
            from apps.clients.models import Client
            client = Client.objects.filter(
                id=client_id, workspace=workspace,
            ).first()
            if client is None:
                return Response(
                    {'error': 'Cliente não encontrado'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        state = request.query_params.get('state')
        qs = TagService.list_tags(
            workspace=workspace, client=client, state=state,
        )
        serializer = InsightItemSerializer(qs, many=True)
        return Response(serializer.data)


class TagDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tag_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        tag = InsightItem.objects.filter(
            id=tag_id, workspace=workspace, kind=InsightItem.KIND_TAG,
        ).first()
        if tag is None:
            return Response(
                {'error': 'Tag não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        history = TagService.history_for(tag)
        return Response({
            'tag': InsightItemSerializer(tag).data,
            'history': InsightTagHistorySerializer(history, many=True).data,
        })

    def patch(self, request, tag_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.tag.manage',
        )
        if not ok:
            return err

        tag = InsightItem.objects.filter(
            id=tag_id, workspace=workspace, kind=InsightItem.KIND_TAG,
        ).first()
        if tag is None:
            return Response(
                {'error': 'Tag não encontrada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TagTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tag = TagService.transition(
                insight=tag,
                new_state=serializer.validated_data['new_state'],
                changed_by=request.user,
                reason=serializer.validated_data.get('reason', ''),
            )
        except InvalidTagTransitionError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(InsightItemSerializer(tag).data)


# =========================================================================
# REANÁLISE MANUAL
# =========================================================================

class _ReanalyzeBase(APIView):
    """
    Base para as views de reanálise manual.

    Cada clique gera um InsightEvent novo com
    `source_kind=manual.reanalyze` e `occurrence_id` = timestamp
    monotônico. Isso evita que a idempotência por `dedupe_key`
    bloqueie cliques repetidos legítimos — o operador pode pedir
    reanálise quantas vezes quiser.

    Devolve `job_id` para o frontend acompanhar o andamento.
    """

    permission_classes = [IsAuthenticated]
    capability = 'intelligence.insight.view'

    def _ingest(self, request, workspace, client_id, briefing_id=None):
        occurrence_id = (
            f'manual-{timezone.now().timestamp()}-{request.user.id}'
        )
        data_version = f'manual-{timezone.now().isoformat()}'

        event, job, created = IngestService.ingest_change_event(
            workspace_id=workspace.id,
            client_id=client_id,
            briefing_id=briefing_id,
            source_kind=InsightEvent.SOURCE_KIND_MANUAL_REANALYZE,
            occurrence_id=occurrence_id,
            data_version=data_version,
        )

        if event is None or job is None:
            return Response(
                {'error': 'Falha ao agendar reanálise'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                'job_id': str(job.id),
                'created': created,
                'event_id': str(event.id),
            },
            status=status.HTTP_200_OK,
        )


class BriefingReanalyzeView(_ReanalyzeBase):
    """
    POST /api/intelligence/briefings/<briefing_id>/reanalyze/

    Agenda reanálise manual do briefing. A análise é executada pelo
    worker (`python manage.py intelligence_worker`). O frontend
    acompanha pelo `job_id`.
    """

    def post(self, request, briefing_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, self.capability,
        )
        if not ok:
            return err

        from apps.briefings.models import Briefing
        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).first()
        if briefing is None:
            return Response(
                {'error': 'Briefing não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return self._ingest(
            request,
            workspace,
            client_id=briefing.client_id,
            briefing_id=briefing.id,
        )


class ClientReanalyzeView(_ReanalyzeBase):
    """
    POST /api/intelligence/clients/<client_id>/reanalyze/

    Agenda reanálise manual do cliente (sem briefing específico).
    A análise cobre o estado consolidado do cliente.
    """

    def post(self, request, client_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, self.capability,
        )
        if not ok:
            return err

        from apps.clients.models import Client
        client = Client.objects.filter(
            id=client_id, workspace=workspace,
        ).first()
        if client is None:
            return Response(
                {'error': 'Cliente não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return self._ingest(
            request,
            workspace,
            client_id=client.id,
            briefing_id=None,
        )


# =========================================================================
# JOB STATUS (polling do frontend)
# =========================================================================

class JobStatusView(APIView):
    """
    GET /api/intelligence/jobs/<job_id>/status/

    Devolve o estado atual do job + se o run associado concluiu.
    Usado pelo frontend para saber quando recarregar os containers.

    Retorna:
        {
            "job_id": str,
            "status": "pending"|"processing"|"completed"|"failed",
            "run_id": str | None,
            "run_status": str | None,
            "has_insights": bool,
            "error_message": str,
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        workspace = _resolve_workspace(request)
        ok, err = _require(
            workspace, request.user, 'intelligence.insight.view',
        )
        if not ok:
            return err

        job = AnalysisJob.objects.filter(
            id=job_id, workspace=workspace,
        ).first()
        if job is None:
            return Response(
                {'error': 'Job não encontrado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        run = job.runs.order_by('-created_at').first()
        has_insights = bool(run and run.insights.exists())

        return Response({
            'job_id': str(job.id),
            'status': job.status,
            'run_id': str(run.id) if run else None,
            'run_status': run.status if run else None,
            'has_insights': has_insights,
            'error_message': job.last_error_message or '',
        })