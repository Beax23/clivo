"""
Modelo Workspace.

Workspace é o tenant do Clivo — representa um escritório de arquitetura.

REGRA ARQUITETURAL:
    Workspace V1 é identidade pura.

    Workspace NÃO é objeto de configuração.
    Workspace NÃO carrega branding.
    Workspace NÃO carrega settings de domínio.

    Configurações específicas (briefing, intelligence, etc)
    pertencem aos domínios que as usam, não ao tenant.

RELAÇÃO:

    Workspace
        ├── WorkspaceMembership  (quem pertence)
        └── WorkspaceSubscription (qual plano)
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class Workspace(models.Model):
    """
    Escritório de arquitetura — tenant do Clivo.

    Identidade mínima: nome, slug, CNPJ, localização.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Identificador único do Workspace')
    )

    name = models.CharField(
        max_length=150,
        help_text=_('Nome do escritório (ex: "Studio Exemplo")')
    )

    slug = models.SlugField(
        max_length=150,
        unique=True,
        help_text=_(
            'Identificador técnico estável (gerado do nome). '
            'Nunca exibido diretamente ao usuário.'
        )
    )

    cnpj = models.CharField(
        max_length=18,
        blank=True,
        help_text=_('CNPJ do escritório (opcional)')
    )

    city = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Cidade do escritório')
    )

    state = models.CharField(
        max_length=2,
        blank=True,
        help_text=_('UF do escritório (ex: "BA", "SP")')
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Se o Workspace está ativo')
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_('Data de criação')
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text=_('Data da última atualização')
    )

    class Meta:
        db_table = 'workspace'
        verbose_name = _('Workspace')
        verbose_name_plural = _('Workspaces')
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.name or not self.name.strip():
            raise ValidationError({
                'name': _('O nome é obrigatório')
            })

        if not self.slug:
            raise ValidationError({
                'slug': _('O slug é obrigatório')
            })

        if self.slug != slugify(self.slug):
            raise ValidationError({
                'slug': _(
                    'O slug deve conter apenas letras minúsculas, '
                    'números e hífens.'
                )
            })

        if self.state and len(self.state) != 2:
            raise ValidationError({
                'state': _('A UF deve ter exatamente 2 caracteres')
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)