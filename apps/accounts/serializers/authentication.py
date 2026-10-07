from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    """Serializer para login."""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        style={'input_type': 'password'},
        write_only=True
    )


class GoogleLoginSerializer(serializers.Serializer):
    """Serializer para login com Google (via allauth)."""
    code = serializers.CharField(required=True)


class SessionInfoSerializer(serializers.Serializer):
    """Serializer para informações da sessão."""
    session_type = serializers.ChoiceField(choices=['app', 'console'])
    created_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField(required=False, allow_null=True)
    user_id = serializers.UUIDField()
    email = serializers.EmailField()