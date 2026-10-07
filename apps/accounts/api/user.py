from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import IntegrityError
from django.contrib.auth import logout
import logging

from apps.accounts.serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
)
from apps.accounts.services import AccountService, SessionService
from apps.accounts.exceptions.account_exceptions import (
    EmailAlreadyRegisteredError,
    SessionError,
)

logger = logging.getLogger('accounts')


class UserCreateView(APIView):
    """View para criar um novo usuário (registro público)."""
    permission_classes = [AllowAny]
    serializer_class = UserCreateSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            user = serializer.save()
            
            SessionService.create_session(request, user, 'app')
            
            return Response(
                UserSerializer(user).data,
                status=status.HTTP_201_CREATED
            )
            
        except EmailAlreadyRegisteredError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_409_CONFLICT
            )
        except IntegrityError:
            return Response(
                {'detail': 'Erro de concorrência. Tente novamente.'},
                status=status.HTTP_409_CONFLICT
            )


class UserMeView(APIView):
    """View para gerenciar o próprio usuário."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(user).data)

    def delete(self, request):
        """Desativa a própria conta e revoga todas as sessões."""
        try:
            user = request.user
            
            AccountService.deactivate_user(user)
            SessionService.destroy_all_sessions(user)
            logout(request)
            
            return Response(
                {'detail': 'Conta desativada com sucesso. Todas as sessões foram encerradas.'},
                status=status.HTTP_200_OK
            )
            
        except SessionError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )