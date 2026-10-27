"""
Serializers da API de Inteligência.

Regras:
    - Somente leitura na exposição de insights (a escrita passa pelos
      services internos).
    - Tags usam `TagTransitionSerializer` para a única escrita
      permitida via API (transição de estado com histórico).
    - Containers são montados pelo ContainerService e serializados
      com InsightItemSerializer.
"""

from rest_framework import serializers

from apps.intelligence.models import (
    InsightItem,
    InsightEvidence,
    InsightTagHistory,
    InsightCostAllocation,
)


class InsightEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsightEvidence
        fields = ['id', 'source_type', 'source_ref', 'quote', 'created_at']
        read_only_fields = fields


class InsightCostAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsightCostAllocation
        fields = [
            'id',
            'usage_record_id',
            'allocated_cost',
            'currency',
            'is_estimated',
            'allocation_rule',
            'created_at',
        ]
        read_only_fields = fields


class InsightItemSerializer(serializers.ModelSerializer):
    evidences = InsightEvidenceSerializer(many=True, read_only=True)
    cost_allocations = InsightCostAllocationSerializer(
        many=True, read_only=True,
    )
    kind_display = serializers.CharField(
        source='get_kind_display', read_only=True,
    )
    confidence_display = serializers.CharField(
        source='get_confidence_display', read_only=True,
    )
    review_state_display = serializers.CharField(
        source='get_review_state_display', read_only=True,
    )

    class Meta:
        model = InsightItem
        fields = [
            'id',
            'kind', 'kind_display',
            'confidence', 'confidence_display',
            'content',
            'metadata',
            'review_state', 'review_state_display',
            'is_stale',
            'evidences',
            'cost_allocations',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class InsightTagHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(
        source='changed_by.email', read_only=True, allow_null=True,
    )

    class Meta:
        model = InsightTagHistory
        fields = [
            'id',
            'previous_state',
            'new_state',
            'changed_by', 'changed_by_email',
            'reason',
            'created_at',
        ]
        read_only_fields = fields


class TagTransitionSerializer(serializers.Serializer):
    """Body do PATCH /api/intelligence/tags/{id}/."""

    new_state = serializers.ChoiceField(
        choices=[
            InsightTagHistory.STATE_CONFIRMED,
            InsightTagHistory.STATE_DISCARDED,
        ],
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )


class ContainerPayloadSerializer(serializers.Serializer):
    """
    Envelope de resposta dos containers.

    `containers` é um dict {slot_name: [InsightItem, ...]}.
    `counts` é um dict {slot_name: int}.
    """

    containers = serializers.DictField(
        child=serializers.ListField(
            child=InsightItemSerializer(),
        ),
        read_only=True,
    )
    counts = serializers.DictField(
        child=serializers.IntegerField(),
        read_only=True,
    )