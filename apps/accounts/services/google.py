"""
Serviço para autenticação com Google via django-allauth.
"""

from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount import providers
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.exceptions.account_exceptions import SocialAccountError


class GoogleAuthService:
    """
    Serviço para autenticação com Google.
    
    Encapsula toda a interação com django-allauth.
    A View não precisa conhecer os internals do allauth.
    """

    @staticmethod
    def authenticate_with_code(request, code: str) -> User:
        """
        Autentica um usuário com o código de autorização do Google.
        
        Args:
            request: Django request
            code: Código de autorização do Google
            
        Returns:
            User: Usuário autenticado/criado
            
        Raises:
            ValidationError: Erro de validação
            SocialAccountError: Erro no provider
        """
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
            
            return sociallogin.user
            
        except ValidationError:
            raise
        except Exception as e:
            # Converte erros do provider para exceção do domínio
            raise SocialAccountError(f'Erro na autenticação com Google: {str(e)}')