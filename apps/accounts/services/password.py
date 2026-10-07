from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.db import transaction, IntegrityError

from apps.accounts.models import User
from apps.accounts.exceptions.account_exceptions import (
    InvalidPasswordError,
    TokenInvalidError,
)
from apps.accounts.services.account import AccountService
from apps.accounts.services.email import EmailService
from apps.accounts.services.session import SessionService


class PasswordService:
    """Serviço para gerenciamento de senhas."""

    @staticmethod
    def validate_password(password: str, user: User = None) -> None:
        """
        Valida a força da senha usando os validadores do Django.
        Esta é a ÚNICA autoridade para validação de senha.
        """
        try:
            password_validation.validate_password(password, user)
        except ValidationError as e:
            # Mantém todas as mensagens de erro
            raise InvalidPasswordError(' '.join(e.messages))

    @staticmethod
    def change_password(
        user: User,
        current_password: str,
        new_password: str,
        exclude_session_key: str = None
    ) -> int:
        if not user.check_password(current_password):
            raise InvalidPasswordError('Senha atual incorreta')
        
        PasswordService.validate_password(new_password, user)
        
        with transaction.atomic():
            user.set_password(new_password)
            user.save()
            
            count_destroyed = SessionService.destroy_all_sessions(
                user=user,
                exclude_current=exclude_session_key
            )
        
        return count_destroyed

    @staticmethod
    def generate_password_reset_token(user: User) -> dict:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        return {
            'uid': uid,
            'token': token,
        }

    @staticmethod
    def verify_password_reset_token(uid: str, token: str) -> User:
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = AccountService.get_user_by_id(user_id)
            
            if user is None:
                raise TokenInvalidError('Usuário inválido')
            
            if not user.is_active:
                raise TokenInvalidError('Usuário inativo')
            
            if not default_token_generator.check_token(user, token):
                raise TokenInvalidError('Token inválido ou expirado')
            
            return user
            
        except (TypeError, ValueError, OverflowError):
            raise TokenInvalidError('Token inválido')

    @staticmethod
    def reset_password(uid: str, token: str, new_password: str) -> int:
        user = PasswordService.verify_password_reset_token(uid, token)
        
        PasswordService.validate_password(new_password, user)
        
        with transaction.atomic():
            user.set_password(new_password)
            user.save()
            
            count_destroyed = SessionService.destroy_all_sessions(user)
        
        return count_destroyed

    @staticmethod
    def request_password_reset(email: str) -> None:
        user = AccountService.get_user_by_email(email)
        
        if user and user.is_active:
            token_data = PasswordService.generate_password_reset_token(user)
            EmailService.send_password_reset_email(user, token_data)