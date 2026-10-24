from django.contrib import admin

from apps.integrations.models import (
    IntegrationProvider,
    IntegrationResource,
    WorkspaceIntegration,
)


@admin.register(IntegrationProvider)
class IntegrationProviderAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'category', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['key', 'name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['name']


@admin.register(IntegrationResource)
class IntegrationResourceAdmin(admin.ModelAdmin):
    list_display = ['provider', 'slug', 'name', 'is_active']
    list_filter = ['provider', 'is_active']
    search_fields = ['slug', 'name', 'description', 'provider__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    autocomplete_fields = ['provider']
    ordering = ['provider__name', 'slug']


@admin.register(WorkspaceIntegration)
class WorkspaceIntegrationAdmin(admin.ModelAdmin):
    list_display = [
        'workspace', 'provider',
        'external_account_email', 'status', 'is_preferred',
        'last_refresh_at', 'created_at',
    ]
    list_filter = ['provider', 'status', 'is_preferred']
    search_fields = [
        'workspace__name', 'provider__name',
        'external_account_email', 'external_account_id',
    ]
    readonly_fields = [
        'id', 'encrypted_payload',
        'last_refresh_at', 'last_error_at', 'last_error_code',
        'created_at', 'updated_at',
    ]
    autocomplete_fields = ['workspace', 'provider', 'created_by']
    ordering = ['-created_at']

    fieldsets = (
        ('Identidade', {
            'fields': (
                'id',
                'workspace', 'provider',
                'external_account_id',
                'external_account_email',
                'external_account_display_name',
                'external_account_avatar_url',
            ),
        }),
        ('Credenciais', {
            'fields': ('encrypted_payload', 'granted_scopes'),
        }),
        ('Estado', {
            'fields': (
                'status', 'is_preferred',
                'last_refresh_at',
                'last_error_at', 'last_error_code',
            ),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )