from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
import logging

from apps.accounts.serializers import (
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from apps.accounts.services import PasswordService
from apps.accounts.exceptions.account_exceptions import (
    InvalidPasswordError,
    TokenInvalidError,
)

logger = logging.getLogger('accounts')


class PasswordChangeView(APIView):
    """View para alterar senha."""
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            user = request.user
            current_session_key = request.session.session_key
            
            count_destroyed = PasswordService.change_password(
                user=user,
                current_password=serializer.validated_data['current_password'],
                new_password=serializer.validated_data['new_password'],
                exclude_session_key=current_session_key
            )
            
            return Response({
                'detail': 'Senha alterada com sucesso',
                'other_sessions_destroyed': count_destroyed
            }, status=status.HTTP_200_OK)
            
        except InvalidPasswordError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class PasswordResetView(APIView):
    """
    View para solicitar reset de senha.
    
    Segurança: Sempre retorna 200 mesmo se email não existir.
    """
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        
        PasswordService.request_password_reset(email)
        
        return Response(
            {'detail': 'Se o email existir, você receberá as instruções para resetar a senha'},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(APIView):
    """View para confirmar reset de senha."""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            count_destroyed = PasswordService.reset_password(
                uid=serializer.validated_data['uid'],
                token=serializer.validated_data['token'],
                new_password=serializer.validated_data['new_password']
            )
            
            return Response({
                'detail': 'Senha redefinida com sucesso',
                'sessions_destroyed': count_destroyed
            }, status=status.HTTP_200_OK)
            
        except (TokenInvalidError, InvalidPasswordError) as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )