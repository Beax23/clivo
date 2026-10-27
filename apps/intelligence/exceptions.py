"""
Exceções do módulo intelligence.

Todas as classes abaixo são referenciadas por código existente:
    analysis_service.py: AnalysisInputError, AIProviderError,
                         AIResponseError, StaleAnalysisError
    budget_service.py:   BudgetExceededError
    intelligence_worker.py: BudgetExceededError, StaleAnalysisError
"""


class IntelligenceError(Exception):
    """Base do módulo intelligence."""
    pass


class AnalysisInputError(IntelligenceError):
    """Falha ao preparar o input da análise."""
    pass


class AIProviderError(IntelligenceError):
    """Falha na comunicação com o provedor de IA."""
    pass


class AIResponseError(IntelligenceError):
    """Resposta da IA inválida ou fora do contrato."""
    pass


class StaleAnalysisError(IntelligenceError):
    """Existe evento mais recente que o run. Análise descartada."""
    pass


class BudgetExceededError(IntelligenceError):
    """Execução bloqueada pela política de quota do Console."""
    pass