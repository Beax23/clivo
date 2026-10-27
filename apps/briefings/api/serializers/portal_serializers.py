"""
Serializers do portal do cliente.

REGRA ARQUITETURAL
------------------
O serializer serve DADO BRUTO. Não resume, não cura, não analisa.
A análise pertence ao `intelligence` (futuro).

DOIS BLOCOS
-----------
`sections`              → bloco original (structure_snapshot)
`supplementary_sections`→ bloco complementar (supplementary_snapshot)

O cliente vê os dois blocos no portal. O bloco complementar aparece
no final da conversa, identificado como "Perguntas complementares".

LINKS:
    portal_url                  → URL do chat do briefing (cliente).
    briefing_page_url           → URL da página do cliente (respostas + moodboard).
    briefing_pdf_url            → PDF do cliente (dados brutos).
    briefing_architect_url      → URL da página do arquiteto.
    briefing_architect_pdf_url  → PDF do arquiteto (dados brutos + transcrições).
"""

from rest_framework import serializers

from apps.briefings.models import Briefing, BriefingAnswer


def _doc_url(doc, request=None):
    if not doc or not doc.file:
        return ''
    try:
        url = doc.file.url
    except Exception:
        return ''
    if not url:
        return ''
    if request is not None and not url.startswith(('http://', 'https://')):
        try:
            url = request.build_absolute_uri(url)
        except Exception:
            pass
    return url


def _doc_public(doc, request=None):
    if doc is None:
        return None
    url = _doc_url(doc, request)
    if not url:
        return None
    return {
        'id': str(doc.id),
        'name': doc.name or '',
        'mime_type': doc.mime_type or '',
        'file_url': url,
    }


def _load_docs_map(doc_ids):
    ids = [str(x) for x in (doc_ids or []) if x]
    if not ids:
        return {}
    from apps.documents.models import Document
    docs = Document.objects.filter(id__in=ids).only(
        'id', 'name', 'mime_type', 'file',
    )
    return {str(d.id): d for d in docs}


def _expand_options(options, request=None):
    if not options:
        return options

    if isinstance(options, dict):
        columns = options.get('columns') or []
        ids = [
            c.get('image_document_id')
            for c in columns
            if isinstance(c, dict) and c.get('image_document_id')
        ]
        docs_by_id = _load_docs_map(ids)
        new_columns = []
        for c in columns:
            if not isinstance(c, dict):
                continue
            entry = {
                'text': c.get('text', ''),
                'image_document_id': c.get('image_document_id'),
                'image_url': None,
                'image_name': None,
            }
            doc_id = c.get('image_document_id')
            if doc_id and str(doc_id) in docs_by_id:
                d = docs_by_id[str(doc_id)]
                url = _doc_url(d, request)
                if url:
                    entry['image_url'] = url
                    entry['image_name'] = d.name or ''
            new_columns.append(entry)
        return {
            'rows': list(options.get('rows') or []),
            'columns': new_columns,
        }

    if isinstance(options, list):
        ids = [
            o.get('image_document_id')
            for o in options
            if isinstance(o, dict) and o.get('image_document_id')
        ]
        docs_by_id = _load_docs_map(ids)
        result = []
        for o in options:
            if not isinstance(o, dict):
                continue
            entry = {
                'text': o.get('text', ''),
                'image_document_id': o.get('image_document_id'),
                'image_url': None,
                'image_name': None,
            }
            doc_id = o.get('image_document_id')
            if doc_id and str(doc_id) in docs_by_id:
                d = docs_by_id[str(doc_id)]
                url = _doc_url(d, request)
                if url:
                    entry['image_url'] = url
                    entry['image_name'] = d.name or ''
            result.append(entry)
        return result

    return options


def _workspace_avatar_url(briefing: Briefing, request=None) -> str:
    ws = getattr(briefing, 'workspace', None)
    if ws is not None:
        file_field = (
            getattr(ws, 'logo', None)
            or getattr(ws, 'avatar', None)
        )
        if file_field:
            try:
                url = file_field.url
            except Exception:
                url = ''
            if url:
                if request and not url.startswith(('http://', 'https://')):
                    try:
                        url = request.build_absolute_uri(url)
                    except Exception:
                        pass
                return url

    owner = getattr(briefing, 'created_by', None)
    if owner is not None:
        try:
            from allauth.socialaccount.models import SocialAccount
            sa = (
                SocialAccount.objects
                .filter(user=owner, provider='google')
                .only('extra_data')
                .first()
            )
            if sa and isinstance(sa.extra_data, dict):
                pic = sa.extra_data.get('picture')
                if pic:
                    return pic
        except Exception:
            pass

    return ''


