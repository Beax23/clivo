"""
Serializers do portal do cliente.

Estes serializers são consumidos por views autenticadas via
`ClientPortalSession`. A estrutura do briefing é derivada do
`structure_snapshot` + os estados atuais das perguntas.
"""

from rest_framework import serializers

from apps.briefings.models import Briefing, BriefingAnswer


# =========================================================================
# LEITURA — o briefing visto pelo cliente
# =========================================================================

class PortalBriefingSerializer(serializers.Serializer):
    """
    Envelope do briefing para o cliente.

    Estrutura:
        {
            "id", "title", "status", "expires_at",
            "progress",                       # vindo de BriefingService
            "next_question_id",               # próxima elegível (ou null)
            "sections": [
                {
                    "id", "title", "description",
                    "questions": [
                        {
                            "id", "text", "instructions",
                            "allowed_response_formats",
                            "is_required",
                            "reference_document_ids",
                            "state",              # da projeção
                            "latest_content",
                            "latest_audio_url",
                            "latest_transcription",
                            "transcription_status",
                            "attachment_ids",
                        }
                    ]
                }
            ]
        }

    Nunca expõe dados internos do workspace.
    """

    def to_representation(self, briefing: Briefing):
        from apps.briefings.services.briefing_service import BriefingService

        answers = {
            str(a.question_id): a
            for a in briefing.answers.select_related(
                'latest_audio',
            ).prefetch_related('attachments')
        }

        sections = []
        ordered_sections = sorted(
            briefing.structure_snapshot.get('sections', []),
            key=lambda s: s.get('position', 0),
        )
        for section in ordered_sections:
            questions_payload = []
            ordered_questions = sorted(
                section.get('questions', []),
                key=lambda q: q.get('position', 0),
            )
            for q in ordered_questions:
                qid = str(q['id'])
                answer = answers.get(qid)
                latest_audio_url = ''
                if answer and answer.latest_audio and answer.latest_audio.file:
                    try:
                        latest_audio_url = answer.latest_audio.file.url
                    except Exception:
                        latest_audio_url = ''

                questions_payload.append({
                    'id': qid,
                    'text': q.get('text', ''),
                    'instructions': q.get('instructions', ''),
                    'question_type': q.get('question_type', 'text'),
                    'allowed_response_formats': list(
                        q.get('allowed_response_formats', [])
                    ),
                    'is_required': bool(q.get('is_required', True)),
                    'position': q.get('position', 0),
                    'reference_document_ids': list(
                        q.get('reference_document_ids', [])
                    ),
                    'state': answer.state if answer else BriefingAnswer.STATE_PENDING,
                    'latest_content': answer.latest_content if answer else '',
                    'latest_audio_url': latest_audio_url,
                    'latest_transcription': (
                        answer.latest_transcription if answer else ''
                    ),
                    'transcription_status': (
                        answer.transcription_status if answer
                        else BriefingAnswer.TRANSCRIPTION_NOT_APPLICABLE
                    ),
                    'attachment_ids': (
                        [str(d.id) for d in answer.attachments.all()]
                        if answer else []
                    ),
                })
            sections.append({
                'id': section.get('id'),
                'title': section.get('title', ''),
                'description': section.get('description', ''),
                'position': section.get('position', 0),
                'questions': questions_payload,
            })

        next_q = BriefingService.get_next_eligible_question(briefing)

        return {
            'id': str(briefing.id),
            'title': briefing.title,
            'status': briefing.status,
            'expires_at': (
                briefing.expires_at.isoformat()
                if briefing.expires_at else None
            ),
            'progress': BriefingService.compute_progress(briefing),
            'next_question_id': str(next_q['id']) if next_q else None,
            'sections': sections,
        }


# =========================================================================
# ESCRITA — submissão de resposta
# =========================================================================

class PortalAnswerSubmitSerializer(serializers.Serializer):
    text = serializers.CharField(
        required=False, allow_blank=True, max_length=20000,
    )
    audio_document_id = serializers.UUIDField(
        required=False, allow_null=True,
    )
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False, allow_empty=True, default=list,
    )

    def validate(self, attrs):
        text = (attrs.get('text') or '').strip()
        has_audio = attrs.get('audio_document_id') is not None
        if not text and not has_audio:
            raise serializers.ValidationError(
                'Envie um texto ou um áudio.'
            )
        attrs['text'] = text
        return attrs


class PortalClarificationSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, max_length=5000)

    def validate_message(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Escreva sua dúvida.')
        return value


class PortalReviewRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=False, allow_blank=True, max_length=5000,
    )