"""
Serializers do QuotaService.

Camada de apresentação pura — recebe QuotaCheckResult (dataclass) e
monta o payload para o frontend. Não toca em modelos.
"""

from rest_framework import serializers


class QuotaCheckSerializer(serializers.Serializer):
    """
    Resposta do endpoint administrativo de quota.

    Todos os campos são read-only. Este serializer nunca é usado
    para escrita.

    `quota_bytes` é `null` quando:
        - o workspace não tem plano ativo, OU
        - o plano não tem limite de storage.bytes, OU
        - o limite é ilimitado (limit_value=None)

    `unconfigured_reason` explica qual dos três casos é, quando
    `status='unconfigured'`; `null` nos demais estados.
    """

    workspace_id = serializers.UUIDField(read_only=True)
    workspace_name = serializers.CharField(read_only=True)

    plan_key = serializers.CharField(read_only=True, allow_null=True)
    plan_name = serializers.CharField(read_only=True, allow_null=True)

    status = serializers.ChoiceField(
        choices=[
            'ok', 'warning', 'blocked', 'unlimited', 'unconfigured',
        ],
        read_only=True,
    )
    allowed = serializers.BooleanField(read_only=True)

    quota_bytes = serializers.IntegerField(read_only=True, allow_null=True)
    used_bytes = serializers.IntegerField(read_only=True)
    remaining_bytes = serializers.IntegerField(read_only=True, allow_null=True)
    percent = serializers.FloatField(read_only=True)

    behavior = serializers.CharField(read_only=True, allow_null=True)
    period = serializers.CharField(read_only=True, allow_null=True)
    feature_key = serializers.CharField(read_only=True, allow_null=True)

    unconfigured_reason = serializers.CharField(
        read_only=True, allow_null=True,
    )