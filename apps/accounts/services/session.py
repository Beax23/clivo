from typing import Optional, Dict, Any
from django.http import HttpRequest
from django.utils import timezone
from django.contrib.sessions.models import Session
from django.contrib.auth import login, logout
from django.conf import settings

from apps.accounts.models import User, UserSession
from apps.accounts.exceptions.account_exceptions import SessionError


class SessionService:
    """
    Serviço para gerenciamento de sessões do Clivo.
    
    Gerencia:
    - Criação de sessões (App e Console)
    - Rastreamento via UserSession
    - Invalidação de sessões
    
    O Django é a autoridade real de autenticação.
    UserSession é apenas rastreamento/observabilidade.
    """
    
    # Tipos de sessão válidos
    VALID_SESSION_TYPES = {'app', 'console'}
    
    # Intervalo mínimo entre updates do last_seen (5 minutos)
    LAST_SEEN_INTERVAL_SECONDS = 300

    @staticmethod
    def validate_session_type(session_type: str) -> None:
        """Valida se o tipo de sessão é permitido."""
        if session_type not in SessionService.VALID_SESSION_TYPES:
            raise SessionError(f'Tipo de sessão inválido: {session_type}')

    @staticmethod
    def register_session(
        request: HttpRequest,
        user: User,
        session_type: str = 'app'
    ) -> UserSession:
        """
        Registra uma sessão no UserSession (após o login do Django).
        
        Este método é chamado pelo signal user_logged_in.
        Não faz login, apenas registra a sessão.
        """
        SessionService.validate_session_type(session_type)
        
        session_key = request.session.session_key
        
        if not session_key:
            raise SessionError('Sessão Django não encontrada')

        # Remove qualquer UserSession existente com esta chave (segurança)
        UserSession.objects.filter(session_key=session_key).delete()

        # Cria o registro de sessão
        user_session = UserSession.objects.create(
            user=user,
            session_key=session_key,
            session_type=session_type,
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
            expires_at=timezone.now() + timezone.timedelta(
                seconds=settings.SESSION_COOKIE_AGE
            ),
            last_seen_at=timezone.now()
        )

        request.session['user_session_id'] = str(user_session.id)
        request.session['session_type'] = session_type
        
        # Limpa o marcador de sessão
        request.session.pop('_clivo_session_type', None)

        return user_session

    @staticmethod
    def ensure_session(
        request: HttpRequest,
        user: User,
        session_type: str = 'app'
    ) -> UserSession:
        """
        Garante que existe um UserSession para o usuário.
        
        Se já existir, retorna. Se não, cria.
        """
        SessionService.validate_session_type(session_type)

        existing_id = request.session.get('user_session_id')

        if existing_id:
            try:
                user_session = UserSession.objects.get(
                    id=existing_id,
                    user=user,
                    is_active=True
                )
                # Atualiza o tipo se necessário
                if user_session.session_type != session_type:
                    user_session.session_type = session_type
                    user_session.save(update_fields=['session_type'])
                return user_session
            except UserSession.DoesNotExist:
                request.session.pop('user_session_id', None)

        # Não existe → registra
        return SessionService.register_session(request, user, session_type)

    @staticmethod
    def login(
        request: HttpRequest,
        user: User,
        session_type: str = 'app'
    ) -> UserSession:
        """
        Autentica o usuário e garante o registro da sessão.
        
        Este método deve ser usado por todas as views que fazem login.
        """
        if not user.is_active:
            raise SessionError('Conta desativada')

        SessionService.validate_session_type(session_type)

        # Marca o tipo de sessão para o signal (na sessão, para atravessar redirects)
        request.session['_clivo_session_type'] = session_type

        # Faz login - Django gerencia a sessão
        login(request, user)

        # Após o login, o signal já deve ter criado o UserSession
        # Mas garantimos que existe
        user_session = SessionService.ensure_session(request, user, session_type)

        return user_session

    @staticmethod
    def destroy_session(request: HttpRequest) -> None:
        """Destroi a sessão atual."""
        if not request.user.is_authenticated:
            raise SessionError('Usuário não autenticado')

        user_session_id = request.session.get('user_session_id')
        if user_session_id:
            try:
                user_session = UserSession.objects.get(id=user_session_id)
                user_session.is_active = False
                user_session.save(update_fields=['is_active'])
            except UserSession.DoesNotExist:
                pass

        # Remove o marcador de sessão
        request.session.pop('_clivo_session_type', None)
        request.session.pop('user_session_id', None)

        logout(request)

    @staticmethod
    def destroy_all_sessions(user: User, exclude_current: Optional[str] = None) -> int:
        """
        Destroi todas as sessões do usuário, exceto a atual se especificada.
        
        Returns: Número de sessões destruídas.
        """
        sessions = UserSession.objects.filter(
            user=user,
            is_active=True
        )

        if exclude_current:
            sessions = sessions.exclude(session_key=exclude_current)

        session_keys = list(sessions.values_list('session_key', flat=True))
        count = len(session_keys)

        if session_keys:
            # Remove as sessões Django primeiro
            Session.objects.filter(session_key__in=session_keys).delete()
            # Depois marca o UserSession como inativo
            sessions.update(is_active=False)

        return count

    @staticmethod
    def destroy_sessions_by_type(user: User, session_type: str) -> int:
        """
        Destroi todas as sessões de um tipo específico.
        """
        SessionService.validate_session_type(session_type)
        
        sessions = UserSession.objects.filter(
            user=user,
            session_type=session_type,
            is_active=True
        )

        session_keys = list(sessions.values_list('session_key', flat=True))
        count = len(session_keys)

        if session_keys:
            Session.objects.filter(session_key__in=session_keys).delete()
            sessions.update(is_active=False)

        return count

    @staticmethod
    def get_session_info(request: HttpRequest) -> Optional[Dict[str, Any]]:
        """Obtém informações da sessão atual."""
        if not request.user.is_authenticated or not request.session.session_key:
            return None

        user_session_id = request.session.get('user_session_id')

        if user_session_id:
            try:
                user_session = UserSession.objects.get(
                    id=user_session_id,
                    user=request.user,
                    is_active=True
                )
                return {
                    'session_type': user_session.session_type,
                    'created_at': user_session.created_at,
                    'last_seen_at': user_session.last_seen_at,
                    'user_id': request.user.id,
                    'email': request.user.email,
                }
            except UserSession.DoesNotExist:
                pass

        # Inconsistência: sessão autenticada sem UserSession ativo
        return None

    @staticmethod
    def update_last_seen(session_key: str) -> bool:
        """Atualiza o last_seen_at de uma sessão."""
        try:
            user_session = UserSession.objects.get(
                session_key=session_key,
                is_active=True
            )
            
            if user_session.last_seen_at:
                elapsed = (timezone.now() - user_session.last_seen_at).total_seconds()
                if elapsed < SessionService.LAST_SEEN_INTERVAL_SECONDS:
                    return False
            
            user_session.last_seen_at = timezone.now()
            user_session.save(update_fields=['last_seen_at'])
            return True
            
        except UserSession.DoesNotExist:
            return False