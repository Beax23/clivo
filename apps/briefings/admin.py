from django.contrib import admin

from apps.briefings.models import (
    BriefingTemplate,
    BriefingSection,
    BriefingQuestion,
    BriefingTemplateEvent,
    Briefing,
    BriefingAnswer,
    BriefingEvent,
    BriefingNote,
)


# =========================================================================
# INLINES
# =========================================================================

class BriefingQuestionInline(admin.TabularInline):
    model = BriefingQuestion
    extra = 0
    fields = [
        'text', 'question_type', 'allowed_response_formats',
        'position', 'is_required',
    ]
    ordering = ['position']
    show_change_link = True


class BriefingSectionInline(admin.TabularInline):
    model = BriefingSection
    extra = 0
    fields = ['title', 'description', 'position']
    ordering = ['position']
    show_change_link = True


# =========================================================================
# TEMPLATE
# =========================================================================

@admin.register(BriefingTemplate)
class BriefingTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'workspace', 'category', 'status',
        'is_active', 'sections_count', 'questions_count',
        'created_at',
    ]
    list_filter = ['status', 'is_active', 'category', 'workspace']
    search_fields = ['name', 'description', 'category']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    autocomplete_fields = ['workspace', 'created_by']
    inlines = [BriefingSectionInline]

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'name', 'description', 'category'),
        }),
        ('Editorial', {
            'fields': ('status', 'is_active'),
        }),
        ('Capa', {
            'fields': ('cover',),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(BriefingSection)
class BriefingSectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'template', 'position', 'created_at']
    list_filter = ['template__workspace']
    search_fields = ['title', 'template__name']
    autocomplete_fields = ['template']
    ordering = ['template', 'position']
    inlines = [BriefingQuestionInline]
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(BriefingQuestion)
class BriefingQuestionAdmin(admin.ModelAdmin):
    list_display = [
        'text_short', 'section', 'question_type',
        'position', 'is_required',
    ]
    list_filter = ['question_type', 'is_required']
    search_fields = ['text', 'instructions']
    autocomplete_fields = ['section']
    ordering = ['section', 'position']
    filter_horizontal = ['reference_documents']
    readonly_fields = ['id', 'created_at', 'updated_at']

    def text_short(self, obj):
        return obj.text[:60]
    text_short.short_description = 'Enunciado'


@admin.register(BriefingTemplateEvent)
class BriefingTemplateEventAdmin(admin.ModelAdmin):
    list_display = ['kind', 'template', 'user', 'created_at']
    list_filter = ['kind']
    search_fields = ['template__name', 'content']
    readonly_fields = [
        'id', 'template', 'kind', 'section_id', 'question_id',
        'content', 'user', 'created_at',
    ]
    autocomplete_fields = ['template', 'user']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =========================================================================
# BRIEFING
# =========================================================================

@admin.register(Briefing)
class BriefingAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'client', 'workspace', 'status',
        'expires_at', 'created_at',
    ]
    list_filter = ['status', 'workspace']
    search_fields = ['title', 'client__name']
    readonly_fields = [
        'id', 'structure_snapshot',
        'started_at', 'completed_at', 'closed_at',
        'created_at', 'updated_at',
    ]
    autocomplete_fields = ['workspace', 'client', 'template', 'created_by']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Identificação', {
            'fields': ('id', 'workspace', 'client', 'template', 'title'),
        }),
        ('Estado', {
            'fields': ('status', 'expires_at'),
        }),
        ('Datas', {
            'fields': ('started_at', 'completed_at', 'closed_at'),
        }),
        ('Snapshot', {
            'fields': ('structure_snapshot',),
            'classes': ('collapse',),
        }),
        ('Rastreabilidade', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(BriefingAnswer)
class BriefingAnswerAdmin(admin.ModelAdmin):
    list_display = [
        'briefing', 'question_id', 'state',
        'transcription_status', 'updated_at',
    ]
    list_filter = ['state', 'transcription_status']
    search_fields = ['briefing__title', 'latest_content']
    readonly_fields = [
        'id', 'briefing', 'question_id',
        'latest_content', 'latest_audio', 'latest_transcription',
        'latest_event', 'created_at', 'updated_at',
    ]
    autocomplete_fields = ['briefing', 'latest_audio', 'latest_event']
    filter_horizontal = ['attachments']
    ordering = ['-updated_at']

    def has_add_permission(self, request):
        return False


@admin.register(BriefingEvent)
class BriefingEventAdmin(admin.ModelAdmin):
    list_display = [
        'briefing', 'kind', 'author_display',
        'question_id_short', 'created_at',
    ]
    list_filter = ['kind']
    search_fields = ['briefing__title', 'content']
    readonly_fields = [
        'id', 'briefing', 'kind', 'question_id', 'content',
        'user', 'portal_session', 'created_at',
    ]
    autocomplete_fields = ['briefing', 'user', 'portal_session']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def author_display(self, obj):
        if obj.user_id:
            return obj.user.email
        if obj.portal_session_id:
            return f'portal:{obj.portal_session_id}'
        return '—'
    author_display.short_description = 'Autor'

    def question_id_short(self, obj):
        return str(obj.question_id)[:8] if obj.question_id else '—'
    question_id_short.short_description = 'Pergunta'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =========================================================================
# NOTE (Journal)
# =========================================================================

@admin.register(BriefingNote)
class BriefingNoteAdmin(admin.ModelAdmin):
    list_display = ['briefing', 'question_short', 'author', 'created_at']
    list_filter = ['briefing__workspace']
    search_fields = ['content', 'briefing__title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    autocomplete_fields = ['briefing', 'author']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def question_short(self, obj):
        return str(obj.question_id)[:8] if obj.question_id else '—'
    question_short.short_description = 'Pergunta'