"""
ClientPortalMiddleware — resolve a sessão do Portal do Cliente.

O cliente autentica no Portal via link com token. Após o primeiro
acesso, guardamos um cookie `clivo_portal` com o token cru.

Este middleware:
    1. Lê o cookie `clivo_portal`
    2. Resolve ClientPortalSession pelo hash
    3. Valida expiração
    4. Popula `request.portal_session` e `request.portal_client`

Não cria sessão. Não autentica. Apenas resolve o contexto.
"""

import logging

from apps.clients.models import ClientPortalSession

logger = logging.getLogger('clients')

PORTAL_COOKIE_NAME = 'clivo_portal'


class ClientPortalMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal_session = None
        request.portal_client = None

        raw = request.COOKIES.get(PORTAL_COOKIE_NAME)
        if raw:
            try:
                session = ClientPortalSession.find_by_raw_token(raw)
                if session and session.is_valid():
                    request.portal_session = session
                    request.portal_client = session.client
            except Exception:
                logger.exception("Falha ao resolver sessão do Portal")

        return self.get_response(request)