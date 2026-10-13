"""
Helpers de resolução de workspace para as views HTML.

REGRA DE OURO:
    Toda view HTML autenticada dentro de um workspace resolve o
    workspace via `public_id` da URL + `request.user`. A URL vence
    a sessão. A sessão é atualizada para refletir a URL, mas nunca
    decide o workspace sozinha.
"""

from django.shortcuts import redirect

from apps.workspaces.public_id import decode_workspace_id
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.services import WorkspaceMembershipService


# Destino padrão quando não conseguimos resolver o workspace.
ENTRY_REDIRECT = '/workspaces/entrar/'


def resolve_workspace_or_redirect(request, public_id):
    """
    Resolve o workspace a partir de `public_id` da URL + `request.user`.

    Retorna uma tupla `(workspace, error_response)`:

        - `(workspace, None)`      → resolvido com sucesso.
        - `(None, HttpResponse)`   → o chamador deve retornar a resposta
                                      de erro diretamente.

    Efeitos colaterais em caso de sucesso:
        - `request.session['current_workspace_id']` é atualizado
          para o workspace resolvido. Isso mantém a sessão coerente
          com a URL (a URL vence, a sessão reflete).
        - `last_access_at` da membership do usuário é atualizado
          (touch), para o workspace continuar sendo o "último acessado"
          em entradas futuras sem public_id na URL.

    Contrato de erro:
        - `public_id` inválido             → redirect para ENTRY_REDIRECT.
        - workspace não encontrado          → redirect para ENTRY_REDIRECT.
        - usuário não é membro              → redirect para ENTRY_REDIRECT.
        - workspace inativo                 → redirect para ENTRY_REDIRECT.

    Em nenhum caso o chamador deve receber um workspace que o
    usuário não pode acessar. Todas as falhas colapsam para o
    mesmo redirect — não vazamos a razão da falha.
    """

    if not public_id:
        return None, redirect(ENTRY_REDIRECT)

    workspace_id = decode_workspace_id(public_id)
    if workspace_id is None:
        return None, redirect(ENTRY_REDIRECT)

    workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
    if workspace is None:
        return None, redirect(ENTRY_REDIRECT)

    # Sincroniza a sessão com a URL.
    request.session['current_workspace_id'] = str(workspace.id)

    # Atualiza o "último acessado" para o workspace continuar sendo
    # a escolha natural quando o usuário entrar por /workspaces/entrar/.
    try:
        WorkspaceMembershipService.touch_last_access(workspace, request.user)
    except Exception:
        # Nunca quebra a renderização por causa do touch.
        pass

    return workspace, None