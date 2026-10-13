"""
Serializers de ReferenceFolder.
"""

from rest_framework import serializers

from apps.references.models import ReferenceFolder


class ReferenceFolderSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de pasta.
    """

    reference_count = serializers.SerializerMethodField()
    references_count = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()

    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = ReferenceFolder
        fields = [
            'id',
            'name',
            'cover_url',
            'reference_count',
            'references_count',
            'items_count',
            'created_by', 'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'cover_url',
            'reference_count',
            'references_count',
            'items_count',
            'created_by', 'created_by_name',
            'created_at',
            'updated_at',
        ]

    def _count(self, obj):
        annotated = getattr(obj, 'reference_count_annotated', None)
        if annotated is not None:
            return annotated
        return obj.references.count()

    def get_reference_count(self, obj):
        return self._count(obj)

    def get_references_count(self, obj):
        return self._count(obj)

    def get_items_count(self, obj):
        return self._count(obj)

    def get_cover_url(self, obj):
        if not obj.cover:
            return ''
        try:
            return obj.cover.url
        except Exception:
            return ''


class ReferenceFolderCreateSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=True, max_length=100, allow_blank=False,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class ReferenceFolderUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=False, max_length=100, allow_blank=False,
    )

    def validate_name(self, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class ReferenceFolderCoverSerializer(serializers.Serializer):
    cover = serializers.FileField(required=True)