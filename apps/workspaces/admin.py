from django.contrib import admin

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceSubscription,
)


# =========================================================================
# INLINES
# =========================================================================

class WorkspaceSubscriptionInline(admin.TabularInline):
    """
    Assinaturas do Workspace.

    A partir do Commit A, um Workspace pode ter VÁRIAS assinaturas
    (histórico). Apenas UMA ativa (constraint no banco). O inline
    NÃO limita `max_num` — a constraint faz isso.

    `fk_name='workspace'` é explícito porque o relacionamento deixou
    de ser OneToOne (o Django, com FK, gera o fk_name automaticamente,
    mas deixar explícito evita ambiguidade se houver mais de uma FK
    para o mesmo model no futuro).
    """

    model = WorkspaceSubscription
    extra = 0
    fields = [
        'plan', 'is_active',
        'started_at', 'ended_at',
        'reason',
        'changed_by', 'changed_from',
    ]
    readonly_fields = ['changed_by', 'changed_from']
    autocomplete_fields = ['plan']
    ordering = ['-started_at']


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
        'reason',
        'started_at', 'ended_at',
    ]
    list_filter = ['is_active', 'plan', 'reason']
    search_fields = ['workspace__name', 'plan__name']
    autocomplete_fields = ['workspace', 'plan', 'changed_by', 'changed_from']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-started_at']

    fieldsets = (
        ('Vínculo', {
            'fields': ('id', 'workspace', 'plan'),
        }),
        ('Vigência', {
            'fields': ('is_active', 'started_at', 'ended_at'),
        }),
        ('Auditoria', {
            'fields': ('reason', 'changed_by', 'changed_from'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )