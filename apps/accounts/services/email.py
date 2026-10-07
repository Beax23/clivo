from django.core.mail import EmailMultiAlternatives
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

        from django.core.mail import send_mail
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