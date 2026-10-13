"""
Serializers de Briefing (execução), BriefingAnswer e BriefingEvent.
"""

from rest_framework import serializers

from apps.briefings.models import (
    Briefing,
    BriefingAnswer,
    BriefingEvent,
)
from apps.briefings.services.briefing_service import BriefingService


# =========================================================================
# ANSWER (leitura)
# =========================================================================

class BriefingAnswerSerializer(serializers.ModelSerializer):
    state_display = serializers.CharField(
        source='get_state_display', read_only=True,
    )
    transcription_status_display = serializers.CharField(
        source='get_transcription_status_display', read_only=True,
    )
    latest_audio_url = serializers.SerializerMethodField()
    attachment_ids = serializers.SerializerMethodField()

    class Meta:
        model = BriefingAnswer
        fields = [
            'id',
            'question_id',
            'state',
            'state_display',
            'latest_content',
            'latest_audio',
            'latest_audio_url',
            'latest_transcription',
            'transcription_status',
            'transcription_status_display',
            'latest_event',
            'attachment_ids',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_latest_audio_url(self, obj):
        if not obj.latest_audio or not obj.latest_audio.file:
            return ''
        try:
            return obj.latest_audio.file.url
        except Exception:
            return ''

    def get_attachment_ids(self, obj):
        return [str(d.id) for d in obj.attachments.all()]


# =========================================================================
# EVENT (leitura)
# =========================================================================

class BriefingEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source='get_kind_display', read_only=True,
    )
    author_email = serializers.SerializerMethodField()
    author_kind = serializers.SerializerMethodField()

    class Meta:
        model = BriefingEvent
        fields = [
            'id',
            'kind',
            'kind_display',
            'question_id',
            'content',
            'author_email',
            'author_kind',
            'created_at',
        ]
        read_only_fields = fields

    def get_author_email(self, obj):
        if obj.user:
            return obj.user.email
        if obj.portal_session and obj.portal_session.client:
            return obj.portal_session.client.email or ''
        return ''

    def get_author_kind(self, obj):
        if obj.user_id:
            return 'user'
        if obj.portal_session_id:
            return 'portal'
        return 'system'


# =========================================================================
# BRIEFING — listagem
# =========================================================================

class BriefingListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True,
    )
    template_name = serializers.CharField(
        source='template.name', read_only=True, allow_null=True,
    )
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Briefing
        fields = [
            'id',
            'title',
            'status',
            'status_display',
            'client',
            'client_name',
            'template',
            'template_name',
            'expires_at',
            'progress',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_progress(self, obj):
        return BriefingService.compute_progress(obj)


# =========================================================================
# BRIEFING — detalhe
# =========================================================================

class BriefingDetailSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True,
    )
    template_name = serializers.CharField(
        source='template.name', read_only=True, allow_null=True,
    )
    progress = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    workspace_id = serializers.UUIDField(
        source='workspace.id', read_only=True,
    )

    class Meta:
        model = Briefing
        fields = [
            'id',
            'workspace_id',
            'title',
            'status',
            'status_display',
            'client',
            'client_name',
            'template',
            'template_name',
            'structure_snapshot',
            'expires_at',
            'started_at',
            'completed_at',
            'closed_at',
            'progress',
            'answers',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_progress(self, obj):
        return BriefingService.compute_progress(obj)

    def get_answers(self, obj):
        qs = obj.answers.select_related(
            'latest_event', 'latest_audio',
        ).prefetch_related('attachments').order_by('created_at')
        return BriefingAnswerSerializer(qs, many=True).data


# =========================================================================
# BRIEFING — criação
# =========================================================================

class BriefingCreateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField()
    client_id = serializers.CharField()
    title = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
    )
    expires_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )


# =========================================================================
# BRIEFING — reopen
# =========================================================================

class BriefingReopenSerializer(serializers.Serializer):
    new_expires_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=1000,
    )