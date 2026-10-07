"""
AdminUserViewSet — o Console visualiza todos os usuários.

REGRA:
    O Console NÃO cria/edita/desativa usuários pela API.
    Isso continua sendo responsabilidade de `accounts`.

    No V1, é read-only. Se for necessário (ex: "desativar usuário
    suspeito"), vira uma action específica no futuro.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from apps.console.api.serializers.user_admin_serializers import (
    AdminUserSerializer,
)
from apps.console.permissions.console_permissions import IsConsoleAdmin

User = get_user_model()


class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only. Lista todos os usuários da plataforma.

    Permite filtros por `q` (email ou nome), `is_active`.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    serializer_class = AdminUserSerializer
    lookup_field = 'id'

    def get_queryset(self):
        qs = User.objects.all().order_by('-created_at')

        q = self.request.query_params.get('q')
        if q:
            qs = (
                qs.filter(email__icontains=q) |
                qs.filter(first_name__icontains=q) |
                qs.filter(last_name__icontains=q)
            )

        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        elif is_active in ('0', 'false', 'False'):
            qs = qs.filter(is_active=False)

        return qs