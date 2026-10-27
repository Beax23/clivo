from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from apps.workspaces.helpers import resolve_workspace_or_redirect
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.queries import WorkspaceQueries
from apps.briefings.models import Briefing
from apps.briefings.api.serializers import PortalBriefingSerializer
from apps.briefings.queries import BriefingQueries


def _resolve_current_workspace(request):
    workspace_id = request.session.get('current_workspace_id')
    if not workspace_id:
        return None
    return WorkspaceQueries.get_for_user(workspace_id, request.user)


def _workspace_public_id(workspace):
    if workspace is None:
        return ''
    return str(
        getattr(workspace, 'public_id', '')
        or getattr(workspace, 'slug', '')
        or workspace.id
    )


class FluxoView(View):
    """
    Renderiza a página da Mesa (painel principal do arquiteto).
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace = _resolve_current_workspace(request)
        public_id = _workspace_public_id(workspace)

        return render(request, 'fluxo.html', {
            'workspace_public_id': public_id,
        })


class BriefingDetailView(View):
    def get(self, request, public_id, briefing_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace, error = resolve_workspace_or_redirect(request, public_id)
        if error is not None:
            return error

        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user,
        ).exists()
        if not is_member:
            return redirect('/workspaces/entrar/')

        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).first()
        if briefing is None:
            return redirect('/fluxo/')

        return render(request, 'briefing_detail.html', {
            'workspace': workspace,
            'briefing_id': str(briefing.id),
            'workspace_public_id': _workspace_public_id(workspace),
        })


class BriefingRawAnswersView(View):
    def get(self, request, briefing_id=None):
        client = getattr(request, 'portal_client', None)
        if client is None:
            return redirect('/portal/')

        briefing = BriefingQueries.get_for_client(client, briefing_id)
        if briefing is None:
            raise Http404('Briefing não encontrado.')

        briefing.mark_expired_if_needed()

        payload = PortalBriefingSerializer(
            context={'request': request},
        ).to_representation(briefing)

        return render(
            request,
            'portal/briefing_raw_client.html',
            {'briefing': payload},
        )


class BriefingArchitectRawView(View):
    def get(self, request, public_id, briefing_id):
        if not request.user.is_authenticated:
            return redirect('/login/')

        workspace, error = resolve_workspace_or_redirect(request, public_id)
        if error is not None:
            return error

        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user,
        ).exists()
        if not is_member:
            return redirect('/workspaces/entrar/')

        briefing = Briefing.objects.filter(
            id=briefing_id, workspace=workspace,
        ).select_related('client', 'workspace', 'template').first()
        if briefing is None:
            return redirect('/fluxo/')

        payload = PortalBriefingSerializer(
            context={'request': request},
        ).to_representation(briefing)

        return render(
            request,
            'portal/briefing_raw_architect.html',
            {'briefing': payload},
        )