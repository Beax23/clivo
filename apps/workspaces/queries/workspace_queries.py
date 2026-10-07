"""
Queries otimizadas para Workspace.

REGRA MULTI-TENANT:
    A resolução de "Workspace atual" nasce SEMPRE da combinação
    (workspace_id, user). Nunca de "workspace depois checar user".
"""

from apps.workspaces.models import Workspace, WorkspaceMembership


class WorkspaceQueries:

    @staticmethod
    def get_for_user(workspace_id, user):
        """
        Porta padrão de resolução do Workspace atual.

        Retorna o Workspace SOMENTE se:
            - o id corresponde
            - o usuário é membro
            - o Workspace está ativo

        Caso contrário, retorna None.
        A view decide se 404 ou 403.
        """
        return (
            Workspace.objects
            .filter(
                id=workspace_id,
                memberships__user=user,
                is_active=True,
            )
            .select_related('subscription__plan')
            .first()
        )

    @staticmethod
    def list_for_user_with_plan(user):
        """Lista Workspaces do usuário já com subscription e plan."""
        return (
            Workspace.objects
            .filter(memberships__user=user, is_active=True)
            .select_related('subscription__plan')
            .distinct()
            .order_by('name')
        )

    @staticmethod
    def get_last_accessed_for_user(user):
        """
        Retorna o Workspace da membership mais recentemente acessada
        pelo usuário.

        Estratégia:
            1. Ordena as memberships por `last_access_at` DESC (NULLs por último).
            2. Se todas forem NULL, cai para `joined_at` DESC.
            3. Retorna o Workspace da primeira membership elegível.

        Nunca retorna None se o usuário tiver ao menos um Workspace.
        """
        qs = (
            WorkspaceMembership.objects
            .filter(
                user=user,
                workspace__is_active=True,
            )
            .select_related('workspace', 'workspace__subscription__plan')
            .order_by('-last_access_at', '-joined_at')
        )
        membership = qs.first()
        if membership is None:
            return None
        return membership.workspace

    @staticmethod
    def get_with_subscription(workspace_id):
        return (
            Workspace.objects
            .select_related('subscription__plan')
            .filter(id=workspace_id)
            .first()
        )

    @staticmethod
    def get_with_members(workspace_id):
        return (
            Workspace.objects
            .prefetch_related('memberships__user', 'memberships__governance')
            .filter(id=workspace_id)
            .first()
        )