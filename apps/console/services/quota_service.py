"""
Fundação do QuotaService — stub documentado.

Este service será implementado quando:
    1. `workspaces.Workspace` existir
    2. `UsageRecord` existir (para métricas `recorded`)
    3. Os domínios expuserem resolvers para métricas `derived`

CONTRATO ARQUITETURAL (não implementar agora):

    check(workspace, feature_key, metric_key, amount) -> QuotaResult
        - Descobre o plan ativo do workspace
        - Descobre a PlanFeature correspondente (plan + feature_key)
        - Lê o PlanFeatureLimit da métrica dentro dessa PlanFeature
        - Calcula uso atual:
            * origin='recorded' → soma UsageRecord no period
            * origin='derived'  → pergunta ao domínio via resolver
        - Aplica `behavior`:
            * hard_limit      → bloqueia se ultrapassar
            * soft_limit      → permite, mas sinaliza alerta
            * overage_allowed → permite e marca overage

    consume(workspace, feature_key, metric_key, amount, source) -> None
        - Chama check() previamente
        - Grava UsageRecord (se origin='recorded')
        - Nunca grava se origin='derived' (o domínio responde sozinho)

CADEIA DE CONSULTA:

    Workspace
        → Plan (ativo)
            → PlanFeature (por feature_key)
                → PlanFeatureLimit (por metric_key)
                    → UsageMetric

REGRA DE OURO:
    QuotaService NÃO conhece domínios específicos.
    Ele nunca faz `if metric == 'clients.count': Client.objects.count()`.
    Essa responsabilidade é do domínio, exposta via `UsageResolver`
    (a ser definido quando Workspace existir).

NÃO IMPLEMENTAR NADA AQUI NA V1.
"""


class QuotaService:
    """
    Stub. Implementação real após Workspace + UsageRecord.
    """

    @staticmethod
    def check(*args, **kwargs):
        raise NotImplementedError(
            'QuotaService será implementado após '
            'Workspace + UsageRecord existirem.'
        )

    @staticmethod
    def consume(*args, **kwargs):
        raise NotImplementedError(
            'QuotaService será implementado após '
            'Workspace + UsageRecord existirem.'
        )