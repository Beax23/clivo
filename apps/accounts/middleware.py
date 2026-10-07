"""
Middleware do módulo accounts para gerenciamento de sessões.
"""

from django.utils.deprecation import MiddlewareMixin
from apps.accounts.services.session import SessionService


class SessionTrackingMiddleware(MiddlewareMixin):
    """
    Middleware para rastrear sessões ativas.
    
    Atualiza o last_seen_at da sessão a cada requisição,
    mas com throttling para evitar writes excessivos.
    """
    
    def process_request(self, request):
        if request.user.is_authenticated and request.session.session_key:
            SessionService.update_last_seen(request.session.session_key)