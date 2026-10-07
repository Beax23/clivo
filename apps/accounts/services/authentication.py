from django.contrib.auth import authenticate

from apps.accounts.models import User
from apps.accounts.exceptions.account_exceptions import AuthenticationFailedError


class AuthenticationService:
    """Serviço de autenticação do Clivo."""

    @staticmethod
    def authenticate_user(email: str, password: str) -> User:
        """Autentica um usuário com email e senha."""
        email = User.normalize_email(email)
        user = authenticate(email=email, password=password)
        
        if user is None:
            raise AuthenticationFailedError('Credenciais inválidas')
        
        # O Django já impede login de usuário inativo no authenticate
        # Esta verificação é redundante, mantida como defesa
        if not user.is_active:
            raise AuthenticationFailedError('Credenciais inválidas')
        
        return user