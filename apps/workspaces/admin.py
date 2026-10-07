from django.contrib import admin

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceSubscription,
)


# =========================================================================
# INLINES
# =========================================================================

class WorkspaceSubscriptionInline(admin.StackedInline):
    """Subscription é OneToOne — no máximo uma por Workspace."""
    model = WorkspaceSubscription
    extra = 0
    max_num = 1
    fields = ['plan', 'is_active', 'started_at', 'ended_at']
    autocomplete_fields = ['plan']
    readonly_fields = []


class WorkspaceMembershipInline(admin.TabularInline):
    """Membros do Workspace dentro do admin do Workspace."""
    model = WorkspaceMembership
    extra = 0
    fields = ['user', 'governance', 'joined_at', 'last_access_at']
    readonly_fields = ['joined_at', 'last_access_at']
    autocomplete_fields = ['user', 'governance']
    ordering = ['-joined_at']


# =========================================================================
# WORKSPACE
# =========================================================================

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'slug', 'city', 'state',
        'is_active', 'created_at',
    ]
    list_filter = ['is_active', 'state']
    search_fields = ['name', 'slug', 'cnpj', 'city']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at']
    ordering = ['name']
    inlines = [WorkspaceSubscriptionInline, WorkspaceMembershipInline]

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'name', 'slug'),
        }),
        ('Dados do escritório', {
            'fields': ('cnpj', 'city', 'state'),
        }),
        ('Estado', {
            'fields': ('is_active',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """
        `slug` é sempre read-only (gerado na criação, imutável na V1).
        """
        return self.readonly_fields


# =========================================================================
# MEMBERSHIP
# =========================================================================

@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'workspace', 'governance',
        'joined_at', 'last_access_at',
    ]
    list_filter = ['governance', 'workspace']
    search_fields = ['user__email', 'workspace__name']
    autocomplete_fields = ['user', 'workspace', 'governance']
    readonly_fields = ['id', 'joined_at', 'last_access_at', 'updated_at']
    ordering = ['-joined_at']

    fieldsets = (
        ('Vínculo', {
            'fields': ('id', 'workspace', 'user', 'governance'),
        }),
        ('Acesso', {
            'fields': ('joined_at', 'last_access_at', 'updated_at'),
        }),
    )


# =========================================================================
# SUBSCRIPTION
# =========================================================================

@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'workspace', 'plan', 'is_active',
        'started_at', 'ended_at',
    ]
    list_filter = ['is_active', 'plan']
    search_fields = ['workspace__name', 'plan__name']
    autocomplete_fields = ['workspace', 'plan']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-started_at']

    fieldsets = (
        ('Vínculo', {
            'fields': ('id', 'workspace', 'plan'),
        }),
        ('Vigência', {
            'fields': ('is_active', 'started_at', 'ended_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )