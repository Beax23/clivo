from django.contrib import admin

from apps.intelligence.models import (
    InsightEvent,
    InsightItem,
    InsightEvidence,
    AnalysisJob,
    AnalysisRun,
)


# =========================================================================
# EVENTOS — append-only
# =========================================================================

@admin.register(InsightEvent)
class InsightEventAdmin(admin.ModelAdmin):
    list_display = [
        'source_kind', 'workspace', 'client', 'briefing',
        'occurrence_id', 'created_at',
    ]
    list_filter = ['source_kind', 'workspace']
    search_fields = ['occurrence_id', 'source_ref', 'dedupe_key']
    readonly_fields = [
        'id', 'workspace', 'client', 'briefing',
        'source_kind', 'source_ref', 'occurrence_id',
        'dedupe_key', 'created_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =========================================================================
# INSIGHTS — projeção
# =========================================================================

class InsightEvidenceInline(admin.TabularInline):
    model = InsightEvidence
    extra = 0
    fields = ['source_type', 'source_ref', 'quote', 'created_at']
    readonly_fields = ['created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InsightItem)
class InsightItemAdmin(admin.ModelAdmin):
    """
    Leitura no admin. A criação acontece via AnalysisService.

    `review_state` é editável — é decisão humana (confirmar/descartar),
    e o modelo prevê isso. Se você quiser bloquear edição até existir
    uma view de revisão, é mudança de uma linha aqui.
    """
    list_display = [
        'kind', 'confidence', 'workspace', 'client', 'briefing',
        'review_state', 'is_stale', 'created_at',
    ]
    list_filter = ['kind', 'confidence', 'review_state', 'is_stale']
    search_fields = ['content']
    readonly_fields = [
        'id', 'run', 'workspace', 'client', 'briefing',
        'kind', 'confidence', 'content', 'metadata',
        'is_stale', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    inlines = [InsightEvidenceInline]

    def has_add_permission(self, request):
        return False


@admin.register(InsightEvidence)
class InsightEvidenceAdmin(admin.ModelAdmin):
    list_display = ['insight', 'source_type', 'source_ref', 'created_at']
    list_filter = ['source_type']
    search_fields = ['source_ref', 'quote']
    readonly_fields = [
        'id', 'insight', 'source_type', 'source_ref', 'quote',
        'created_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# =========================================================================
# JOBS E RUNS — observabilidade
# =========================================================================

@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'status', 'workspace', 'client', 'briefing',
        'attempt_count', 'created_at', 'completed_at', 'failed_at',
    ]
    list_filter = ['status', 'workspace']
    search_fields = ['job_key', 'last_error_message']
    readonly_fields = [
        'id', 'workspace', 'client', 'briefing',
        'target_kinds', 'data_version', 'job_key',
        'status', 'attempt_count',
        'processing_started_at', 'completed_at', 'failed_at',
        'last_error_message', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'status', 'model', 'prompt_version',
        'workspace', 'client', 'briefing',
        'input_tokens', 'output_tokens', 'duration_ms',
        'is_stale', 'created_at',
    ]
    list_filter = ['status', 'provider', 'is_stale', 'workspace']
    search_fields = ['input_hash', 'model', 'error_message']
    readonly_fields = [
        'id', 'job', 'workspace', 'client', 'briefing',
        'input_hash', 'data_version',
        'provider', 'model', 'prompt_version',
        'status', 'started_at', 'completed_at',
        'input_tokens', 'output_tokens', 'duration_ms',
        'error_message', 'is_stale',
        'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False