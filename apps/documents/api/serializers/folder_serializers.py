"""
Serializers de DocumentFolder.
"""

from rest_framework import serializers

from apps.documents.models import DocumentFolder


class DocumentFolderSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de pasta.

    Expõe `document_count` para o frontend mostrar "Contratos (5)".
    """

    document_count = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = DocumentFolder
        fields = [
            'id',
            'name',
            'document_count',
            'created_by', 'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'document_count',
            'created_by', 'created_by_name',
            'created_at',
            'updated_at',
        ]

    def get_document_count(self, obj):
        annotated = getattr(obj, 'document_count_annotated', None)
        if annotated is not None:
            return annotated
        return obj.documents.count()


class DocumentFolderCreateSerializer(serializers.Serializer):
    """
    Body para criar pasta.
    """

    name = serializers.CharField(
        required=True,
        max_length=100,
        allow_blank=False,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value


class DocumentFolderUpdateSerializer(serializers.Serializer):
    """
    Body para renomear pasta.
    """

    name = serializers.CharField(
        required=True,
        max_length=100,
        allow_blank=False,
    )

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('O nome não pode ser vazio.')
        return value