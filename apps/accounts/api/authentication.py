from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount import providers
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
import logging

from apps.accounts.serializers import (
    LoginSerializer,
    GoogleLoginSerializer,
    SessionInfoSerializer,
)
from apps.accounts.services import (
    AuthenticationService,
    SessionService,
)
from apps.accounts.exceptions.account_exceptions import (
    AuthenticationFailedError,
    EmailAlreadyRegisteredError,
    SessionError,
)

logger = logging.getLogger('accounts')


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    """Endpoint para inicializar o cookie CSRF."""
    permission_classes = [AllowAny]

    def get(self, request):
        get_token(request)
        return Response({'detail': 'CSRF cookie set'})


class LoginView(APIView):
    """View para login com email e senha."""
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            user = AuthenticationService.authenticate_user(
                email=serializer.validated_data['email'],
                password=serializer.validated_data['password']
            )
            
            # Usa SessionService.login para autenticar e registrar sessão
            SessionService.login(request, user, 'app')
            
            return Response({
                'detail': 'Login realizado com sucesso',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'full_name': user.full_name,
                },
                'session': SessionService.get_session_info(request)
            }, status=status.HTTP_200_OK)
            
        except AuthenticationFailedError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except SessionError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class GoogleLoginView(APIView):
    """
    View para login com Google via django-allauth.
    
    Contrato: POST /api/auth/login/google/ com { "code": "..." }
    
    O django-allauth é a autoridade única para OAuth.
    Esta view apenas recebe o code e delega ao allauth.
    """
    permission_classes = [AllowAny]
    serializer_class = GoogleLoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        code = serializer.validated_data.get('code')
        
        if not code:
            return Response(
                {'detail': 'Código de autorização do Google é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Inicializa o adapter do allauth
            adapter = GoogleOAuth2Adapter(request)
            
            # Obtém o token e dados do usuário via adapter
            token_data = adapter.get_access_token_data(code)
            
            # Cria o sociallogin via provider
            provider = providers.registry.by_id('google')
            sociallogin = provider.sociallogin_from_response(request, token_data)
            
            # Delega completamente para o allauth
            complete_social_login(request, sociallogin)
            
            user = sociallogin.user
            
            if not user.is_active:
                return Response(
                    {'detail': 'Conta desativada'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # O allauth já fez o login, mas precisamos garantir o UserSession
            # Usa o signal user_logged_in para isso
            # O tipo de sessão é 'app' (padrão)
            
            return Response({
                'detail': 'Login com Google realizado com sucesso',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'full_name': user.full_name,
                    'avatar': user.avatar,
                },
                'session': SessionService.get_session_info(request),
            }, status=status.HTTP_200_OK)
                
        except ValidationError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except EmailAlreadyRegisteredError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_409_CONFLICT
            )
        except providers.ProviderException as e:
            logger.error(f'Erro no provider Google: {str(e)}', exc_info=True)
            return Response(
                {'detail': 'Erro na autenticação com Google'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f'Erro inesperado no login com Google: {str(e)}', exc_info=True)
            return Response(
                {'detail': 'Erro interno ao processar login com Google'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LogoutView(APIView):
    """View para logout."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            SessionService.destroy_session(request)
            return Response(
                {'detail': 'Logout realizado com sucesso'},
                status=status.HTTP_200_OK
            )
        except SessionError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SessionView(APIView):
    """View para obter informações da sessão atual."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_info = SessionService.get_session_info(request)
        
        if session_info is None:
            return Response(
                {'detail': 'Sessão não encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = SessionInfoSerializer(session_info)
        return Response(serializer.data)