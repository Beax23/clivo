from rest_framework.permissions import BasePermission

from apps.console.services.membership_service import ConsoleMembershipService


class IsConsoleAdmin(BasePermission):
    """
    Permissão de entrada no Console.

    V1: basta ter ConsoleMembership. Não há distinção de governança.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        service = ConsoleMembershipService()
        return service.has_access(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)