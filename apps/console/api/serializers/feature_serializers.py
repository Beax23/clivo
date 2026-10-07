import re

from rest_framework import serializers
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.console.models import Feature


class FeatureSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura de Feature.

    `key` é exposta para integração técnica (frontend não precisa
    renderizar — é apenas identificação estável).
    """

    class Meta:
        model = Feature
        fields = [
            'id', 'key', 'name', 'description',
            'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FeatureCreateSerializer(serializers.ModelSerializer):
    """
    Serializer para criar Feature.

    A `key` é gerada automaticamente a partir do `name` (slug),
    exatamente como em Plan. O operador não conhece a chave técnica.
    """

    class Meta:
        model = Feature
        fields = ['name', 'description', 'is_active']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_('O nome é obrigatório'))
        return value.strip()

    def create(self, validated_data):
        # Gera key a partir do nome (slug)
        base_key = slugify(validated_data['name']).replace('-', '_')
        base_key = re.sub(r'[^a-z0-9_]', '', base_key) or 'feature'

        # Garante unicidade
        key = base_key
        counter = 1
        while Feature.objects.filter(key=key).exists():
            counter += 1
            key = f"{base_key}_{counter}"

        validated_data['key'] = key
        return super().create(validated_data)


class FeatureUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualizar Feature.

    A `key` NÃO é editável após criação — é identidade técnica estável.
    """

    class Meta:
        model = Feature
        fields = ['name', 'description', 'is_active']