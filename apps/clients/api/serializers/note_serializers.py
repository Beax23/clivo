from rest_framework import serializers

from apps.clients.models import ClientNote


class ClientNoteSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de nota.

    `author` é quem escreveu. Imutável após criação — `update_note`
    não aceita trocar autor.
    """

    author_email = serializers.EmailField(
        source='author.email', read_only=True, allow_null=True
    )
    author_name = serializers.CharField(
        source='author.full_name', read_only=True, allow_null=True
    )

    class Meta:
        model = ClientNote
        fields = [
            'id', 'client',
            'author', 'author_email', 'author_name',
            'content', 'is_pinned',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'client', 'author',
            'created_at', 'updated_at',
        ]


class ClientNoteCreateSerializer(serializers.Serializer):
    content = serializers.CharField()
    is_pinned = serializers.BooleanField(required=False, default=False)


class ClientNoteUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(required=False)
    is_pinned = serializers.BooleanField(required=False)