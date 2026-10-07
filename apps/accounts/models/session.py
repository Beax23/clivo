import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone

from apps.accounts.models.user import User


class UserSession(models.Model):
    """
    Modelo para rastreamento de sessões ativas de usuários.
    
    Este modelo é apenas para rastreamento e controle.
    O mecanismo de autenticação é gerenciado pelo Django.
    """
    
    SESSION_TYPES = [
        ('app', 'App'),
        ('console', 'Console'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da sessão')
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions',
        help_text=_('Usuário da sessão')
    )
    
    session_key = models.CharField(
        max_length=40,
        unique=True,
        help_text=_('Chave da sessão Django')
    )
    
    session_type = models.CharField(
        max_length=10,
        choices=SESSION_TYPES,
        default='app',
        help_text=_('Tipo de sessão: app ou console')
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_('Endereço IP da sessão')
    )
    
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('User-Agent da sessão')
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação da sessão')
    )
    
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Última atividade da sessão')
    )
    
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Data de expiração da sessão (metadado)')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Sessão ativa?')
    )
    
    class Meta:
        db_table = 'accounts_user_session'
        verbose_name = _('Sessão do Usuário')
        verbose_name_plural = _('Sessões dos Usuários')
        indexes = [
            models.Index(fields=['user', 'session_type']),
            models.Index(fields=['is_active', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.session_type} - {self.session_key[:8]}"