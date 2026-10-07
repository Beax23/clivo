from rest_framework import serializers

from apps.clients.models import Client


class ClientListSerializer(serializers.ModelSerializer):
    """
    Leve — usado na listagem.

    NÃO expõe `created_by`: quem criou é informação de detalhe/auditoria,
    não informação primária para o arquiteto escolher um cliente.
    """

    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )

    class Meta:
        model = Client
        fields = [
            'id', 'public_code', 'name', 'email', 'phone',
            'status', 'status_display',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ClientDetailSerializer(serializers.ModelSerializer):
    """
    Completo — usado na página do cliente.

    Expõe quem criou o cliente (rastreabilidade de domínio).
    `created_by` é histórico: nunca editável.
    """

    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, allow_null=True
    )
    created_by_email = serializers.EmailField(
        source='created_by.email', read_only=True, allow_null=True
    )
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )

    class Meta:
        model = Client
        fields = [
            'id', 'public_code', 'name', 'email', 'phone',
            'context', 'status', 'status_display',
            'created_by', 'created_by_name', 'created_by_email',
            'created_at', 'updated_at',
        ]
        # IMPORTANTE: id, public_code, created_by e timestamps são read-only.
        # `status` é editável via clients.client.update.
        # `created_by` é histórico — nunca editável.
        read_only_fields = [
            'id', 'public_code',
            'created_by', 'created_by_name', 'created_by_email',
            'created_at', 'updated_at',
        ]


class ClientCreateSerializer(serializers.Serializer):
    """
    Criação de cliente.

    NÃO aceita workspace, created_by nem public_code.
    Esses vêm do contexto autenticado.

    `status` nasce como `active` por padrão — não é aceito na criação.
    """

    name = serializers.CharField(max_length=200)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)


class ClientUpdateSerializer(serializers.Serializer):
    """
    Atualização descritiva — inclui `status`.

    `context` muda via `context` action.
    `created_by` é histórico e imutável.
    """

    name = serializers.CharField(max_length=200, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=[c[0] for c in Client.STATUS_CHOICES],
        required=False,
    )


class ClientContextUpdateSerializer(serializers.Serializer):
    context = serializers.DictField()