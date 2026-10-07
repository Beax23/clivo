class AccountError(Exception):
    """Exceção base para o módulo accounts."""
    pass


class AuthenticationFailedError(AccountError):
    """Erro de autenticação."""
    pass


class EmailAlreadyRegisteredError(AccountError):
    """Email já está registrado."""
    pass


class InvalidPasswordError(AccountError):
    """Senha inválida."""
    pass


class SessionError(AccountError):
    """Erro de sessão."""
    pass


class SocialAccountError(AccountError):
    """Erro com conta social (Google)."""
    pass


class UserNotFoundError(AccountError):
    """Usuário não encontrado."""
    pass


class UserInactiveError(AccountError):
    """Usuário inativo."""
    pass


class TokenInvalidError(AccountError):
    """Token inválido ou expirado."""
    pass