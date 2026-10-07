"""
Modelo ClientContact.

Pessoas associadas ao cliente.
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clients.models.client import Client


class ClientContact(models.Model):

    ROLE_PRIMARY = 'primary'
    ROLE_SPOUSE = 'spouse'
    ROLE_CHILD = 'child'
    ROLE_FAMILY = 'family'
    ROLE_BUSINESS = 'business'
    ROLE_OTHER = 'other'

    ROLE_CHOICES = [
        (ROLE_PRIMARY, 'Titular'),
        (ROLE_SPOUSE, 'Cônjuge'),
        (ROLE_CHILD, 'Filho(a)'),
        (ROLE_FAMILY, 'Familiar'),
        (ROLE_BUSINESS, 'Profissional'),
        (ROLE_OTHER, 'Outro'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='contacts',
    )

    name = models.CharField(max_length=150)

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_OTHER,
    )

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    notes = models.TextField(
        blank=True,
        help_text=_('Anotações específicas sobre este contato'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_contact'
        verbose_name = _('Contato do Cliente')
        verbose_name_plural = _('Contatos do Cliente')
        indexes = [
            models.Index(fields=['client', 'role']),
        ]
        ordering = ['role', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_role_display()})"