from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from typing import Optional, Union, List


class EmailService:
    """
    Serviço para envio de emails do módulo accounts.

    Este é o PONTO ÚNICO de envio transacional de email da plataforma.
    Domínios NÃO devem importar `django.core.mail` diretamente —
    devem chamar `EmailService.send()` ou um dos helpers específicos.

    Responsabilidades:
        - Reset de senha
        - Convite de workspace
        - Envio do código do cliente
        - Notificação de briefing concluído
        - Envio manual de briefing
    """

    # ==================================================================
    # GENERIC SEND
    # ==================================================================

    @staticmethod
    def send(
        to: Union[str, List[str]],
        subject: str,
        text: str = '',
        html: str = '',
        from_email: Optional[str] = None,
        fail_silently: bool = False,
    ):
        """
        Envio genérico de email.

        Args:
            to: lista de emails ou email único
            subject: assunto
            text: corpo texto puro
            html: corpo HTML (opcional)
            from_email: remetente (default: DEFAULT_FROM_EMAIL)
            fail_silently: se True, engole exceções

        Returns:
            Número de emails enviados com sucesso.
        """
        if isinstance(to, str):
            to = [to]

        from_email = from_email or getattr(
            settings, 'DEFAULT_FROM_EMAIL', 'suporte@clivoos.com'
        )

        if html:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text or strip_tags(html),
                from_email=from_email,
                to=to,
            )
            msg.attach_alternative(html, 'text/html')
            return msg.send(fail_silently=fail_silently)

        return send_mail(
            subject=subject,
            message=text,
            from_email=from_email,
            recipient_list=to,
            fail_silently=fail_silently,
        )

    # ==================================================================
    # PASSWORD RESET
    # ==================================================================

    @staticmethod
    def send_password_reset_email(user, token_data: dict, frontend_url: Optional[str] = None):
        frontend_url = frontend_url or getattr(
            settings, 'FRONTEND_URL', 'http://localhost:9000'
        )
        reset_url = (
            f"{frontend_url}/reset-password"
            f"?uid={token_data['uid']}&token={token_data['token']}"
        )

        context = {
            'user': user,
            'reset_url': reset_url,
            'site_name': getattr(settings, 'SITE_NAME', 'Clivo'),
        }

        html_message = render_to_string('accounts/email/password_reset.html', context)
        plain_message = strip_tags(html_message)

        EmailService.send(
            to=user.email,
            subject='Redefinição de senha - Clivo',
            text=plain_message,
            html=html_message,
        )

    # ==================================================================
    # WORKSPACE INVITATION
    # ==================================================================

    @staticmethod
    def send_workspace_invitation(invitation, invite_url: str):
        """
        Envia o email de convite de workspace.

        Args:
            invitation: WorkspaceInvitation
            invite_url: URL completa do convite
        """
        invited_by = invitation.invited_by
        inviter_name = ''
        if invited_by:
            inviter_name = invited_by.full_name or invited_by.email or ''

        workspace = invitation.workspace
        governance = invitation.governance

        context = {
            'invitation': invitation,
            'invite_url': invite_url,
            'workspace': workspace,
            'governance': governance,
            'inviter_name': inviter_name,
            'site_name': getattr(settings, 'SITE_NAME', 'Clivo'),
            'frontend_url': getattr(settings, 'FRONTEND_URL', '').rstrip('/'),
            'expires_at': invitation.expires_at,
        }

        subject = f'{inviter_name or "Alguém"} te convidou para o {workspace.name}'

        html_message = render_to_string('email_convite.html', context)
        plain_message = render_to_string('email_convite.txt', context)

        EmailService.send(
            to=invitation.email,
            subject=subject,
            text=plain_message,
            html=html_message,
        )

    # ==================================================================
    # CLIENT PORTAL CODE
    # ==================================================================

    @staticmethod
    def send_client_code_email(client, workspace, portal_url: str):
        """
        Envia o código do cliente + link do Portal.

        Args:
            client: Client
            workspace: Workspace
            portal_url: URL completa do Portal
        """
        context = {
            'client_name': client.name,
            'workspace_name': workspace.name,
            'public_code': client.public_code,
            'portal_url': portal_url,
            'site_name': getattr(settings, 'SITE_NAME', 'Clivo'),
        }

        subject = f'Seu acesso ao espaço de {client.name} — Clivo'

        html_message = render_to_string('emails/cliente_code.html', context)
        plain_message = strip_tags(html_message)

        EmailService.send(
            to=client.email,
            subject=subject,
            text=plain_message,
            html=html_message,
        )

    # ==================================================================
    # BRIEFING — CONCLUSÃO AUTOMÁTICA
    # ==================================================================

    @staticmethod
    def send_briefing_completed(
        *,
        briefing,
        client_portal_url: str,
        architect_email: str,
        client_pdf_bytes: bytes = None,
        client_pdf_filename: str = None,
    ):
        """
        Envia e-mail de conclusão para o arquiteto e o cliente.

        - Para o arquiteto: link para o painel + notificação.
        - Para o cliente: PDF anexado (moodboard) + link do portal.

        `fail_silently=False` de propósito: quem chama precisa
        tratar falha de envio. A idempotência é responsabilidade
        do chamador (via BriefingEvent).
        """
        frontend_url = getattr(
            settings, 'FRONTEND_URL', ''
        ).rstrip('/')
        site_name = getattr(settings, 'SITE_NAME', 'Clivo')

        # --- Para o arquiteto ---
        subject_arch = f'Briefing "{briefing.title}" concluído'
        text_arch = (
            f'Olá,\n\n'
            f'O cliente {briefing.client.name} concluiu o briefing '
            f'"{briefing.title}".\n\n'
            f'Abra no Clivo: {frontend_url}/fluxo/\n\n'
            f'— {site_name}'
        )
        html_arch = (
            f'<p>Olá,</p>'
            f'<p>O cliente <strong>{briefing.client.name}</strong> '
            f'concluiu o briefing <strong>{briefing.title}</strong>.</p>'
            f'<p><a href="{frontend_url}/fluxo/">Abrir no Clivo</a></p>'
            f'<p>— {site_name}</p>'
        )

        EmailService.send(
            to=architect_email,
            subject=subject_arch,
            text=text_arch,
            html=html_arch,
        )

        # --- Para o cliente ---
        if not briefing.client.email:
            return

        subject_client = f'Seu briefing foi registrado — {briefing.title}'
        text_client = (
            f'Olá,\n\n'
            f'Recebemos suas respostas do briefing "{briefing.title}".\n'
            f'Em anexo está uma cópia para você guardar.\n\n'
        )
        if client_portal_url:
            text_client += f'Você também pode voltar ao portal: {client_portal_url}\n\n'
        text_client += f'— {site_name}'

        html_client = (
            f'<p>Olá,</p>'
            f'<p>Recebemos suas respostas do briefing '
            f'<strong>{briefing.title}</strong>.</p>'
            f'<p>Em anexo está uma cópia para você guardar.</p>'
        )
        if client_portal_url:
            html_client += (
                f'<p><a href="{client_portal_url}">Abrir o portal</a></p>'
            )
        html_client += f'<p>— {site_name}</p>'

        if client_pdf_bytes is not None:
            EmailService._send_with_attachments(
                to=briefing.client.email,
                subject=subject_client,
                text=text_client,
                html=html_client,
                attachments=[(
                    client_pdf_filename or f'briefing-{briefing.id}.pdf',
                    client_pdf_bytes,
                    'application/pdf',
                )],
            )
        else:
            EmailService.send(
                to=briefing.client.email,
                subject=subject_client,
                text=text_client,
                html=html_client,
            )

    # ==================================================================
    # BRIEFING — ENVIO MANUAL
    # ==================================================================

    @staticmethod
    def send_briefing_to_client(
        *,
        briefing,
        to_email: str,
        pdf_bytes: bytes = None,
        pdf_filename: str = None,
        message: str = '',
        client_portal_url: str = '',
    ):
        """
        Envia (ou reenvia) o briefing para o cliente.

        Chamado pelo arquiteto. `to_email` normalmente é o e-mail
        do cliente, mas pode ser outro endereço — o operador
        assume a responsabilidade.
        """
        site_name = getattr(settings, 'SITE_NAME', 'Clivo')

        subject = f'Briefing: {briefing.title}'
        body_intro = (
            message.strip()
            if message and message.strip()
            else 'Segue o briefing solicitado.'
        )

        text = (
            f'Olá,\n\n'
            f'{body_intro}\n\n'
        )
        if client_portal_url:
            text += f'Acesse o portal: {client_portal_url}\n\n'
        text += f'— {site_name}'

        html = (
            f'<p>Olá,</p>'
            f'<p>{body_intro}</p>'
        )
        if client_portal_url:
            html += f'<p><a href="{client_portal_url}">Abrir o portal</a></p>'
        html += f'<p>— {site_name}</p>'

        if pdf_bytes is not None:
            EmailService._send_with_attachments(
                to=to_email,
                subject=subject,
                text=text,
                html=html,
                attachments=[(
                    pdf_filename or f'briefing-{briefing.id}.pdf',
                    pdf_bytes,
                    'application/pdf',
                )],
            )
        else:
            EmailService.send(
                to=to_email,
                subject=subject,
                text=text,
                html=html,
            )

    # ==================================================================
    # INTERNO — envio com anexos
    # ==================================================================

    @staticmethod
    def _send_with_attachments(
        *,
        to,
        subject: str,
        text: str,
        html: str,
        attachments: list = None,
        from_email: str = None,
        fail_silently: bool = False,
    ):
        """
        Envia e-mail com anexos em memória.

        `attachments` é uma lista de tuplas:
            (filename, bytes, mimetype)
        """
        if isinstance(to, str):
            to = [to]

        from_email = from_email or getattr(
            settings, 'DEFAULT_FROM_EMAIL', 'suporte@clivoos.com'
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=from_email,
            to=to,
        )
        if html:
            msg.attach_alternative(html, 'text/html')

        for fname, data, mime in (attachments or []):
            msg.attach(fname, data, mime)

        return msg.send(fail_silently=fail_silently)