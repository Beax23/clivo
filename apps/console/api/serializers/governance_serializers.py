from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.console.models import ConsoleGovernance


class GovernanceSerializer(serializers.ModelSerializer):
    """Serializer de leitura de Governança."""

    is_system = serializers.BooleanField(read_only=True)
    is_protected = serializers.BooleanField(read_only=True)
    created_by_email = serializers.EmailField(
        source='created_by.email', read_only=True, allow_null=True
    )
    capabilities_count = serializers.SerializerMethodField()

    class Meta:
        model = ConsoleGovernance
        fields = [
            'id', 'key', 'name', 'description',
            'scope',
            'is_system', 'is_protected',
            'capabilities_count',
            'created_at', 'updated_at', 'created_by_email',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_email']

    def get_capabilities_count(self, obj):
        return obj.capabilities_relation.filter(
            capability__is_active=True
        ).count()


class GovernanceCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar Governança."""

    key = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    scope = serializers.ChoiceField(
        choices=['console', 'workspace'],
        default='workspace',
    )
    is_system = serializers.BooleanField(default=False, read_only=True)
    is_protected = serializers.BooleanField(default=False)

    class Meta:
        model = ConsoleGovernance
        fields = [
            'key', 'name', 'description', 'scope',
            'is_system', 'is_protected',
        ]

    def validate_key(self, value):
        if not value.islower() or ' ' in value:
            raise serializers.ValidationError(
                _('A chave deve ser em minúsculas, sem espaços')
            )
        if ConsoleGovernance.objects.filter(key=value).exists():
            raise serializers.ValidationError(
                _('Já existe uma governança com esta chave')
            )
        return value

    def validate(self, attrs):
        if attrs.get('is_system') and not attrs.get('is_protected'):
            raise serializers.ValidationError({
                'is_protected': _('Governanças de sistema devem ser protegidas')
            })
        return attrs


class GovernanceUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualizar Governança.

    Governanças de sistema PODEM ter `name` e `description` editados.
    O bloqueio existe apenas para exclusão (feito no service).
    """

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = ConsoleGovernance
        fields = ['name', 'description']