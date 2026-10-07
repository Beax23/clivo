"""
Modelo ClientPortalFeedback.

Feedback de EXPERIÊNCIA do cliente sobre o Portal.

IMPORTANTE:
    Este modelo NÃO armazena feedback sobre conteúdo interpretado
    (briefing, intelligence). Isso pertence a `intelligence`.

    Aqui é apenas:
        - "Foi fácil responder?"
        - "Algo não funcionou?"
        - "Como foi sua experiência?"

Escopo: experiência do Portal.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


class ClientPortalFeedback(models.Model):

    KIND_EXPERIENCE = 'experience'
    KIND_ISSUE = 'issue'
    KIND_SUGGESTION = 'suggestion'

    KIND_CHOICES = [
        (KIND_EXPERIENCE, 'Experiência'),
        (KIND_ISSUE, 'Problema'),
        (KIND_SUGGESTION, 'Sugestão'),
    ]

    RATING_POOR = 'poor'
    RATING_OK = 'ok'
    RATING_GREAT = 'great'

    RATING_CHOICES = [
        (RATING_POOR, 'Ruim'),
        (RATING_OK, 'Ok'),
        (RATING_GREAT, 'Ótimo'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='portal_feedbacks',
    )

    kind = models.CharField(
        max_length=20,
        choices=KIND_CHOICES,
        default=KIND_EXPERIENCE,
    )

    rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        blank=True,
    )

    message = models.TextField(
        blank=True,
        help_text=_('Comentário livre do cliente'),
    )

    page = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Página do Portal onde o feedback foi enviado'),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'client_portal_feedback'
        verbose_name = _('Feedback do Portal')
        verbose_name_plural = _('Feedbacks do Portal')
        indexes = [
            models.Index(fields=['client', '-created_at']),
            models.Index(fields=['kind']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback {self.kind} — {self.client.name}"