def _base_url(request):
    if request is not None:
        try:
            return request.build_absolute_uri('/').rstrip('/')
        except Exception:
            pass
    from django.conf import settings
    return getattr(settings, 'FRONTEND_URL', '').rstrip('/')


def _portal_briefing_url(briefing, request=None):
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/portal/briefings/{briefing.id}/'


def _client_page_url(briefing, request=None):
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/portal/briefings/{briefing.id}/respostas/'


def _client_pdf_url(briefing, request=None):
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/api/portal/briefings/{briefing.id}/export-pdf/'


def _architect_page_url(briefing, request=None):
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/w/{briefing.workspace_id}/briefings/{briefing.id}/resumo/'


def _architect_pdf_url(briefing, request=None):
    base = _base_url(request)
    if not base:
        return ''
    return f'{base}/api/briefings/{briefing.id}/export-pdf/'


def _serialize_question(
    q: dict,
    answer,
    request,
) -> dict:
    """
    Serializa uma pergunta (original ou complementar) com o mesmo
    formato. Usado pelos dois blocos.
    """
    latest_audio_url = ''
    if answer and answer.latest_audio and answer.latest_audio.file:
        try:
            latest_audio_url = answer.latest_audio.file.url
        except Exception:
            latest_audio_url = ''

    ref_docs = []
    ref_ids = list(q.get('reference_document_ids') or [])
    if ref_ids:
        docs = _load_docs_map(ref_ids)
        for rid in ref_ids:
            d = docs.get(str(rid))
            if d is None:
                continue
            payload = _doc_public(d, request)
            if payload:
                ref_docs.append(payload)

    attachments = []
    if answer is not None:
        for doc in answer.attachments.all():
            payload = _doc_public(doc, request)
            if payload:
                attachments.append(payload)

    expanded_options = _expand_options(q.get('options'), request)

    return {
        'id': str(q['id']),
        'text': q.get('text', ''),
        'instructions': q.get('instructions', ''),
        'question_type': q.get('question_type', 'text'),
        'allowed_response_formats': list(
            q.get('allowed_response_formats', [])
        ),
        'is_required': bool(q.get('is_required', True)),
        'position': q.get('position', 0),
        'is_custom': bool(q.get('is_custom', False)),
        'reference_documents': ref_docs,
        'options': expanded_options,
        'state': (
            answer.state if answer
            else BriefingAnswer.STATE_PENDING
        ),
        'latest_content': answer.latest_content if answer else '',
        'latest_audio_url': latest_audio_url,
        'latest_transcription': (
            answer.latest_transcription if answer else ''
        ),
        'transcription_status': (
            answer.transcription_status if answer
            else BriefingAnswer.TRANSCRIPTION_NOT_APPLICABLE
        ),
        'attachments': attachments,
    }


