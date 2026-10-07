"""
PortalInvitationService — envia o acesso do Portal por email.

REGRAS:
    - Não usa SMTP diretamente. Delega ao `EmailService.send()`.
    - Reenvio REVOGA todas as sessões anteriores do cliente.
      Só o último link enviado permanece válido.
    - A invitation nasce como `pending`, vira `sent` ou `failed`.
    - NUNCA retorna o token cru na resposta da API.
    - NUNCA vaza detalhes de infraestrutura em erro 500.
"""

from typing import Optional
import logging

from django.conf import settings
from django.utils import timezone

from apps.clients.models import (
    Client,
    ClientPortalInvitation,
    ClientPortalSession,
)
from apps.clients.exceptions import PortalEmailMissingError
from apps.clients.events import ClientEventEmitter
from apps.accounts.services.email import EmailService

logger = logging.getLogger('clients')


class PortalInvitationService:

    DEFAULT_SESSION_TTL_MINUTES = 30

    @staticmethod
    def send_access(
        client: Client,
        actor,
        request=None,
        ttl_minutes: Optional[int] = None,
    ) -> ClientPortalInvitation:
        """
        Gera uma sessão temporária e envia o link por email.

        Passos:
            1. Valida email do cliente
            2. Revoga TODAS as sessões ativas anteriores do cliente
               (reenvio invalida links antigos)
            3. Cria nova ClientPortalSession (token cru só em memória)
            4. Cria ClientPortalInvitation como `pending`
            5. Envia email via EmailService.send()
            6. Marca invitation como `sent` ou `failed`

        Se o envio falhar:
            - invitation fica `failed`
            - a sessão recém-criada é REVOGADA
            - a exceção é propagada (view trata sem vazar detalhe)
        """
        if not client.email:
            raise PortalEmailMissingError(
                'O cliente não possui email cadastrado.'
            )

        # 1. Revoga sessões anteriores — reenvio invalida links antigos
        PortalInvitationService._revoke_all_active_sessions(client)

        # 2. Nova sessão
        session, raw_token = ClientPortalSession.issue(
            client=client,
            ttl_minutes=ttl_minutes or PortalInvitationService.DEFAULT_SESSION_TTL_MINUTES,
        )

        # 3. Invitation como pending
        invitation = ClientPortalInvitation.objects.create(
            client=client,
            session=session,
            email=client.email,
            sent_by=actor if actor and actor.is_authenticated else None,
            status=ClientPortalInvitation.STATUS_PENDING,
        )

        # 4. Envio
        try:
            PortalInvitationService._send_email(
                client=client,
                raw_token=raw_token,
                expires_at=session.expires_at,
            )
        except Exception as exc:
            # Falha: revoga a sessão e marca invitation como failed
            invitation.status = ClientPortalInvitation.STATUS_FAILED
            invitation.error_message = str(exc)
            invitation.save(update_fields=['status', 'error_message'])

            session.revoke()

            logger.exception(
                "Falha ao enviar acesso do Portal para client_id=%s email=%s",
                client.id,
                client.email,
            )
            raise

        # 5. Sucesso
        invitation.status = ClientPortalInvitation.STATUS_SENT
        invitation.save(update_fields=['status'])

        ClientEventEmitter.portal_invitation_sent(
            client=client, actor=actor, request=request,
        )
        return invitation

    # ------------------------------------------------------------------
    # REVOGAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def _revoke_all_active_sessions(client: Client) -> int:
        """
        Revoga todas as sessões ativas (não revogadas e ainda não expiradas).

        Retorna quantas foram revogadas.
        """
        now = timezone.now()
        qs = ClientPortalSession.objects.filter(
            client=client,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        count = qs.count()
        if count:
            qs.update(revoked_at=now)
        return count

    # ------------------------------------------------------------------
    # EMAIL
    # ------------------------------------------------------------------

    @staticmethod
    def _send_email(client: Client, raw_token: str, expires_at):
        """
        Envia o email via EmailService (infra compartilhada).

        NÃO importa `django.core.mail` diretamente.
        """
        frontend_url = getattr(
            settings, 'FRONTEND_URL', 'http://localhost:9000'
        ).rstrip('/')
        portal_url = f"{frontend_url}/portal/{client.public_code}/?t={raw_token}"

        subject = f'Seu acesso ao espaço do {client.name} — Clivo'
        text_body = (
            f'Olá,\n\n'
            f'Você recebeu acesso ao espaço de {client.name} no Clivo.\n\n'
            f'Abra o link abaixo para entrar:\n{portal_url}\n\n'
            f'Este link expira em {expires_at.strftime("%d/%m/%Y %H:%M")}.\n\n'
            f'Equipe Clivo'
        )
        html_body = (
            f'<p>Olá,</p>'
            f'<p>Você recebeu acesso ao espaço de <strong>{client.name}</strong> no Clivo.</p>'
            f'<p><a href="{portal_url}">Abrir meu espaço</a></p>'
            f'<p>Este link expira em {expires_at.strftime("%d/%m/%Y %H:%M")}.</p>'
            f'<p>Equipe Clivo</p>'
        )

        EmailService.send(
            to=client.email,
            subject=subject,
            text=text_body,
            html=html_body,
        )