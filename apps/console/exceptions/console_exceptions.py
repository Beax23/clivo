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