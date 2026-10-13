"""
Serializers de BriefingNote (Journal do arquiteto).
"""

from rest_framework import serializers

from apps.briefings.models import BriefingNote


class BriefingNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = BriefingNote
        fields = [
            'id',
            'briefing',
            'question_id',
            'author',
            'author_email',
            'author_name',
            'content',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'briefing',
            'author',
            'author_email',
            'author_name',
            'created_at',
            'updated_at',
        ]

    def get_author_email(self, obj):
        return obj.author.email if obj.author else None

    def get_author_name(self, obj):
        return obj.author.full_name if obj.author else None


class BriefingNoteCreateSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, max_length=20000)
    question_id = serializers.UUIDField(
        required=False, allow_null=True,
    )

    def validate_content(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('A anotação não pode ser vazia.')
        return value


class BriefingNoteUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, max_length=20000)

    def validate_content(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('A anotação não pode ser vazia.')
        return value