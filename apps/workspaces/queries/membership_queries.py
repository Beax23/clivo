from apps.workspaces.models import WorkspaceMembership


class MembershipQueries:

    @staticmethod
    def list_for_workspace(workspace_id):
        return (
            WorkspaceMembership.objects
            .filter(workspace_id=workspace_id)
            .select_related('user', 'governance')
            .order_by('-joined_at')
        )

    @staticmethod
    def count_owners(workspace_id):
        return WorkspaceMembership.objects.filter(
            workspace_id=workspace_id,
            governance__key='proprietario',
        ).count()