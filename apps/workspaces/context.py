"""
Context processors do módulo workspaces.

Expõem dados do workspace ativo para todos os templates do shell
sem precisar passar via view. O `workspace_public_id` é lido do
`resolver_match` da URL atual.
"""


def workspace_public_id(request):
    """
    Injeta `workspace_public_id` no contexto de todo template.

    Regras:
        - Se a URL atual é `/w/<public_id>/...`, devolve o `<public_id>`.
        - Se a URL não segue esse padrão (login, console, api,
          rotas antigas, admin), devolve `None`.

    O template decide o que fazer com `None`:
        - Páginas autenticadas dentro de workspace esperam valor.
        - Páginas fora do padrão (console, login) recebem None
          e não usam esse valor.
    """
    match = getattr(request, 'resolver_match', None)
    if match is None:
        return {'workspace_public_id': None}

    public_id = match.kwargs.get('public_id')
    return {'workspace_public_id': public_id}