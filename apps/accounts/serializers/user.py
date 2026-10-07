from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services.account import AccountService


class UserSerializer(serializers.ModelSerializer):
    """Serializer para o modelo User."""
    
    full_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'avatar', 'avatar_url', 'is_active', 'is_superuser', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_active', 'is_superuser', 'email']

    def get_full_name(self, obj):
        return obj.full_name
    
    def get_avatar_url(self, obj):
        """Retorna a URL do avatar ou None."""
        return obj.avatar if obj.avatar else None


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar usuário."""
    
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 
            'password', 'password_confirm'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': _('As senhas não coincidem')
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        return AccountService.create_account(
            password=password,
            **validated_data
        )


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer para atualizar usuário."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'avatar']