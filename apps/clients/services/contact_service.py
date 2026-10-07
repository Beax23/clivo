"""
ContactService — CRUD de contatos do cliente.
"""

from typing import List, Optional

from apps.clients.models import Client, ClientContact
from apps.clients.exceptions import ContactNotFoundError


class ContactService:

    @staticmethod
    def list_for_client(client: Client) -> List[ClientContact]:
        return list(
            ClientContact.objects.filter(client=client).order_by('role', 'name')
        )

    @staticmethod
    def get_for_client(client: Client, contact_id) -> ClientContact:
        try:
            return ClientContact.objects.get(id=contact_id, client=client)
        except (ClientContact.DoesNotExist, ValueError):
            raise ContactNotFoundError('Contato não encontrado')

    @staticmethod
    def create_contact(
        client: Client,
        name: str,
        role: str = 'other',
        email: str = '',
        phone: str = '',
        notes: str = '',
    ) -> ClientContact:
        name = (name or '').strip()
        if not name:
            raise ValueError('O nome do contato é obrigatório')

        return ClientContact.objects.create(
            client=client,
            name=name,
            role=role,
            email=(email or '').strip().lower(),
            phone=(phone or '').strip(),
            notes=(notes or '').strip(),
        )

    @staticmethod
    def update_contact(
        contact: ClientContact,
        name: Optional[str] = None,
        role: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ClientContact:
        fields = []

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError('O nome do contato é obrigatório')
            contact.name = name
            fields.append('name')

        if role is not None:
            contact.role = role
            fields.append('role')

        if email is not None:
            contact.email = (email or '').strip().lower()
            fields.append('email')

        if phone is not None:
            contact.phone = (phone or '').strip()
            fields.append('phone')

        if notes is not None:
            contact.notes = (notes or '').strip()
            fields.append('notes')

        if fields:
            contact.save(update_fields=fields + ['updated_at'])

        return contact

    @staticmethod
    def delete_contact(contact: ClientContact) -> None:
        contact.delete()