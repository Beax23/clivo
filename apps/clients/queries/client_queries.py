"""
Queries otimizadas para Client.
"""

from apps.clients.models import Client


class ClientQueries:

    @staticmethod
    def list_for_workspace(workspace):
        """
        Lista TODOS os clientes do workspace, sem filtro de status.
        """
        return (
            Client.objects
            .filter(workspace=workspace)
            .order_by('-created_at')
        )

    @staticmethod
    def get_with_relations(client_id):
        return (
            Client.objects
            .select_related('workspace', 'created_by')
            .filter(id=client_id)
            .first()
        )

    @staticmethod
    def get_by_public_code(code: str):
        return (
            Client.objects
            .select_related('workspace')
            .filter(public_code=code)
            .first()
        )

    @staticmethod
    def count_for_workspace(workspace) -> int:
        """Conta TODOS os clientes do workspace."""
        return Client.objects.filter(workspace=workspace).count()

    @staticmethod
    def count_active_for_workspace(workspace) -> int:
        """Conta apenas clientes ativos do workspace."""
        return Client.objects.filter(
            workspace=workspace,
            status=Client.STATUS_ACTIVE,
        ).count()