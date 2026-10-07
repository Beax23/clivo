from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.console.api.views.membership_views import MembershipViewSet
from apps.console.api.views.governance_views import GovernanceViewSet
from apps.console.api.views.capability_views import CapabilityViewSet
from apps.console.api.views.plan_views import PlanViewSet
from apps.console.api.views.feature_views import FeatureViewSet
from apps.console.api.views.plan_feature_views import PlanFeatureViewSet
from apps.console.api.views.provider_views import (
    ProviderViewSet,
    ProviderConnectionViewSet,
    ProviderContractViewSet,
)
from apps.console.api.views.provider_pricing_views import ProviderPricingViewSet
from apps.console.api.views.usage_views import UsageMetricViewSet
from apps.console.api.views.usage_record_views import UsageRecordViewSet
from apps.console.api.views.provider_log_views import ProviderLogViewSet
from apps.console.api.views.cost_views import CostViewSet
from apps.console.api.views.workspace_admin_views import AdminWorkspaceViewSet
from apps.console.api.views.user_admin_views import AdminUserViewSet

router = DefaultRouter()

# Console V1 — acesso e governança
router.register(r'members', MembershipViewSet, basename='member')
router.register(r'governances', GovernanceViewSet, basename='governance')
router.register(r'capabilities', CapabilityViewSet, basename='capability')

# Console V1 — comercial
router.register(r'plans', PlanViewSet, basename='plan')
router.register(r'features', FeatureViewSet, basename='feature')
router.register(r'plan-features', PlanFeatureViewSet, basename='plan-feature')

# Console V1 — providers
router.register(r'providers', ProviderViewSet, basename='provider')
router.register(r'connections', ProviderConnectionViewSet, basename='connection')
router.register(r'contracts', ProviderContractViewSet, basename='contract')
router.register(r'pricings', ProviderPricingViewSet, basename='pricing')

# Console V1 — uso e logs
router.register(r'metrics', UsageMetricViewSet, basename='metric')
router.register(r'usage-records', UsageRecordViewSet, basename='usage-record')
router.register(r'provider-logs', ProviderLogViewSet, basename='provider-log')

# Console V1 — economia
router.register(r'costs', CostViewSet, basename='cost')

# Console V1 — visão administrativa (read-only)
router.register(r'workspaces', AdminWorkspaceViewSet, basename='admin-workspace')
router.register(r'users', AdminUserViewSet, basename='admin-user')

urlpatterns = [
    path('api/console/', include(router.urls)),
]