"""
Views da API de Inteligência.

Endpoints:
    GET  /api/intelligence/mesa/
        Containers da Mesa para o workspace atual (opcional ?client=).

    GET  /api/intelligence/clientes/<client_id>/
        Containers do Cliente.

    GET  /api/intelligence/briefings/<briefing_id>/relatorio/
        Relatório do briefing (8 containers).

    GET  /api/intelligence/tags/
        Lista tags do workspace (?client=&state=).

    GET  /api/intelligence/tags/<id>/
        Detalhe da tag + histórico.

    PATCH /api/intelligence/tags/<id>/
        Transição de estado (confirmada/descartada) com histórico.

Autorização:
    - Usuário autenticado.
    - Membro do workspace (via `user_has_capability` do módulo
      `workspaces`, que é o único ponto de autorização cross-app).
    - Capability necessária: `intelligence.insight.view` para leitura
      e `intelligence.tag.manage` para transição de tag.
"""

import logging

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
from apps.intelligence.models import InsightItem
from apps.intelligence.services import (
    ContainerService,
    TagService,
    InvalidTagTransitionError,
)
from apps.workspaces.permissions.workspace_permissions import (
    user_has_capability,
)
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('intelligence')


def _resolve_workspace(request):
    """
    Resolve o workspace ativo da sessão. Retorna None se não houver.
    Reusa o contrato de `workspaces` — sem duplicar resolução.
    """
    ws_id = request.session.get('current_workspace_id')
    if not ws_id:
        return None
    return WorkspaceQueries.get_for_user(ws_id, request.user)


def _require(workspace, user, capability: str):
    """
    Retorna (True, None) ou (False, Response 403).
    """
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