class PortalBriefingSerializer(serializers.Serializer):
    """Envelope do briefing para o portal. Dado bruto, sem análise."""

    def to_representation(self, briefing: Briefing):
        from apps.briefings.services.briefing_service import BriefingService

        request = self.context.get('request') if self.context else None

        answers = {
            str(a.question_id): a
            for a in briefing.answers.select_related(
                'latest_audio',
            ).prefetch_related('attachments')
        }

        # ----- Bloco original -----
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
                questions_payload.append(
                    _serialize_question(q, answer, request)
                )
            sections.append({
                'id': section.get('id'),
                'title': section.get('title', ''),
                'description': section.get('description', ''),
                'position': section.get('position', 0),
                'questions': questions_payload,
            })

        # ----- Bloco complementar -----
        supplementary_sections = []
        ordered_supp_sections = sorted(
            (briefing.supplementary_snapshot or {}).get('sections', []),
            key=lambda s: s.get('position', 0),
        )
        for section in ordered_supp_sections:
            questions_payload = []
            ordered_questions = sorted(
                section.get('questions', []),
                key=lambda q: q.get('position', 0),
            )
            for q in ordered_questions:
                qid = str(q['id'])
                answer = answers.get(qid)
                questions_payload.append(
                    _serialize_question(q, answer, request)
                )
            supplementary_sections.append({
                'id': section.get('id'),
                'title': section.get('title', ''),
                'description': section.get('description', ''),
                'position': section.get('position', 0),
                'questions': questions_payload,
            })

        # ----- Próxima pergunta e estado -----
        next_q = BriefingService.get_next_eligible_question(briefing)

        progress = BriefingService.compute_progress(briefing)
        supplementary_state = briefing.supplementary_state()

        has_new_custom_questions = self._has_new_custom_questions(
            briefing,
        )

        workspace_name = ''
        if briefing.workspace is not None:
            workspace_name = briefing.workspace.name or ''

        client_name = ''
        if briefing.client is not None:
            client_name = briefing.client.name or ''

        return {
            'id': str(briefing.id),
            'title': briefing.title,
            'workspace_id': (
                str(briefing.workspace_id)
                if briefing.workspace_id else ''
            ),
            'workspace_name': workspace_name,
            'workspace_avatar_url': _workspace_avatar_url(briefing, request),
            'client_id': (
                str(briefing.client_id) if briefing.client_id else ''
            ),
            'client_name': client_name,
            'intro_message': briefing.intro_message or '',
            'show_intro': briefing.show_intro_to_portal(),
            'portal_url': _portal_briefing_url(briefing, request),
            'briefing_page_url': _client_page_url(briefing, request),
            'briefing_pdf_url': _client_pdf_url(briefing, request),
            'briefing_architect_url': _architect_page_url(briefing, request),
            'briefing_architect_pdf_url': _architect_pdf_url(briefing, request),
            'status': briefing.status,
            'portal_status': briefing.portal_status(),
            'can_answer': briefing.portal_can_answer(),
            'expires_at': (
                briefing.expires_at.isoformat()
                if briefing.expires_at else None
            ),
            'first_opened_at': (
                briefing.first_opened_at.isoformat()
                if briefing.first_opened_at else None
            ),
            'progress': progress,
            'next_question_id': str(next_q['id']) if next_q else None,
            'has_custom_questions': bool(briefing.has_custom_questions),
            'sections': sections,
            'supplementary_sections': supplementary_sections,
            'supplementary_state': supplementary_state,
            'has_new_custom_questions': has_new_custom_questions,
        }

    def _has_new_custom_questions(self, briefing: Briefing) -> bool:
        """
        True se existe evento `custom_question_added` mais recente que
        `last_viewed_at` do briefing.

        Um cliente que nunca abriu (`last_viewed_at is None`) conta
        como "tem novas" se houver qualquer evento de adição.
        """
        from apps.briefings.models import BriefingEvent

        last_event = BriefingEvent.objects.filter(
            briefing=briefing,
            kind=BriefingEvent.KIND_CUSTOM_QUESTION_ADDED,
        ).order_by('-created_at').first()

        if last_event is None:
            return False

        if briefing.last_viewed_at is None:
            return True

        return last_event.created_at > briefing.last_viewed_at


class PortalBriefingListSerializer(serializers.Serializer):
    def to_representation(self, briefing: Briefing):
        from apps.briefings.services.briefing_service import BriefingService

        return {
            'id': str(briefing.id),
            'title': briefing.title,
            'status': briefing.status,
            'portal_status': briefing.portal_status(),
            'can_answer': briefing.portal_can_answer(),
            'expires_at': (
                briefing.expires_at.isoformat()
                if briefing.expires_at else None
            ),
            'progress': BriefingService.compute_progress(briefing),
            'has_supplementary_questions': (
                briefing.has_supplementary_questions()
            ),
            'supplementary_state': briefing.supplementary_state(),
        }


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
        has_attachments = bool(attrs.get('attachment_ids'))
        if not text and not has_audio and not has_attachments:
            raise serializers.ValidationError(
                'Envie um texto, um áudio ou uma imagem.'
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