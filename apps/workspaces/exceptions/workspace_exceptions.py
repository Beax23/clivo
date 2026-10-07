"""
Exceções do módulo workspaces.

Padrão:
    WorkspaceError (base)
        ├── WorkspaceNotFoundError
        ├── WorkspaceSlugConflictError
        ├── WorkspaceUserNotActiveError
        ├── SlugGenerationError
        ├── MembershipError
        │       ├── DuplicateMembershipError
        │       ├── UserNotActiveError
        │       ├── GovernanceNotFoundError
        │       ├── GovernanceScopeError
        │       └── LastOwnerError
        ├── SubscriptionError
        │       ├── DefaultPlanNotFoundError
        │       ├── DefaultPlanAmbiguousError
        │       └── ProprietarioGovernanceNotFoundError
        └── WorkspaceInvitationError
                ├── InvitationNotFoundError
                ├── InvitationAlreadyPendingError
                └── InvitationResendLimitError
"""


class WorkspaceError(Exception):
    """Exceção base para o módulo workspaces."""
    pass


# ---- Workspace ----

class WorkspaceNotFoundError(WorkspaceError):
    """Workspace não encontrado."""
    pass


class WorkspaceSlugConflictError(WorkspaceError):
    """Slug já está em uso por outro Workspace."""
    pass


class WorkspaceUserNotActiveError(WorkspaceError):
    """O usuário criador do Workspace precisa estar ativo."""
    pass


class SlugGenerationError(WorkspaceError):
    """
    Não foi possível gerar um slug único após várias tentativas.

    Sintoma de bug de concorrência ou de estado inconsistente
    do banco.
    """
    pass


# ---- Membership ----

class MembershipError(WorkspaceError):
    """Erro relacionado a membros do Workspace."""
    pass


class DuplicateMembershipError(MembershipError):
    """Usuário já é membro deste Workspace."""
    pass


class UserNotActiveError(MembershipError):
    """Usuário inativo não pode ser adicionado ao Workspace."""
    pass


class GovernanceNotFoundError(MembershipError):
    """Governance referenciada não existe."""
    pass


class GovernanceScopeError(MembershipError):
    """
    A Governance referenciada não é do escopo WORKSPACE.

    Apenas governanças com scope='workspace' podem ser atribuídas
    a membros de um Workspace.
    """
    pass


class LastOwnerError(MembershipError):
    """
    Não é possível remover o último proprietário do Workspace.

    Um Workspace sem proprietário fica órfão de administração.
    """
    pass


# ---- Subscription ----

class SubscriptionError(WorkspaceError):
    """Erro relacionado à assinatura do Workspace."""
    pass


class DefaultPlanNotFoundError(SubscriptionError):
    """
    Não existe Plan com is_default=True no Console.

    O Console precisa ter exatamente um plano inicial antes que
    qualquer Workspace possa ser criado.
    """
    pass


class DefaultPlanAmbiguousError(SubscriptionError):
    """
    Existe mais de um Plan com is_default=True no Console.

    Isso é um bug de integridade da plataforma, não uma situação
    para escolher arbitrariamente.
    """
    pass


class ProprietarioGovernanceNotFoundError(SubscriptionError):
    """
    A Governance 'proprietario' com scope='workspace' não foi
    encontrada no Console.

    Rode `python manage.py seed_console` para criá-la.
    """
    pass


# ---- Invitations ----

class WorkspaceInvitationError(WorkspaceError):
    """Erro genérico de convite."""
    pass


class InvitationNotFoundError(WorkspaceInvitationError):
    """Convite não encontrado."""
    pass


class InvitationAlreadyPendingError(WorkspaceInvitationError):
    """Já existe convite pendente para este email."""
    pass


class InvitationResendLimitError(WorkspaceInvitationError):
    """Limite de reenvios atingido."""
    pass