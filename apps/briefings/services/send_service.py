"""
SendService — envio manual do briefing pelo arquiteto.

Diferente do NotificationService (automático, apenas em conclusão),
este é acionado pelo arquiteto a qualquer momento:

    - briefing concluído ou não
    - reenvio após ajuste
    - envio para e-mail alternativo

Registra SEMPRE um BriefingEvent `manual_send` com quem enviou,
para quem e quando. Isso torna o reenvio auditável.

REGRA ARQUITETURAL
------------------
- Não gera PDF em modo arquiteto. Sempre em modo cliente,
  sem notas internas.
- Se o envio falhar, o EmailService levanta e o evento NÃO é
  gravado. Isso evita estado inconsistente (marcar como enviado
  um e-mail que nunca saiu).
- Não bloqueia a conclusão do briefing. É uma ação explícita do
  arquiteto, disparada por ele.
"""

import logging

from apps.briefings.models import Briefing
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class BriefingSendService:

    KIND_MANUAL_SEND = 'manual_send'

    @staticmethod
    def send_to_client(
        *,
        briefing: Briefing,
        actor,
        to_email: str = None,
        message: str = '',
        request=None,
    ) -> dict:
        """
        Envia (ou reenvia) o briefing para o cliente.

        Args:
            briefing: execução
            actor: usuário que está enviando (arquiteto/equipe)
            to_email: destinatário. Se None, usa `briefing.client.email`.
            message: texto opcional a ser incluído no corpo
            request: opcional, para correlation_id e detecção de host

        Returns:
            {
                'sent': bool,
                'to': str,
                'event_id': str,
            }

        Levanta BriefingError se não houver e-mail de destino.

        Levanta outras exceções propagadas do EmailService quando o
        envio falhar (smtp down, credencial inválida, etc.).
        """
        from apps.accounts.services.email import EmailService
        from apps.briefings.services.export_service import (
            BriefingExportService,
        )
        from apps.briefings.exceptions import BriefingError

        # ------------------------------------------------------------------
        # 1. Resolve o destinatário
        # ------------------------------------------------------------------

        target_email = (to_email or '').strip() or (
            briefing.client.email or ''
        )
        if not target_email:
            raise BriefingError(
                'Nenhum e-mail de destino. '
                'Informe um endereço ou cadastre um no cliente.'
            )

        # ------------------------------------------------------------------
        # 2. Gera PDF em modo cliente (sem notas internas)
        #
        # Falha na geração NÃO bloqueia o envio. O e-mail ainda é
        # enviado — apenas sem anexo. O evento registra has_pdf=False.
        # ------------------------------------------------------------------

        pdf_bytes = None
        pdf_filename = None
        try:
            pdf_bytes, pdf_filename = BriefingExportService.render_pdf(
                briefing,
                template_name='briefings/export_client.html',
                mode='client',
            )
        except Exception:
            logger.exception(
                'Falha ao gerar PDF para envio manual (briefing=%s). '
                'O e-mail será enviado sem anexo.',
                briefing.id,
            )

        # ------------------------------------------------------------------
        # 3. Resolve URL do portal do cliente
        # ------------------------------------------------------------------

        portal_url = ''
        try:
            from django.conf import settings
            base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
            if base:
                portal_url = f'{base}/'
        except Exception:
            pass

        # ------------------------------------------------------------------
        # 4. Envia o e-mail
        #
        # Se o envio falhar, a exceção sobe. O evento NÃO é gravado.
        # Isso evita marcar como enviado algo que não saiu.
        # ------------------------------------------------------------------

        EmailService.send_briefing_to_client(
            briefing=briefing,
            to_email=target_email,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename,
            message=message,
            client_portal_url=portal_url,
        )

        # ------------------------------------------------------------------
        # 5. Registra o evento (append-only) — só após sucesso do envio
        # ------------------------------------------------------------------

        event = BriefingEventService.log(
            briefing=briefing,
            kind=BriefingSendService.KIND_MANUAL_SEND,
            user=actor,
            content={
                'to': target_email,
                'by': actor.email if actor else None,
                'has_pdf': pdf_bytes is not None,
                'message': message or None,
            },
        )

        logger.info(
            'Briefing %s enviado manualmente para %s por %s',
            briefing.id,
            target_email,
            actor.email if actor else '?',
        )

        return {
            'sent': True,
            'to': target_email,
            'event_id': str(event.id),
        }