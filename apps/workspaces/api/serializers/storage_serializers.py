"""
Serializer de leitura do estado de armazenamento do Workspace.

Contrato igual ao do endpoint administrativo do Console:
    - status, allowed, quota_bytes, used_bytes, remaining_bytes
    - percent, behavior, period, feature_key, plan_key
    - unconfigured_reason

Todos read-only. Este serializer nunca é usado para escrita.
"""

from rest_framework import serializers


class WorkspaceStorageSerializer(serializers.Serializer):
    """
    Estado completo de armazenamento do workspace.

    `quota_bytes = null` quando:
        - workspace sem plano ativo, OU
        - plano sem limite de storage.bytes, OU
        - limite ilimitado.

    `unconfigured_reason` explica qual desses casos ocorreu;
    `null` quando `status` é diferente de `unconfigured`.
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