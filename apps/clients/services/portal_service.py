"""
PortalService — acesso operacional do Portal do Cliente.

Responsável por:
    - autenticar via token (sessão)
    - registrar acesso
    - revogar sessões
    - emitir eventos

NÃO envia email. Isso é PortalInvitationService.
"""

from typing import List, Optional

from django.utils import timezone

from apps.clients.models import (
    Client,
    ClientPortalAccess,
    ClientPortalSession,
    ClientPortalFeedback,
)
from apps.clients.exceptions import (
    PortalSessionError,
    PortalSessionExpiredError,
)
from apps.clients.events import ClientEventEmitter


class PortalService:

    # ------------------------------------------------------------------
    # AUTENTICAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def open_session_with_token(raw_token: str, request) -> ClientPortalSession:
        """
        Valida o token cru e cria/retorna a sessão, registrando o acesso.
        """
        session = ClientPortalSession.find_by_raw_token(raw_token)
        if session is None:
            raise PortalSessionError('Token inválido')

        if not session.is_valid():
            raise PortalSessionExpiredError('Sessão expirada ou revogada')

        session.touch()
        PortalService._register_access(session, request)
        ClientEventEmitter.portal_opened(
            client=session.client, request=request,
        )
        return session

    @staticmethod
    def revoke_session(session: ClientPortalSession) -> None:
        session.revoke()

    @staticmethod
    def list_active_sessions(client: Client) -> List[ClientPortalSession]:
        return list(
            ClientPortalSession.objects
            .filter(client=client, revoked_at__isnull=True)
            .order_by('-created_at')
        )

    @staticmethod
    def get_session_or_none(session_id) -> Optional[ClientPortalSession]:
        try:
            return ClientPortalSession.objects.select_related('client').get(
                id=session_id
            )
        except (ClientPortalSession.DoesNotExist, ValueError):
            return None

    # ------------------------------------------------------------------
    # FEEDBACK DO PORTAL
    # ------------------------------------------------------------------

    @staticmethod
    def submit_feedback(
        client: Client,
        kind: str,
        message: str = '',
        rating: str = '',
        page: str = '',
        request=None,
    ) -> ClientPortalFeedback:
        feedback = ClientPortalFeedback.objects.create(
            client=client,
            kind=kind,
            message=(message or '').strip(),
            rating=rating or '',
            page=(page or '').strip(),
        )
        ClientEventEmitter.portal_feedback_received(
            client=client, feedback=feedback, request=request,
        )
        return feedback

    @staticmethod
    def list_feedbacks(client: Client) -> List[ClientPortalFeedback]:
        return list(
            ClientPortalFeedback.objects
            .filter(client=client)
            .order_by('-created_at')
        )

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    @staticmethod
    def _register_access(session: ClientPortalSession, request) -> ClientPortalAccess:
        return ClientPortalAccess.objects.create(
            client=session.client,
            session=session,
            ip_address=request.META.get('REMOTE_ADDR') if request else None,
            user_agent=(request.META.get('HTTP_USER_AGENT', '')[:255] if request else ''),
        )