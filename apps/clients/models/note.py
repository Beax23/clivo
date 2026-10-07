"""
Modelo ClientNote.

Anotação interna da equipe sobre o cliente.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


class ClientNote(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='notes',
    )

    author = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='client_notes',
    )

    content = models.TextField()

    is_pinned = models.BooleanField(
        default=False,
        help_text=_('Se a anotação deve aparecer em destaque'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_note'
        verbose_name = _('Anotação do Cliente')
        verbose_name_plural = _('Anotações do Cliente')
        indexes = [
            models.Index(fields=['client', '-created_at']),
            models.Index(fields=['author']),
            models.Index(fields=['is_pinned']),
        ]
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        author = self.author.email if self.author else 'sistema'
        return f"Nota de {author} sobre {self.client.name}"