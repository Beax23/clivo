"""
WorkspaceSubscriptionService — consulta e (futuramente) alteração
do plano do Workspace.

V1:
    - A subscription é criada junto com o Workspace.
    - Sem endpoint para trocar plano.
    - Sem billing.
"""

from typing import Optional

from apps.workspaces.models import (
    Workspace,
    WorkspaceSubscription,
)


class WorkspaceSubscriptionService:

    @staticmethod
    def get_subscription(workspace: Workspace) -> Optional[WorkspaceSubscription]:
        try:
            return WorkspaceSubscription.objects.select_related('plan').get(
                workspace=workspace
            )
        except WorkspaceSubscription.DoesNotExist:
            return None

    @staticmethod
    def get_active_plan(workspace: Workspace):
        """Retorna o Plan ativo do Workspace, ou None."""
        sub = WorkspaceSubscriptionService.get_subscription(workspace)
        if sub and sub.is_active:
            return sub.plan
        return None