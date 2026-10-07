from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
from typing import Optional


class UserManager(BaseUserManager):
    """
    Manager personalizado para User com UUID e email como identifier.
    """

    def normalize_email(self, email: str) -> str:
        """Canonicalização de email: trim + lowercase."""
        if email:
            return email.strip().lower()
        return email

    def create_user(self, email: str, password: Optional[str] = None, **extra_fields):
        if not email:
            raise ValueError(_('O email é obrigatório'))
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        
        if password is not None:
            user.set_password(password)
        else:
            user.set_unusable_password()
        
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: Optional[str] = None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superusuário deve ter is_staff=True'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superusuário deve ter is_superuser=True'))

        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email: str):
        email = self.normalize_email(email)
        return self.get(email=email)