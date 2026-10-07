from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.accounts.services.session import SessionService


@receiver(user_logged_in)
def ensure_user_session(sender, request, user, **kwargs):
    """
    Garante que toda vez que o Django registrar um login
    (via allauth/Google redirect, via LoginView, ou qualquer outro caminho),
    exista um UserSession correspondente.
    
    O tipo de sessão é determinado por:
    1. request.session['_clivo_session_type'] (definido antes do login)
    2. 'app' (fallback)
    """
    session_type = request.session.get(
        '_clivo_session_type',
        'app'
    )

    SessionService.ensure_session(
        request=request,
        user=user,
        session_type=session_type,
    )