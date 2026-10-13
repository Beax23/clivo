"""
QuotaService — resolve a política de cota de armazenamento do workspace.

CONCEITOS SEPARADOS (nunca misturados)
--------------------------------------
    Quota contratada       → PlanFeatureLimit do 'storage.bytes' via plano
    Consumo contabilizado  → Sum(Document.size) + Sum(Reference.size) do workspace
    Teto físico do Clivo   → StorageProviderSnapshot (auditoria; NÃO usado aqui)

O QuotaService calcula cota e uso. Nunca toca no snapshot do B2.

FONTE DA COTA
-------------
    workspace.active_subscription  (property — assinatura ativa)
      → subscription.plan
        → plan.plan_features  (reverse FK)
          → plan_feature.limits  (reverse FK)
            → limit.metric.key == 'storage.bytes'

Regras:
    - Sem subscription ativa → quota desconhecida (None)
    - Plano inativo → quota desconhecida (None)
    - Sem PlanFeatureLimit de 'storage.bytes' → quota desconhecida (None)
    - Exatamente um PlanFeatureLimit → QuotaInfo
    - Mais de um PlanFeatureLimit → AmbiguousQuotaConfigurationError
      (não somar, não escolher o primeiro)

MÁQUINA DE ESTADOS (`check`)
----------------------------
    unconfigured → sem plano ativo OU sem limite configurado
                   allowed=True (política provisória), remaining=None
    unlimited    → limit_value=NULL
                   allowed=True, remaining=None
    ok           → used < 80% da quota
                   allowed=True, remaining=quota-used
    warning      → 80% ≤ used < 100% OU used ≥ 100% em soft/overage
                   allowed=True, remaining=max(quota-used, 0)
    blocked      → used ≥ 100% E behavior='hard_limit'
                   allowed=False, remaining=0

O limiar de aviso é 80%, hardcoded aqui (`WARNING_THRESHOLD`).
Não configurável por plano nesta fase.

UNIDADE
-------
Bytes inteiros. Nunca MB/GB com arredondamento intermediário.
A formatação humana (KB/MB/GB) é responsabilidade da camada de apresentação.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

logger = logging.getLogger('console')


# Limiar de aviso — 80%. Hardcoded; se virar requisito por plano, move-se.
WARNING_THRESHOLD = Decimal('0.80')

# Chave canônica da métrica de armazenamento.
STORAGE_METRIC_KEY = 'storage.bytes'


# =========================================================================
# RESULTADOS
# =========================================================================

@dataclass(frozen=True)
class QuotaInfo:
    """
    Cota contratada de um workspace.

    `limit_value = None` significa ilimitado.
    """
    limit_value: Optional[int]
    period: str
    behavior: str
    feature_key: str
    plan_key: str


@dataclass(frozen=True)
class QuotaCheckResult:
    """
    Estado completo de quota do workspace.

    `status`:
        unconfigured → sem plano ou sem limite; allowed=True, remaining=None
        unlimited    → limit_value=None; allowed=True, remaining=None
        ok           → uso < 80%; allowed=True, remaining=quota-used
        warning      → 80% ≤ uso OU uso ≥ 100% em soft/overage; allowed=True
        blocked      → uso ≥ 100% em hard_limit; allowed=False

    `allowed` reflete apenas o resultado da cota. Outras regras de negócio
    (permissão, workspace ativo) são verificadas antes, pelos chamadores.
    """
    status: str
    allowed: bool
    quota_bytes: Optional[int]
    used_bytes: int
    remaining_bytes: Optional[int]
    percent: float
    behavior: Optional[str]
    period: Optional[str]
    feature_key: Optional[str]
    plan_key: Optional[str]


# =========================================================================
# SERVIÇO
# =========================================================================

class QuotaService:

    # ==================================================================
    # COTA
    # ==================================================================

    @staticmethod
    def get_quota_info(workspace) -> Optional[QuotaInfo]:
        """
        Resolve a cota de 'storage.bytes' do workspace.

        Retorna None se não há quota configurada.
        Levanta AmbiguousQuotaConfigurationError se houver mais de uma
        feature do plano definindo o mesmo storage.bytes.

        Usa `workspace.active_subscription` (property), que filtra
        `is_active=True` e devolve None quando não há assinatura ativa.
        """
        from apps.console.models import PlanFeatureLimit
        from apps.console.exceptions import AmbiguousQuotaConfigurationError

        subscription = getattr(workspace, 'active_subscription', None)
        if subscription is None:
            return None

        plan = subscription.plan
        if plan is None or not plan.is_active:
            return None

        limits = list(
            PlanFeatureLimit.objects
            .filter(
                plan_feature__plan=plan,
                metric__key=STORAGE_METRIC_KEY,
                metric__is_active=True,
            )
            .select_related('plan_feature__feature')
            .order_by('plan_feature__feature__key')
        )

        if not limits:
            return None

        if len(limits) > 1:
            feature_keys = sorted(
                lim.plan_feature.feature.key for lim in limits
            )
            raise AmbiguousQuotaConfigurationError(
                f"O plano '{plan.key}' tem {len(limits)} features definindo "
                f"o limite de '{STORAGE_METRIC_KEY}': "
                f"{', '.join(feature_keys)}. "
                f"A configuração é ambígua — o operador precisa corrigir."
            )

        lim = limits[0]
        return QuotaInfo(
            limit_value=lim.limit_value,
            period=lim.period,
            behavior=lim.behavior,
            feature_key=lim.plan_feature.feature.key,
            plan_key=plan.key,
        )

    # ==================================================================
    # CONSUMO
    # ==================================================================

    @staticmethod
    def get_usage_bytes(workspace) -> int:
        """
        Soma de Document.size + Reference.size do workspace.

        Sempre retorna int >= 0.
        Cada módulo é agregado separadamente; nunca faz UNION.
        """
        from apps.documents.models import Document
        from apps.references.models import Reference

        documents_total = (
            Document.objects
            .filter(workspace=workspace)
            .aggregate(total=Sum('size'))
            .get('total') or 0
        )
        references_total = (
            Reference.objects
            .filter(workspace=workspace)
            .aggregate(total=Sum('size'))
            .get('total') or 0
        )

        try:
            documents_int = int(documents_total)
        except (TypeError, ValueError):
            documents_int = 0
        try:
            references_int = int(references_total)
        except (TypeError, ValueError):
            references_int = 0

        return max(0, documents_int) + max(0, references_int)

    # ==================================================================
    # RESTANTE
    # ==================================================================

    @staticmethod
    def get_remaining_bytes(workspace) -> Optional[int]:
        """
        quota - used, ou None se não há quota ou é ilimitada.

        Nunca retorna negativo — se used ≥ quota, retorna 0.
        Levanta AmbiguousQuotaConfigurationError propagando de get_quota_info.
        """
        info = QuotaService.get_quota_info(workspace)
        if info is None or info.limit_value is None:
            return None

        used = QuotaService.get_usage_bytes(workspace)
        remaining = info.limit_value - used
        return remaining if remaining > 0 else 0

    # ==================================================================
    # CHECK
    # ==================================================================

    @staticmethod
    def check(workspace) -> QuotaCheckResult:
        """
        Estado completo de quota do workspace.

        Nunca levanta — se a configuração for ambígua, retorna
        'unconfigured' com reason em `feature_key='__ambiguous__'`.
        O endpoint administrativo pode checar esse marcador e responder
        500 explicitamente; este método prioriza não quebrar chamadores.
        """
        from apps.console.exceptions import AmbiguousQuotaConfigurationError

        used = QuotaService.get_usage_bytes(workspace)

        try:
            info = QuotaService.get_quota_info(workspace)
        except AmbiguousQuotaConfigurationError as exc:
            logger.warning(
                'Quota ambígua para workspace=%s: %s',
                getattr(workspace, 'pk', '?'), exc,
            )
            return QuotaCheckResult(
                status='unconfigured',
                allowed=True,
                quota_bytes=None,
                used_bytes=used,
                remaining_bytes=None,
                percent=0.0,
                behavior=None,
                period=None,
                feature_key='__ambiguous__',
                plan_key=None,
            )

        # Sem quota configurada — estado explícito, permitir provisoriamente.
        if info is None:
            return QuotaCheckResult(
                status='unconfigured',
                allowed=True,
                quota_bytes=None,
                used_bytes=used,
                remaining_bytes=None,
                percent=0.0,
                behavior=None,
                period=None,
                feature_key=None,
                plan_key=None,
            )

        # Ilimitado — nada a avaliar.
        if info.limit_value is None:
            return QuotaCheckResult(
                status='unlimited',
                allowed=True,
                quota_bytes=None,
                used_bytes=used,
                remaining_bytes=None,
                percent=0.0,
                behavior=info.behavior,
                period=info.period,
                feature_key=info.feature_key,
                plan_key=info.plan_key,
            )

        quota = int(info.limit_value)
        remaining = quota - used
        if remaining < 0:
            remaining = 0

        percent = 0.0
        if quota > 0:
            percent = round((used / quota) * 100.0, 2)

        ratio = Decimal(used) / Decimal(quota) if quota > 0 else Decimal('0')

        # Comparações
        if ratio < WARNING_THRESHOLD:
            status = 'ok'
            allowed = True
        elif ratio < Decimal('1'):
            status = 'warning'
            allowed = True
        else:
            # used >= quota
            if info.behavior == 'hard_limit':
                status = 'blocked'
                allowed = False
            else:
                status = 'warning'
                allowed = True

        return QuotaCheckResult(
            status=status,
            allowed=allowed,
            quota_bytes=quota,
            used_bytes=used,
            remaining_bytes=remaining,
            percent=percent,
            behavior=info.behavior,
            period=info.period,
            feature_key=info.feature_key,
            plan_key=info.plan_key,
        )