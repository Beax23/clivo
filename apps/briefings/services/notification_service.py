"""
NotificationService — envio de e-mails de conclusão e de
complementares.

REGRA ARQUITETURAL
------------------
Duas notificações distintas:

1. Conclusão do bloco ORIGINAL (on_briefing_completed)
   Idempotência: `BriefingEvent(kind='completion_email_sent')`.
   Já existia antes.

2. Perguntas complementares (on_supplementary_questions_added)
   Disparado EXPLICITAMENTE pelo arquiteto via endpoint
   `POST /api/briefings/{id}/notify-supplementary/`. Não é
   automático ao adicionar pergunta.

NOTIFICAÇÃO ≠ ENTREGA
---------------------
O botão do arquiteto só mostra sucesso quando o SMTP ACEITOU o
envio (resultado `1` do EmailService). Não temos confirmação de
entrega (bounce). Gravamos 3 estados:

    requested   → antes do envio
    accepted    → SMTP aceitou (resultado > 0)
    failed      → exceção ou resultado 0

NUNCA gravamos 'delivered'. Confirmação de entrega exigiria webhook
de bounce, fora do escopo desta versão.

WHATSAPP
--------
No-op com log explícito. Não existe integração WhatsApp configurada
em `integrations`. Se um dia existir, o gancho está preparado.
"""

import logging

from django.db import transaction

from apps.briefings.models import Briefing, BriefingEvent
from apps.briefings.services.event_service import BriefingEventService

logger = logging.getLogger('briefings')


