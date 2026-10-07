from django.contrib import admin

from apps.documents.models import Document, DocumentHistory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'extension', 'workspace', 'client',
        'size_display', 'created_by', 'created_at',
    ]
    list_filter = ['extension', 'workspace']
    search_fields = ['name', 'client__name', 'workspace__name']
    readonly_fields = [
        'id', 'extension', 'mime_type', 'size',
        'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    autocomplete_fields = ['workspace', 'client', 'created_by', 'updated_by']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'name'),
        }),
        ('Arquivo', {
            'fields': ('file', 'extension', 'mime_type', 'size'),
        }),
        ('Contexto', {
            'fields': ('client', 'project_id'),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(DocumentHistory)
class DocumentHistoryAdmin(admin.ModelAdmin):
    list_display = [
        'action', 'document', 'user', 'timestamp',
    ]
    list_filter = ['action']
    search_fields = ['document__name', 'user__email']
    readonly_fields = [
        'id', 'document', 'user', 'action',
        'timestamp', 'previous_value', 'new_value',
    ]
    ordering = ['-timestamp']
    autocomplete_fields = ['document', 'user']
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Evento', {
            'fields': ('id', 'document', 'user', 'action', 'timestamp'),
        }),
        ('Alteração', {
            'fields': ('previous_value', 'new_value'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        # Histórico é append-only e criado exclusivamente via service.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False