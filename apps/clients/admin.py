from django.contrib import admin

from apps.clients.models import (
    Client,
    ClientContact,
    ClientNote,
    ClientPortalAccess,
    ClientPortalSession,
    ClientPortalInvitation,
    ClientPortalFeedback,
)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'public_code', 'workspace', 'status', 'created_at']
    list_filter = ['status', 'workspace']
    search_fields = ['name', 'email', 'public_code']
    readonly_fields = ['id', 'public_code', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(ClientContact)
class ClientContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'client', 'role']
    list_filter = ['role']
    search_fields = ['name', 'client__name']
    autocomplete_fields = ['client']


@admin.register(ClientNote)
class ClientNoteAdmin(admin.ModelAdmin):
    list_display = ['client', 'author', 'created_at', 'is_pinned']
    list_filter = ['is_pinned']
    search_fields = ['content', 'client__name']
    autocomplete_fields = ['client', 'author']


@admin.register(ClientPortalAccess)
class ClientPortalAccessAdmin(admin.ModelAdmin):
    list_display = ['client', 'accessed_at', 'ip_address']
    readonly_fields = ['id', 'accessed_at']
    search_fields = ['client__name']
    autocomplete_fields = ['client']


@admin.register(ClientPortalSession)
class ClientPortalSessionAdmin(admin.ModelAdmin):
    list_display = ['client', 'created_at', 'expires_at', 'revoked_at']
    readonly_fields = ['id', 'token_hash', 'created_at']
    search_fields = ['client__name']
    autocomplete_fields = ['client']


@admin.register(ClientPortalInvitation)
class ClientPortalInvitationAdmin(admin.ModelAdmin):
    list_display = ['client', 'email', 'status', 'sent_at']
    list_filter = ['status']
    search_fields = ['client__name', 'email']
    readonly_fields = ['id', 'sent_at']
    autocomplete_fields = ['client', 'session', 'sent_by']


@admin.register(ClientPortalFeedback)
class ClientPortalFeedbackAdmin(admin.ModelAdmin):
    list_display = ['client', 'kind', 'rating', 'created_at']
    list_filter = ['kind', 'rating']
    search_fields = ['client__name', 'message']
    readonly_fields = ['id', 'created_at']
    autocomplete_fields = ['client']