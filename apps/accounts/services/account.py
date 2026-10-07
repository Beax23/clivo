from typing import Optional
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.exceptions.account_exceptions import (
    EmailAlreadyRegisteredError,
    UserNotFoundError,
    UserInactiveError,
)


class AccountService:
    """Serviço para gerenciamento de contas."""

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[User]:
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        email = User.normalize_email(email)
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            return None

    @staticmethod
    def create_account(
        email: str,
        password: str,
        first_name: str = '',
        last_name: str = '',
        **extra_fields
    ) -> User:
        """
        Cria uma nova conta de usuário com senha.
        
        Password é obrigatório para criação de conta via este método.
        Para contas sociais (Google), o allauth gerencia a criação.
        """
        email = User.normalize_email(email)
        
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    **extra_fields
                )
                return user
                
        except IntegrityError as e:
            # Verifica se é a constraint de email único
            if 'accounts_user_email_ci_unique' in str(e):
                raise EmailAlreadyRegisteredError('Este email já está registrado')
            # Re-levanta outras IntegrityError
            raise

    @staticmethod
    def update_user(user: User, **fields) -> User:
        allowed_fields = ['first_name', 'last_name', 'avatar']
        
        for field, value in fields.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)
        
        user.clean()
        user.save()
        return user

    @staticmethod
    def deactivate_user(user: User) -> None:
        """Desativa a conta. A revogação de sessões deve ser feita pelo chamador."""
        user.is_active = False
        user.save()

    @staticmethod
    def activate_user(user: User) -> None:
        user.is_active = True
        user.save()

    @staticmethod
    def check_user_active(user: User) -> None:
        if not user.is_active:
            raise UserInactiveError('Usuário inativo')