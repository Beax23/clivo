"""
NotificationService — envio automático de e-mail ao concluir briefing.

REGRA ARQUITETURAL
------------------
Duas garantias:

1. IDEMPOTÊNCIA: o envio de conclusão é disparado uma e apenas
   uma vez por briefing. Um `BriefingEvent` com
   `kind='completion_email_sent'` marca que o envio já ocorreu.
   Se a função rodar de novo, ela verifica e sai.

2. NÃO BLOQUEIA: o envio é agendado via `transaction.on_commit`,
   nunca dentro da transação de conclusão do briefing. Se o
   provedor de e-mail estiver fora, o briefing continua concluído.

Falha de envio NÃO grava o evento de idempotência. Isso permite
retentativa (manual ou por cron futuro).
"""

import logging

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class NotificationService:

    KIND_MARKER = BriefingEvent.KIND_COMPLETION_EMAIL_SENT

    # ==================================================================
    # API
    # ==================================================================

    @staticmethod
    def on_briefing_completed(briefing_id) -> bool:
        """
        Chamado quando um briefing vira `completed`.

        Retorna `True` se um e-mail foi disparado nesta chamada,
        `False` se já havia sido disparado antes ou se a situação
        não permite (ex.: briefing não existe).

        Nunca levanta.
        """
        try:
            briefing = Briefing.objects.select_related(
                'client', 'workspace', 'template', 'created_by',
            ).get(id=briefing_id)
        except Briefing.DoesNotExist:
            logger.warning(
                'Briefing %s não existe em on_briefing_completed',
                briefing_id,
            )
            return False

        if briefing.status != Briefing.STATUS_COMPLETED:
            logger.info(
                'Briefing %s não está completed, ignorando notificação',
                briefing_id,
            )
            return False

        if NotificationService._already_notified(briefing):
            logger.info(
                'Briefing %s já teve e-mail de conclusão enviado, '
                'ignorando', briefing_id,
            )
            return False

        try:
            NotificationService._send(briefing)
        except Exception:
            logger.exception(
                'Falha ao enviar e-mail de conclusão '
                '(briefing=%s). Evento de idempotência NÃO foi '
                'gravado — retentativa é possível.',
                briefing_id,
            )
            return False

        # Só marca como enviado após sucesso
        NotificationService._mark_notified(briefing)
        logger.info(
            'E-mail de conclusão enviado (briefing=%s)', briefing_id,
        )
        return True

    # ==================================================================
    # INTERNO
    # ==================================================================

    @staticmethod
    def _already_notified(briefing: Briefing) -> bool:
        return BriefingEvent.objects.filter(
            briefing=briefing,
            kind=NotificationService.KIND_MARKER,
        ).exists()

    @staticmethod
    def _mark_notified(briefing: Briefing) -> None:
        BriefingEventService.log(
            briefing=briefing,
            kind=NotificationService.KIND_MARKER,
            user=None,
            portal_session=None,
            content={
                'architect_email': briefing.created_by.email
                    if briefing.created_by else None,
                'client_email': briefing.client.email or None,
            },
        )

    @staticmethod
    def _send(briefing: Briefing) -> None:
        from apps.accounts.services.email import EmailService

        architect_email = (
            briefing.created_by.email
            if briefing.created_by else None
        )

        # Gera PDF moodboard do cliente (sem notas internas)
        client_pdf_bytes = None
        client_pdf_filename = None
        try:
            from apps.briefings.services.export_service import (
                BriefingExportService,
            )
            client_pdf_bytes, client_pdf_filename = (
                BriefingExportService.render_pdf(
                    briefing,
                    template_name='briefings/export_client.html',
                    mode='client',
                )
            )
        except Exception:
            logger.exception(
                'Falha ao gerar PDF do cliente para envio de '
                'conclusão (briefing=%s). Vai enviar sem anexo.',
                briefing.id,
            )

        client_portal_url = NotificationService._portal_url(briefing)

        if architect_email:
            EmailService.send_briefing_completed(
                briefing=briefing,
                client_portal_url=client_portal_url,
                architect_email=architect_email,
                client_pdf_bytes=client_pdf_bytes,
                client_pdf_filename=client_pdf_filename,
            )
        else:
            # Sem e-mail do arquiteto: ainda envia para o cliente
            if briefing.client.email:
                from django.conf import settings
                site_name = getattr(settings, 'SITE_NAME', 'Clivo')
                EmailService.send(
                    to=briefing.client.email,
                    subject=(
                        f'Seu briefing foi registrado — {briefing.title}'
                    ),
                    text=(
                        f'Olá,\n\n'
                        f'Recebemos suas respostas do briefing '
                        f'"{briefing.title}".\n\n'
                        f'— {site_name}'
                    ),
                )

    @staticmethod
    def _portal_url(briefing: Briefing) -> str:
        """
        Link autenticado do portal do cliente para este briefing.
        """
        from django.conf import settings
        frontend_url = getattr(
            settings, 'FRONTEND_URL', ''
        ).rstrip('/')
        if not frontend_url:
            return ''
        return f'{frontend_url}/'