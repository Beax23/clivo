"""
Exceções do módulo console.

Padrão:

    ConsoleError (base)
        ├── GovernanceError
        │     ├── GovernanceNotFoundError
        │     ├── GovernanceProtectedError
        │     └── GovernanceInUseError
        ├── CapabilityError
        │     └── CapabilityNotFoundError
        ├── MembershipError
        │     ├── DuplicateMembershipError
        │     └── UserNotActiveError
        ├── UsageMetricNotFoundError
        └── QuotaError
              └── AmbiguousQuotaConfigurationError
"""


class ConsoleError(Exception):
    """Exceção base para o módulo console."""
    pass


# ---- Governança ----

class GovernanceError(ConsoleError):
    """Erro relacionado a governanças."""
    pass


class GovernanceNotFoundError(GovernanceError):
    """Governança não encontrada."""
    pass


class GovernanceProtectedError(GovernanceError):
    """Tentativa de modificar governança protegida."""
    pass


class GovernanceInUseError(GovernanceError):
    """Tentativa de excluir governança em uso."""
    pass


# ---- Capability ----

class CapabilityError(ConsoleError):
    """Erro relacionado a capabilities."""
    pass


class CapabilityNotFoundError(CapabilityError):
    """Capability não encontrada."""
    pass


# ---- Membership ----

class MembershipError(ConsoleError):
    """Erro relacionado a membros do Console."""
    pass


class DuplicateMembershipError(MembershipError):
    """Usuário já é membro do Console."""
    pass


class UserNotActiveError(MembershipError):
    """Usuário inativo."""
    pass


# ---- Usage ----

class UsageMetricNotFoundError(ConsoleError):
    """Métrica de uso não encontrada."""
    pass


# ---- Quota ----

class QuotaError(ConsoleError):
    """Erro relacionado a cotas de uso."""
    pass


class AmbiguousQuotaConfigurationError(QuotaError):
    """
    Mais de uma Feature do mesmo plano define limite para a mesma métrica.

    Essa é uma configuração ambígua: somar poderia duplicar cotas sem
    intenção comercial; escolher a primeira esconderia erros silenciosamente.
    O Console deve sinalizar para o operador corrigir.
    """
    pass