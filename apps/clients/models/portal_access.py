"""
Modelo ClientPortalAccess.

Observabilidade do uso do Portal — registra cada acesso bem-sucedido.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


class ClientPortalAccess(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='portal_accesses',
    )

    session = models.ForeignKey(
        'clients.ClientPortalSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accesses',
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    accessed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'client_portal_access'
        verbose_name = _('Acesso ao Portal')
        verbose_name_plural = _('Acessos ao Portal')
        indexes = [
            models.Index(fields=['client', '-accessed_at']),
        ]
        ordering = ['-accessed_at']

    def __str__(self):
        return f"{self.client.name} @ {self.accessed_at}"