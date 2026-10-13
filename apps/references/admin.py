from django.contrib import admin

from apps.references.models import (
    Reference,
    ReferenceFolder,
    ReferenceHistory,
    ReferenceCategory,
)


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'workspace', 'client',
        'folder', 'created_by', 'created_at',
    ]
    list_filter = ['workspace', 'source', 'visible_to_client']
    search_fields = [
        'title', 'description', 'client__name', 'workspace__name',
        'categories__name',
    ]
    readonly_fields = [
        'id', 'metadata', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    autocomplete_fields = ['workspace', 'client', 'folder', 'created_by', 'updated_by']
    date_hierarchy = 'created_at'
    filter_horizontal = ['categories']

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'title'),
        }),
        ('Imagem', {
            'fields': ('image',),
        }),
        ('Conteúdo', {
            'fields': ('description', 'categories'),
        }),
        ('Contexto', {
            'fields': ('client', 'project_id', 'folder'),
        }),
        ('Origem', {
            'fields': ('source', 'source_url'),
        }),
        ('Visibilidade', {
            'fields': ('visible_to_client',),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
        ('Metadados', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
    )


@admin.register(ReferenceFolder)
class ReferenceFolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'workspace', 'created_by', 'created_at']
    list_filter = ['workspace']
    search_fields = ['name', 'workspace__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['name']
    autocomplete_fields = ['workspace', 'created_by']

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'name'),
        }),
        ('Capa', {
            'fields': ('cover',),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ReferenceHistory)
class ReferenceHistoryAdmin(admin.ModelAdmin):
    list_display = ['action', 'reference', 'user', 'timestamp']
    list_filter = ['action']
    search_fields = ['reference__title', 'user__email']
    readonly_fields = [
        'id', 'reference', 'user', 'action',
        'timestamp', 'previous_value', 'new_value',
    ]
    ordering = ['-timestamp']
    autocomplete_fields = ['reference', 'user']
    date_hierarchy = 'timestamp'

    fieldsets = (
        ('Evento', {
            'fields': ('id', 'reference', 'user', 'action', 'timestamp'),
        }),
        ('Alteração', {
            'fields': ('previous_value', 'new_value'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReferenceCategory)
class ReferenceCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'slug', 'color', 'workspace',
        'is_system', 'position', 'created_at',
    ]
    list_filter = ['is_system', 'workspace']
    search_fields = ['name', 'slug', 'workspace__name']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at']
    ordering = ['workspace', 'position', 'name']
    autocomplete_fields = ['workspace', 'created_by']

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'name', 'slug'),
        }),
        ('Estado', {
            'fields': ('color', 'is_system', 'position'),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )