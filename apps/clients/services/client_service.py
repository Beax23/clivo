"""
ClientService — ciclo de vida do Client.

AUDITORIA DO ENVIO DE ACESSO
----------------------------
`create_client` envia o e-mail com o código de acesso e o link do
portal. Para que esse envio seja RASTREÁVEL (mesmo padrão do
`PortalInvitationService`), gravamos um `ClientPortalInvitation`
com `status='sent'` ou `status='failed'`.

IMPORTANTE: aqui NÃO criamos `ClientPortalSession` nem revogamos
sessões antigas. O cliente entra no portal digitando o código
(`POST /api/portal/login/`). O envio com token/sessão é
responsabilidade do `PortalInvitationService` (ação
`POST /api/clients/{id}/portal/send-access/`), que é um fluxo
diferente e deliberado.

Falha de envio NÃO falha a criação do cliente. O registro auditável
fica como `failed` e o arquiteto pode reenviar depois.
"""

from typing import Optional

from django.conf import settings
from django.db import transaction

from apps.clients.models import (
    Client,
    ClientPortalInvitation,
)
from apps.clients.services.public_code import generate_unique_public_code
from apps.clients.exceptions import (
    ClientDuplicateEmailError,
    ClientNotFoundError,
)
from apps.clients.events import ClientEventEmitter


class ClientService:

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_client(
        workspace,
        name: str,
        created_by,
        email: str = '',
        phone: str = '',
        request=None,
    ) -> Client:
        name = (name or '').strip()
        if not name:
            raise ValueError('O nome do cliente é obrigatório')

        email = (email or '').strip().lower()

        if email and Client.objects.filter(
            workspace=workspace,
            email__iexact=email,
        ).exists():
            raise ClientDuplicateEmailError(
                'Já existe um cliente com este email neste workspace'
            )

        client = Client.objects.create(
            workspace=workspace,
            public_code=generate_unique_public_code(),
            name=name,
            email=email,
            phone=(phone or '').strip(),
            created_by=created_by,
        )

        ClientEventEmitter.client_created(
            client=client, actor=created_by, request=request,
        )

        # Envio do código de acesso — fora da atomicidade do cliente.
        # Falha de envio não reverte a criação.
        if client.email:
            ClientService._send_access_code(
                client=client,
                actor=created_by,
            )

        return client

    # ------------------------------------------------------------------
    # ENVIO DO CÓDIGO DE ACESSO (com auditoria)
    # ------------------------------------------------------------------

    @staticmethod
    def _send_access_code(*, client: Client, actor=None) -> None:
        """
        Envia o e-mail com `public_code` + link do portal e grava
        um `ClientPortalInvitation` com o resultado.

        NÃO cria sessão. NÃO revoga sessões. O cliente digita o
        código na tela do portal.
        """
        from apps.accounts.services.email import EmailService

        target_email = (client.email or '').strip()
        if not target_email:
            return

        frontend_url = (
            getattr(settings, 'FRONTEND_URL', '') or
            'https://clivoos.com'
        ).rstrip('/')
        # O portal é acessado em /portal/ — o cliente digita o código
        # lá. NÃO colocar o código no path.
        portal_url = f'{frontend_url}/portal/'

        invitation = ClientPortalInvitation.objects.create(
            client=client,
            session=None,
            email=target_email,
            sent_by=(
                actor if (actor and getattr(actor, 'is_authenticated', False))
                else None
            ),
            status=ClientPortalInvitation.STATUS_PENDING,
        )

        try:
            EmailService.send_client_code_email(
                client=client,
                workspace=client.workspace,
                portal_url=portal_url,
            )
        except Exception as exc:
            invitation.status = ClientPortalInvitation.STATUS_FAILED
            invitation.error_message = str(exc)[:2000]
            invitation.save(update_fields=['status', 'error_message'])
            import logging
            logging.getLogger('clients').exception(
                'Falha ao enviar código de acesso para client_id=%s '
                'email=%s', client.id, target_email,
            )
            return

        invitation.status = ClientPortalInvitation.STATUS_SENT
        invitation.save(update_fields=['status'])

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id(client_id) -> Optional[Client]:
        try:
            return Client.objects.select_related('workspace').get(id=client_id)
        except (Client.DoesNotExist, ValueError):
            return None

    @staticmethod
    def get_by_public_code(code: str) -> Optional[Client]:
        try:
            return Client.objects.select_related('workspace').get(
                public_code=code
            )
        except Client.DoesNotExist:
            return None

    @staticmethod
    def list_for_workspace(workspace):
        """
        Lista TODOS os clientes do workspace.

        Não filtra por status. Filtros por status são responsabilidade
        da camada de apresentação/frontend.
        """
        return (
            Client.objects
            .filter(workspace=workspace)
            .order_by('-created_at')
        )

    # ------------------------------------------------------------------
    # ATUALIZAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def update_client(
        client: Client,
        actor,
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        status: Optional[str] = None,
        request=None,
    ) -> Client:
        changes = {}

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError('O nome do cliente é obrigatório')
            if client.name != name:
                client.name = name
                changes['name'] = True

        if email is not None:
            email = (email or '').strip().lower()
            if email and email != client.email:
                if Client.objects.filter(
                    workspace=client.workspace,
                    email__iexact=email,
                ).exclude(pk=client.pk).exists():
                    raise ClientDuplicateEmailError(
                        'Já existe um cliente com este email neste workspace'
                    )
                client.email = email
                changes['email'] = True

        if phone is not None:
            phone = (phone or '').strip()
            if client.phone != phone:
                client.phone = phone
                changes['phone'] = True

        if status is not None:
            if status not in dict(Client.STATUS_CHOICES):
                raise ValueError(f'Status inválido: {status}')
            if client.status != status:
                client.status = status
                changes['status'] = True

        if changes:
            client.save(update_fields=list(changes.keys()) + ['updated_at'])
            ClientEventEmitter.client_updated(
                client=client,
                changes=changes,
                actor=actor,
                request=request,
            )

        return client

    @staticmethod
    @transaction.atomic
    def update_context(client: Client, context: dict, actor=None, request=None) -> Client:
        client.context = context or {}
        client.save(update_fields=['context', 'updated_at'])
        ClientEventEmitter.client_updated(
            client=client,
            changes={'context': True},
            actor=actor,
            request=request,
        )
        return client

    # ------------------------------------------------------------------
    # EXCLUSÃO — DELETE REAL
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete_client(client: Client, actor=None, request=None) -> None:
        """
        Exclui o cliente. CASCADE cuida das relações.

        NÃO existe soft delete. NÃO existe restore.
        """
        client_id = client.id
        client_name = client.name
        client.delete()
        ClientEventEmitter.client_deleted(
            client_id=client_id,
            client_name=client_name,
            actor=actor,
            request=request,
        )