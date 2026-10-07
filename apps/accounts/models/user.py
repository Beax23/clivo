import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.core.validators import EmailValidator
from django.db.models.functions import Lower

from apps.accounts.managers.user_manager import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Modelo principal de usuário do Clivo.

    Este modelo representa a identidade única de uma pessoa na plataforma.
    NÃO contém informações específicas de domínio (workspace, console, etc.).

    O is_staff e is_superuser são restritos ao Django Admin/Infraestrutura.
    Nao representam autoridade da Clivo. Para isso, use:
    - ConsoleMembership (acesso ao Console)
    - WorkspaceMembership (acesso a Workspaces)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único universal do usuário')
    )

    email = models.EmailField(
        max_length=254,
        unique=True,
        db_index=True,
        validators=[EmailValidator()],
        help_text=_('Email principal do usuário (usado para login)')
    )

    first_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_('Primeiro nome do usuário')
    )

    last_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_('Sobrenome do usuário')
    )

    avatar = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_('URL da foto de perfil (vem do Google ou upload)')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Designa se o usuário pode fazer login')
    )

    is_staff = models.BooleanField(
        default=False,
        help_text=_('Designa se o usuário tem acesso ao admin Django')
    )

    is_superuser = models.BooleanField(
        default=False,
        help_text=_('Designa se o usuário tem todos os poderes no admin')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação da conta')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'accounts_user'
        verbose_name = _('Usuário')
        verbose_name_plural = _('Usuários')
        indexes = [
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower('email'),
                name='accounts_user_email_ci_unique'
            ),
        ]
        ordering = ['-created_at']

    @classmethod
    def normalize_email(cls, email: str) -> str:
        """Canonicalização de email: trim + lowercase."""
        if email:
            return email.strip().lower()
        return email

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.email

    def clean(self):
        super().clean()
        self.email = self.normalize_email(self.email)

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name