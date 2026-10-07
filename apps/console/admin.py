from django.contrib import admin

from apps.console.models import (
    ConsoleMembership,
    ConsoleGovernance,
    ConsoleCapability,
    ConsoleGovernanceCapability,
    Provider,
    ProviderConnection,
    ProviderContract,
    ProviderPricing,
    UsageMetric,
    UsageRecord,
    ProviderLog,
    Plan,
    PlanFeature,
    PlanFeatureLimit,
    Feature,
)


# =========================================================================
# CONSOLE V1 — ACESSO
# =========================================================================

@admin.register(ConsoleMembership)
class ConsoleMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'created_by']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']


# =========================================================================
# CONSOLE V1 — GOVERNANÇA
# =========================================================================

@admin.register(ConsoleGovernance)
class ConsoleGovernanceAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'is_system', 'is_protected', 'created_at']
    list_filter = ['is_system', 'is_protected']
    search_fields = ['name', 'key', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['name']


@admin.register(ConsoleCapability)
class ConsoleCapabilityAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'source_app', 'is_active', 'created_at']
    list_filter = ['source_app', 'is_active']
    search_fields = ['code', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['source_app', 'name']


@admin.register(ConsoleGovernanceCapability)
class ConsoleGovernanceCapabilityAdmin(admin.ModelAdmin):
    list_display = ['governance', 'capability', 'created_at', 'created_by']
    list_filter = ['governance', 'capability']
    search_fields = ['governance__name', 'capability__code']
    autocomplete_fields = ['governance', 'capability']
    readonly_fields = ['created_at']


# =========================================================================
# CONSOLE V1 — COMERCIAL: FEATURES
# =========================================================================

@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['key', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['name']


# =========================================================================
# CONSOLE V1 — COMERCIAL: PLANS
# =========================================================================

class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 0
    fields = ['feature', 'created_at', 'created_by']
    readonly_fields = ['created_at', 'created_by']
    ordering = ['feature__name']
    autocomplete_fields = ['feature']


class PlanFeatureLimitInline(admin.TabularInline):
    model = PlanFeatureLimit
    extra = 0
    fields = ['metric', 'limit_value', 'period', 'behavior']
    ordering = ['metric__key']
    autocomplete_fields = ['metric']


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'key', 'price', 'currency',
        'billing_period', 'is_active', 'is_public', 'is_default',
    ]
    list_filter = [
        'is_active', 'is_public', 'is_default',
        'billing_period', 'currency',
    ]
    search_fields = ['name', 'key', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['price', 'name']
    inlines = [PlanFeatureInline]


@admin.register(PlanFeature)
class PlanFeatureAdmin(admin.ModelAdmin):
    list_display = ['plan', 'feature', 'created_at', 'created_by']
    list_filter = ['plan', 'feature']
    search_fields = ['plan__key', 'plan__name', 'feature__key', 'feature__name']
    autocomplete_fields = ['plan', 'feature']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PlanFeatureLimit)
class PlanFeatureLimitAdmin(admin.ModelAdmin):
    list_display = [
        'plan_feature', 'metric', 'limit_value', 'period', 'behavior',
    ]
    list_filter = ['period', 'behavior', 'metric']
    search_fields = [
        'plan_feature__plan__key', 'plan_feature__plan__name',
        'plan_feature__feature__key', 'plan_feature__feature__name',
        'metric__key', 'metric__name',
    ]
    autocomplete_fields = ['plan_feature', 'metric']
    readonly_fields = ['created_at', 'updated_at']


# =========================================================================
# CONSOLE V1 — PROVIDERS
# =========================================================================

@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'category', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'key', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['name']


@admin.register(ProviderConnection)
class ProviderConnectionAdmin(admin.ModelAdmin):
    list_display = ['provider', 'name', 'environment', 'is_active', 'created_at']
    list_filter = ['provider', 'environment', 'is_active']
    search_fields = ['provider__name', 'name', 'credential_ref']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['provider__name', 'name']


@admin.register(ProviderContract)
class ProviderContractAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'name', 'billing_period', 'fixed_cost',
        'currency', 'is_active', 'started_at',
    ]
    list_filter = ['provider', 'billing_period', 'is_active', 'currency']
    search_fields = ['provider__name', 'name', 'external_reference']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['provider__name', '-started_at']


@admin.register(ProviderPricing)
class ProviderPricingAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'metric', 'identifier', 'pricing_model',
        'unit_price', 'currency', 'is_active', 'starts_at',
    ]
    list_filter = ['provider', 'pricing_model', 'currency', 'is_active']
    search_fields = ['provider__name', 'metric__key', 'identifier']
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['provider', 'contract', 'metric']
    ordering = ['provider__name', 'metric__key', '-starts_at']


# =========================================================================
# CONSOLE V1 — MÉTRICAS
# =========================================================================

@admin.register(UsageMetric)
class UsageMetricAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'unit', 'kind', 'origin', 'is_active']
    list_filter = ['kind', 'origin', 'is_active']
    search_fields = ['key', 'name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['key']


# =========================================================================
# CONSOLE V1 — USO E LOGS (read-only no admin)
# =========================================================================

@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'metric', 'quantity', 'unit',
        'estimated_cost', 'currency', 'status', 'occurred_at',
    ]
    list_filter = ['provider', 'status', 'currency']
    search_fields = ['provider__name', 'metric__key', 'operation', 'request_id']
    readonly_fields = [
        'id', 'provider', 'connection', 'metric', 'workspace_id',
        'occurred_at', 'quantity', 'unit', 'request_id', 'operation',
        'model', 'metadata', 'estimated_cost', 'currency', 'status',
        'created_at',
    ]
    ordering = ['-occurred_at']

    def has_add_permission(self, request):
        # Bloqueia criação manual — só via UsageRecordService
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProviderLog)
class ProviderLogAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'operation', 'model', 'status',
        'latency_ms', 'estimated_cost', 'occurred_at',
    ]
    list_filter = ['provider', 'status', 'currency']
    search_fields = [
        'provider__name', 'operation', 'model',
        'request_id', 'correlation_id',
    ]
    readonly_fields = [
        'id', 'provider', 'connection', 'workspace_id',
        'occurred_at', 'operation', 'model', 'status',
        'latency_ms', 'input_units', 'output_units',
        'estimated_cost', 'currency',
        'request_id', 'correlation_id',
        'error_message', 'metadata', 'created_at',
    ]
    ordering = ['-occurred_at']

    def has_add_permission(self, request):
        # Bloqueia criação manual — só via ProviderLogService
        return False

    def has_change_permission(self, request, obj=None):
        return False