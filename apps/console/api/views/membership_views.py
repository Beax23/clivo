from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.console.models import ConsoleMembership
from apps.console.api.serializers.membership_serializers import (
    MembershipSerializer,
    MembershipCreateSerializer,
)
from apps.console.services.membership_service import ConsoleMembershipService
from apps.console.permissions.console_permissions import IsConsoleAdmin
from apps.console.exceptions.console_exceptions import (
    DuplicateMembershipError,
    UserNotActiveError,
)


class MembershipViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de membros do Console.

    V1: ConsoleMembership concede acesso administrativo integral.
    """

    permission_classes = [IsAuthenticated, IsConsoleAdmin]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'create':
            return MembershipCreateSerializer
        return MembershipSerializer

    def get_queryset(self):
        return ConsoleMembership.objects.select_related(
            'user', 'created_by'
        ).all().order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Adiciona um novo membro ao Console (user_id ou email)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        service = ConsoleMembershipService()

        try:
            membership = service.add_member(
                user=user,
                created_by=request.user,
            )
            return Response(
                MembershipSerializer(membership).data,
                status=status.HTTP_201_CREATED,
            )
        except DuplicateMembershipError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except UserNotActiveError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def update(self, request, *args, **kwargs):
        """Não há nada para atualizar — membership é binária."""
        membership = self.get_object()
        return Response(MembershipSerializer(membership).data)

    def destroy(self, request, *args, **kwargs):
        """Remove um membro do Console (DELETE real)."""
        membership = self.get_object()
        service = ConsoleMembershipService()
        service.remove_member(membership)
        return Response(
            {'detail': 'Membro removido do Console com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    @action(detail=False, methods=['get'], url_path='check-access')
    def check_access(self, request):
        """Verifica se o usuário atual tem acesso ao Console."""
        service = ConsoleMembershipService()
        has_access = service.has_access(request.user)
        return Response({'has_access': has_access})