"""
WorkspaceContextMiddleware — injeta `workspace_public_id` em toda request.

Resolve a partir da sessão (`current_workspace_id`). Necessário porque
`workspace_public_id` no `context_processor` só existe quando a URL
traz `<public_id>` no path (`/w/<public_id>/...`). Em `/clientes/` e
`/fluxo/` a URL não tem esse parâmetro, e o JS ficaria sem valor para
montar `/w/<pid>/briefings/<id>/resumo/`.
"""

import logging

from apps.workspaces.public_id import encode_workspace_id
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('workspaces')


class WorkspaceContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.workspace_public_id = ''

        try:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                ws_id = request.session.get('current_workspace_id')
                if ws_id:
                    workspace = WorkspaceQueries.get_for_user(ws_id, user)
                    if workspace is not None:
                        request.workspace_public_id = encode_workspace_id(
                            workspace.id,
                        )
        except Exception:
            logger.exception(
                'Falha ao resolver workspace_public_id (path=%s)',
                getattr(request, 'path', '?'),
            )

        return self.get_response(request)