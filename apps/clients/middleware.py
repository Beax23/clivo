"""
ClientPortalMiddleware — resolve a sessão do Portal do Cliente.

O cliente autentica no Portal via código público (public_code).
Após o login, guardamos um cookie `clivo_portal` com o token cru.

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

        # Log apenas em DEBUG — silencioso em produção
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Portal middleware: cookie '%s' %s — path=%s",
                PORTAL_COOKIE_NAME,
                'PRESENTE' if raw else 'AUSENTE',
                request.path,
            )

        if raw:
            try:
                session = ClientPortalSession.find_by_raw_token(raw)

                if session is None:
                    logger.debug(
                        "Portal middleware: token não encontrado no banco "
                        "(path=%s)", request.path,
                    )
                elif not session.is_valid():
                    logger.debug(
                        "Portal middleware: sessão inválida (revoked=%s, "
                        "expires=%s) — path=%s",
                        session.revoked_at,
                        session.expires_at,
                        request.path,
                    )
                else:
                    request.portal_session = session
                    request.portal_client = session.client
                    logger.debug(
                        "Portal middleware: sessão resolvida para client=%s "
                        "(path=%s)", session.client_id, request.path,
                    )
            except Exception:
                logger.exception(
                    "Falha ao resolver sessão do Portal (path=%s)",
                    request.path,
                )

        return self.get_response(request)