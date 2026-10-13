"""
Serializers de ReferenceCategory.
"""

from rest_framework import serializers

from apps.references.models import ReferenceCategory


class ReferenceCategorySerializer(serializers.ModelSerializer):
    reference_count = serializers.SerializerMethodField()

    class Meta:
        model = ReferenceCategory
        fields = [
            'id',
            'name',
            'slug',
            'color',
            'is_system',
            'position',
            'reference_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'slug', 'is_system', 'position',
            'reference_count', 'created_at', 'updated_at',
        ]

    def get_reference_count(self, obj):
        annotated = getattr(obj, 'reference_count_annotated', None)
        if annotated is not None:
            return annotated
        return obj.references.count()


class ReferenceCategoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, max_length=60, allow_blank=False)
    color = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class ReferenceCategoryUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=60, allow_blank=False)
    color = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
    )

    def validate_name(self, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value