"""
Exceções do orçamento operacional de armazenamento.

    StorageBudgetError (base)
        ├── StorageBudgetNotFoundError
        ├── StorageBudgetNotConfiguredError
        ├── StorageBudgetBelowCommittedError
        ├── StorageBudgetUnlimitedQuotaError
        └── StorageBudgetAmbiguousQuotaError
"""

from apps.console.exceptions.console_exceptions import ConsoleError


class StorageBudgetError(ConsoleError):
    """Erro genérico do orçamento de armazenamento."""
    pass


class StorageBudgetNotFoundError(StorageBudgetError):
    """Orçamento não encontrado no banco."""
    pass


class StorageBudgetNotConfiguredError(StorageBudgetError):
    """
    Orçamento não configurado.

    Deve ser inicializado via `python manage.py seed_storage_budget`
    ou por PATCH no Console.
    """
    pass


class StorageBudgetBelowCommittedError(StorageBudgetError):
    """
    Tentativa de reduzir o orçamento abaixo do já comprometido.

    O novo valor não cobriria as quotas já prometidas aos workspaces
    ativos. A operação é bloqueada.
    """
    pass


class StorageBudgetUnlimitedQuotaError(StorageBudgetError):
    """
    Existe workspace ativo com plano de quota ilimitada.

    A política estrita não consegue garantir orçamento enquanto
    isso existir. Bloqueia o cálculo de `committed_bytes`.
    """
    pass


class StorageBudgetAmbiguousQuotaError(StorageBudgetError):
    """
    Existe plano com configuração ambígua de quota
    (mais de uma feature definindo `storage.bytes`).

    Bloqueia o cálculo de `committed_bytes`.
    """
    pass