class NotificationService:

    KIND_COMPLETION = BriefingEvent.KIND_COMPLETION_EMAIL_SENT
    KIND_SUPPLEMENTARY = BriefingEvent.KIND_SUPPLEMENTARY_NOTIFICATION_SENT

    # ==================================================================
    # CONCLUSÃO DO BLOCO ORIGINAL
    # ==================================================================

    @staticmethod
    def on_briefing_completed(briefing_id) -> bool:
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

        if NotificationService._already_notified(
            briefing, NotificationService.KIND_COMPLETION,
        ):
            logger.info(
                'Briefing %s já teve e-mail de conclusão enviado, '
                'ignorando', briefing_id,
            )
            return False

        try:
            NotificationService._send_completion(briefing)
        except Exception:
            logger.exception(
                'Falha ao enviar e-mail de conclusão '
                '(briefing=%s). Evento de idempotência NÃO foi '
                'gravado — retentativa é possível.',
                briefing_id,
            )
            return False

        BriefingEventService.log(
            briefing=briefing,
            kind=NotificationService.KIND_COMPLETION,
            user=None,
            portal_session=None,
            content={
                'architect_email': briefing.created_by.email
                    if briefing.created_by else None,
                'client_email': briefing.client.email or None,
            },
        )
        logger.info(
            'E-mail de conclusão enviado (briefing=%s)', briefing_id,
        )
        return True

    # ==================================================================
    # COMPLEMENTARES — solicitação explícita do arquiteto
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def on_supplementary_questions_added(
        briefing_id,
        *,
        actor=None,
    ) -> dict:
        """
        Envia notificação ao cliente sobre perguntas complementares.

        Retorna:
            {
                'sent': bool,
                'to': str,
                'event_id': str | None,
                'status': 'requested' | 'accepted' | 'failed',
                'error_message': str | None,
            }

        `status`:
            requested  → event registrado, envio em curso
            accepted   → SMTP aceitou
            failed     → SMTP recusou (exceção ou retorno 0)

        Nunca retorna 'delivered' — não temos confirmação de entrega.
        """
        try:
            briefing = Briefing.objects.select_related(
                'client', 'workspace', 'created_by',
            ).get(id=briefing_id)
        except Briefing.DoesNotExist:
            logger.warning(
                'Briefing %s não existe em '
                'on_supplementary_questions_added',
                briefing_id,
            )
            return {
                'sent': False,
                'to': '',
                'event_id': None,
                'status': 'failed',
                'error_message': 'Briefing não encontrado.',
            }

        questions = briefing.supplementary_questions()
        if not questions:
            return {
                'sent': False,
                'to': '',
                'event_id': None,
                'status': 'failed',
                'error_message': (
                    'Este briefing não tem perguntas complementares.'
                ),
            }

        target_email = (briefing.client.email or '').strip()
        if not target_email:
            return {
                'sent': False,
                'to': '',
                'event_id': None,
                'status': 'failed',
                'error_message': 'Cliente sem e-mail cadastrado.',
            }

        active_instance_ids = set()
        for q in questions:
            qid = str(q.get('id') or '')
            if qid:
                active_instance_ids.add(qid)

        already_sent = NotificationService._supplementary_already_sent(
            briefing, active_instance_ids,
        )
        if already_sent:
            logger.info(
                'Briefing %s já teve complementares notificadas para o '
                'batch atual. Ignorando.', briefing_id,
            )
            return {
                'sent': False,
                'to': target_email,
                'event_id': None,
                'status': 'accepted',
                'error_message': None,
            }

        requested_event = BriefingEventService.log(
            briefing=briefing,
            kind=NotificationService.KIND_SUPPLEMENTARY,
            user=actor if (
                actor and getattr(actor, 'is_authenticated', False)
            ) else None,
            content={
                'status': 'requested',
                'instance_ids': sorted(active_instance_ids),
                'to': target_email,
            },
        )

        whatsapp_sent, whatsapp_reason = (
            NotificationService._send_whatsapp_if_available(briefing)
        )

        try:
            NotificationService._send_supplementary_email(
                briefing, questions, target_email,
            )
        except Exception as exc:
            logger.exception(
                'Falha ao enviar e-mail de complementares '
                '(briefing=%s)', briefing_id,
            )
            BriefingEventService.log(
                briefing=briefing,
                kind=NotificationService.KIND_SUPPLEMENTARY,
                user=None,
                content={
                    'status': 'failed',
                    'instance_ids': sorted(active_instance_ids),
                    'to': target_email,
                    'error_message': str(exc)[:1000],
                    'whatsapp_status': (
                        'sent' if whatsapp_sent else 'skipped'
                    ),
                    'whatsapp_reason': whatsapp_reason,
                },
            )
            return {
                'sent': False,
                'to': target_email,
                'event_id': str(requested_event.id),
                'status': 'failed',
                'error_message': str(exc),
            }

        BriefingEventService.log(
            briefing=briefing,
            kind=NotificationService.KIND_SUPPLEMENTARY,
            user=None,
            content={
                'status': 'accepted',
                'instance_ids': sorted(active_instance_ids),
                'to': target_email,
                'whatsapp_status': (
                    'sent' if whatsapp_sent else 'skipped'
                ),
                'whatsapp_reason': whatsapp_reason,
            },
        )

        logger.info(
            'E-mail de complementares enviado (briefing=%s, to=%s)',
            briefing_id, target_email,
        )

        return {
            'sent': True,
            'to': target_email,
            'event_id': str(requested_event.id),
            'status': 'accepted',
            'error_message': None,
        }

    # ==================================================================
    # INTERNO
    # ==================================================================

    @staticmethod
    def _already_notified(briefing: Briefing, kind: str) -> bool:
        return BriefingEvent.objects.filter(
            briefing=briefing, kind=kind,
        ).exists()

    @staticmethod
    def _supplementary_already_sent(
        briefing: Briefing,
        active_instance_ids: set,
    ) -> bool:
        """
        Verifica se o batch atual (instance_ids ativos) já recebeu
        notificação bem-sucedida (status='accepted').

        A notificação é considerada "já enviada" quando existe um
        evento `supplementary_notification_sent` com `status='accepted'`
        cujos `instance_ids` são exatamente os mesmos do batch atual.

        Se o batch mudou (pergunta adicionada/removida), a notificação
        anterior não cobre o novo estado e o arquiteto pode reenviar.
        """
        if not active_instance_ids:
            return False

        events = BriefingEvent.objects.filter(
            briefing=briefing,
            kind=NotificationService.KIND_SUPPLEMENTARY,
        ).order_by('-created_at')

        for event in events:
            content = event.content or {}
            if content.get('status') != 'accepted':
                continue
            sent_ids = set(content.get('instance_ids') or [])
            if sent_ids == active_instance_ids:
                return True

        return False

    @staticmethod
    def _send_completion(briefing: Briefing) -> None:
        from apps.accounts.services.email import EmailService

        architect_email = (
            briefing.created_by.email
            if briefing.created_by else None
        )

        client_pdf_bytes = None
        client_pdf_filename = None
        try:
            from apps.briefings.services.export_service import (
                BriefingExportService,
            )
            client_pdf_bytes, client_pdf_filename = (
                BriefingExportService.render_pdf(
                    briefing,
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
    def _send_supplementary_email(
        briefing: Briefing,
        questions: list,
        target_email: str,
    ) -> None:
        from apps.accounts.services.email import EmailService
        from django.conf import settings

        site_name = getattr(settings, 'SITE_NAME', 'Clivo')
        portal_url = NotificationService._supplementary_portal_url(briefing)

        count = len(questions)
        plural = 'perguntas' if count > 1 else 'pergunta'

        subject = (
            f'Novas {plural} no seu briefing — {briefing.title}'
        )

        lines = [
            f'Olá, {briefing.client.name}!',
            '',
            f'O arquiteto adicionou {count} {plural} complementar(es) '
            f'ao briefing "{briefing.title}".',
            '',
            'Para ver e responder, acesse:',
            portal_url,
            '',
            f'— {site_name}',
        ]

        EmailService.send(
            to=target_email,
            subject=subject,
            text='\n'.join(lines),
        )

    @staticmethod
    def _send_whatsapp_if_available(briefing: Briefing):
        """
        Gancho para envio via WhatsApp.

        Hoje: no-op com log explícito. Não existe integração WhatsApp
        configurada em `integrations`. Não simulamos envio.

        Retorna (sent: bool, reason: str).
        """
        try:
            from apps.integrations.models import WorkspaceIntegration
            has_whatsapp = WorkspaceIntegration.objects.filter(
                workspace=briefing.workspace,
                provider__key='whatsapp',
                status=WorkspaceIntegration.STATUS_ACTIVE,
            ).exists()
        except Exception:
            logger.exception(
                'Falha ao verificar integração WhatsApp (briefing=%s)',
                briefing.id,
            )
            return (False, 'whatsapp_check_error')

        if not has_whatsapp:
            return (False, 'no_whatsapp_provider_configured')

        logger.warning(
            'Integração WhatsApp existe para workspace=%s, mas o '
            'adaptador de envio não está implementado nesta versão. '
            'Nenhuma mensagem foi enviada.',
            briefing.workspace_id,
        )
        return (False, 'whatsapp_adapter_not_implemented')

    @staticmethod
    def _portal_url(briefing: Briefing) -> str:
        from django.conf import settings
        frontend_url = getattr(
            settings, 'FRONTEND_URL', ''
        ).rstrip('/')
        if not frontend_url:
            return ''
        return f'{frontend_url}/'

    @staticmethod
    def _supplementary_portal_url(briefing: Briefing) -> str:
        from django.conf import settings
        frontend_url = getattr(
            settings, 'FRONTEND_URL', ''
        ).rstrip('/')
        if not frontend_url:
            return ''
        return f'{frontend_url}/portal/briefings/{briefing.id}/'