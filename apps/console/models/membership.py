import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ConsoleMembership(models.Model):
    """
    Associação de um usuário ao Console.

    V1:
        Todo usuário com ConsoleMembership tem acesso administrativo
        integral ao Console. Não há níveis de administrador.

    Um usuário pode ter no máximo UMA membership (OneToOne).

    Remover o acesso = DELETE do registro.

    Não usar:
        - is_active
        - deleted_at
        - activate() / deactivate()

    Não forçar governance.
    Não usar is_superuser como regra de negócio do Console.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único da associação')
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='console_membership',
        help_text=_('Usuário associado ao Console')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_console_memberships',
        help_text=_('Usuário que concedeu acesso')
    )

    class Meta:
        db_table = 'console_membership'
        verbose_name = _('Membro do Console')
        verbose_name_plural = _('Membros do Console')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} (Console)"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user and not self.user.is_active:
            raise ValidationError({
                'user': _(
                    'Não é possível adicionar um usuário inativo ao Console'
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)