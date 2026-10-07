from rest_framework import serializers

from apps.clients.models import ClientContact


class ClientContactSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = ClientContact
        fields = [
            'id', 'client', 'name', 'role', 'role_display',
            'email', 'phone', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'client', 'created_at', 'updated_at']


class ClientContactCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(
        choices=[c[0] for c in ClientContact.ROLE_CHOICES],
        default=ClientContact.ROLE_OTHER,
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ClientContactUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    role = serializers.ChoiceField(
        choices=[c[0] for c in ClientContact.ROLE_CHOICES],
        required=False,
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)