"""
Queries otimizadas para Workspace.

REGRA MULTI-TENANT:
    A resolução de "Workspace atual" nasce SEMPRE da combinação
    (workspace_id, user). Nunca de "workspace depois checar user".

REGRA DE PREFETCH:
    - `list_for_user_with_plan` e `get_last_accessed_for_user` são
      chamadas em listagens. Usam `Prefetch` filtrado por
      `is_active=True` com `to_attr='_active_subscriptions'`. Isso
      garante que a property `Workspace.active_subscription` use o
      cache sem disparar N+1 nem carregar assinaturas inativas.
    - `get_for_user` e `get_with_subscription` operam sobre UM
      workspace. Não usam Prefetch — a property resolve quando o
      consumidor precisar.
"""

from django.db.models import Prefetch

from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.workspaces.models import WorkspaceSubscription


def _active_subscriptions_prefetch():
    """
    Prefetch das assinaturas ATIVAS de um workspace, com plano
    carregado e ordenadas por started_at DESC.

    `to_attr='_active_subscriptions'` faz o Django guardar o
    resultado em uma lista — que a property `active_subscription`
    consome sem query adicional.
    """
    return Prefetch(
        'subscriptions',
        queryset=(
            WorkspaceSubscription.objects
            .filter(is_active=True)
            .select_related('plan')
            .order_by('-started_at')
        ),
        to_attr='_active_subscriptions',
    )


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

        NÃO faz prefetch de subscriptions. A property
        `active_subscription` resolve sob demanda quando consumida.
        """
        return (
            Workspace.objects
            .filter(
                id=workspace_id,
                memberships__user=user,
                is_active=True,
            )
            .first()
        )

    @staticmethod
    def list_for_user_with_plan(user):
        """
        Lista Workspaces do usuário com a assinatura ativa prefetchada.

        O Prefetch é filtrado (is_active=True) e o resultado fica em
        `_active_subscriptions`. A property `active_subscription` usa
        esse cache diretamente, sem query adicional.
        """
        return (
            Workspace.objects
            .filter(memberships__user=user, is_active=True)
            .prefetch_related(_active_subscriptions_prefetch())
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

        O Prefetch atravessa a relação workspace → subscriptions,
        porque a membership é o ponto de partida.
        """
        prefetch = Prefetch(
            'workspace__subscriptions',
            queryset=(
                WorkspaceSubscription.objects
                .filter(is_active=True)
                .select_related('plan')
                .order_by('-started_at')
            ),
            to_attr='_active_subscriptions',
        )

        qs = (
            WorkspaceMembership.objects
            .filter(
                user=user,
                workspace__is_active=True,
            )
            .select_related('workspace')
            .prefetch_related(prefetch)
            .order_by('-last_access_at', '-joined_at')
        )
        membership = qs.first()
        if membership is None:
            return None
        return membership.workspace

    @staticmethod
    def get_with_subscription(workspace_id):
        """
        Retorna o Workspace por id. Sem prefetch — a property
        `active_subscription` resolve quando o consumidor precisar.
        """
        return (
            Workspace.objects
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