# apps/briefings/api/serializers/briefing_serializers.py

"""
Serializers de Briefing (execução), BriefingAnswer e BriefingEvent.
"""

from rest_framework import serializers

from apps.briefings.models import (
    Briefing,
    BriefingAnswer,
    BriefingEvent,
)
from apps.briefings.services.briefing_service import BriefingService


# =========================================================================
# HELPERS
# =========================================================================

def _absolute_url(request, url):
    if not url:
        return ''
    if url.startswith(('http://', 'https://')):
        return url
    if request is not None:
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url
    return url


def _briefing_cover_url(briefing, request=None):
    template = briefing.template
    if template is None:
        return ''
    if not template.cover:
        return ''
    try:
        url = template.cover.url
    except Exception:
        return ''
    return _absolute_url(request, url)


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


def _load_docs_map(doc_ids, request=None):
    ids = [str(x) for x in (doc_ids or []) if x]
    if not ids:
        return {}
    from apps.documents.models import Document
    docs = Document.objects.filter(id__in=ids).only(
        'id', 'name', 'mime_type', 'file',
    )
    result = {}
    for d in docs:
        url = _doc_url(d, request)
        if not url:
            continue
        result[str(d.id)] = {
            'id': str(d.id),
            'name': d.name or '',
            'mime_type': d.mime_type or '',
            'file_url': url,
        }
    return result


def _expand_options(options, request=None):
    """
    Expande `options` de uma pergunta, resolvendo `image_document_id`
    para `image_url` / `image_name`.
    """
    if not options:
        return options

    if isinstance(options, dict):
        columns = options.get('columns') or []
        ids = [
            c.get('image_document_id')
            for c in columns
            if isinstance(c, dict) and c.get('image_document_id')
        ]
        docs = _load_docs_map(ids, request)
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
            if doc_id and str(doc_id) in docs:
                entry['image_url'] = docs[str(doc_id)]['file_url']
                entry['image_name'] = docs[str(doc_id)]['name']
            new_columns.append(entry)
        return {'rows': list(options.get('rows') or []), 'columns': new_columns}

    if isinstance(options, list):
        ids = [
            o.get('image_document_id')
            for o in options
            if isinstance(o, dict) and o.get('image_document_id')
        ]
        docs = _load_docs_map(ids, request)
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
            if doc_id and str(doc_id) in docs:
                entry['image_url'] = docs[str(doc_id)]['file_url']
                entry['image_name'] = docs[str(doc_id)]['name']
            result.append(entry)
        return result

    return options


def _expand_structure_snapshot(snapshot, request=None):
    """
    Devolve uma cópia do snapshot com as `options` expandidas
    (image_url resolvida). Não persiste nada.
    """
    if not isinstance(snapshot, dict):
        return snapshot
    import copy
    data = copy.deepcopy(snapshot)
    for section in data.get('sections', []):
        for q in section.get('questions', []):
            q['options'] = _expand_options(q.get('options'), request)
    return data


# =========================================================================
# ANSWER (leitura)
# =========================================================================

class BriefingAnswerSerializer(serializers.ModelSerializer):
    state_display = serializers.CharField(
        source='get_state_display', read_only=True,
    )
    transcription_status_display = serializers.CharField(
        source='get_transcription_status_display', read_only=True,
    )
    latest_audio_url = serializers.SerializerMethodField()
    attachment_ids = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = BriefingAnswer
        fields = [
            'id',
            'question_id',
            'state',
            'state_display',
            'latest_content',
            'latest_audio',
            'latest_audio_url',
            'latest_transcription',
            'transcription_status',
            'transcription_status_display',
            'latest_event',
            'attachment_ids',
            'attachments',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_latest_audio_url(self, obj):
        if not obj.latest_audio or not obj.latest_audio.file:
            return ''
        try:
            return obj.latest_audio.file.url
        except Exception:
            return ''

    def get_attachment_ids(self, obj):
        return [str(d.id) for d in obj.attachments.all()]

    def get_attachments(self, obj):
        request = self.context.get('request') if self.context else None
        result = []
        for doc in obj.attachments.all():
            url = _doc_url(doc, request)
            if not url:
                continue
            result.append({
                'id': str(doc.id),
                'name': doc.name or '',
                'mime_type': doc.mime_type or '',
                'file_url': url,
            })
        return result


# =========================================================================
# EVENT (leitura)
# =========================================================================

class BriefingEventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source='get_kind_display', read_only=True,
    )
    author_email = serializers.SerializerMethodField()
    author_kind = serializers.SerializerMethodField()

    class Meta:
        model = BriefingEvent
        fields = [
            'id',
            'kind',
            'kind_display',
            'question_id',
            'content',
            'author_email',
            'author_kind',
            'created_at',
        ]
        read_only_fields = fields

    def get_author_email(self, obj):
        if obj.user:
            return obj.user.email
        if obj.portal_session and obj.portal_session.client:
            return obj.portal_session.client.email or ''
        return ''

    def get_author_kind(self, obj):
        if obj.user_id:
            return 'user'
        if obj.portal_session_id:
            return 'portal'
        return 'system'


# =========================================================================
# BRIEFING — listagem
# =========================================================================

class BriefingListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True,
    )
    template_name = serializers.CharField(
        source='template.name', read_only=True, allow_null=True,
    )
    cover_url = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Briefing
        fields = [
            'id',
            'title',
            'status',
            'status_display',
            'client',
            'client_name',
            'template',
            'template_name',
            'cover_url',
            'expires_at',
            'progress',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_cover_url(self, obj):
        request = self.context.get('request') if self.context else None
        return _briefing_cover_url(obj, request)

    def get_progress(self, obj):
        return BriefingService.compute_progress(obj)


# =========================================================================
# BRIEFING — detalhe
# =========================================================================

class BriefingDetailSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True,
    )
    client_name = serializers.CharField(
        source='client.name', read_only=True, allow_null=True,
    )
    template_name = serializers.CharField(
        source='template.name', read_only=True, allow_null=True,
    )
    cover_url = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    answers = serializers.SerializerMethodField()
    structure_snapshot = serializers.SerializerMethodField()
    moodboard_images = serializers.SerializerMethodField()
    workspace_id = serializers.UUIDField(
        source='workspace.id', read_only=True,
    )

    class Meta:
        model = Briefing
        fields = [
            'id',
            'workspace_id',
            'title',
            'status',
            'status_display',
            'client',
            'client_name',
            'template',
            'template_name',
            'cover_url',
            'structure_snapshot',
            'moodboard_images',
            'expires_at',
            'started_at',
            'completed_at',
            'cancelled_at',
            'progress',
            'answers',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_cover_url(self, obj):
        request = self.context.get('request') if self.context else None
        return _briefing_cover_url(obj, request)

    def get_progress(self, obj):
        return BriefingService.compute_progress(obj)

    def get_structure_snapshot(self, obj):
        request = self.context.get('request') if self.context else None
        return _expand_structure_snapshot(obj.structure_snapshot, request)

    def get_answers(self, obj):
        request = self.context.get('request') if self.context else None
        qs = obj.answers.select_related(
            'latest_event', 'latest_audio',
        ).prefetch_related('attachments').order_by('created_at')
        return BriefingAnswerSerializer(
            qs, many=True, context={'request': request},
        ).data

    def get_moodboard_images(self, obj):
        """
        Monta a lista de imagens que o CLIENTE enviou/escolheu,
        já com URLs resolvidas.

        Fontes:
            1. Attachments da resposta (uploads do cliente).
            2. Opções escolhidas (single_choice / multiple_choice)
               cuja `image_document_id` aponta para um Document.
        """
        request = self.context.get('request') if self.context else None
        result = []
        seen = set()

        answers = obj.answers.prefetch_related('attachments')
        answers_by_qid = {str(a.question_id): a for a in answers}

        # 1) Attachments (uploads)
        for answer in answers_by_qid.values():
            for doc in answer.attachments.all():
                url = _doc_url(doc, request)
                if not url:
                    continue
                key = f'upload:{doc.id}'
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    'id': str(doc.id),
                    'kind': 'upload',
                    'url': url,
                    'name': doc.name or '',
                    'mime_type': doc.mime_type or '',
                    'question_id': str(answer.question_id),
                })

        # 2) Opções escolhidas (com imagem)
        for q in obj.snapshot_questions():
            qid = str(q['id'])
            answer = answers_by_qid.get(qid)
            if answer is None:
                continue
            content = (answer.latest_content or '').strip()
            if not content:
                continue
            options = q.get('options') or []
            if not isinstance(options, list):
                continue

            chosen_texts = {
                t.strip() for t in content.split(',') if t.strip()
            }
            doc_ids = [
                str(o.get('image_document_id'))
                for o in options
                if isinstance(o, dict) and o.get('image_document_id')
            ]
            if not doc_ids:
                continue
            docs = _load_docs_map(doc_ids, request)

            for opt in options:
                if not isinstance(opt, dict):
                    continue
                opt_text = (opt.get('text') or '').strip()
                if opt_text not in chosen_texts:
                    continue
                doc_id = opt.get('image_document_id')
                if not doc_id:
                    continue
                doc = docs.get(str(doc_id))
                if not doc:
                    continue
                key = f'chosen:{doc_id}'
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    'id': str(doc_id),
                    'kind': 'chosen',
                    'url': doc['file_url'],
                    'name': doc['name'] or opt_text,
                    'mime_type': doc['mime_type'] or '',
                    'question_id': qid,
                    'option_text': opt_text,
                })

        return result


# =========================================================================
# BRIEFING — criação
# =========================================================================

class BriefingCreateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField()
    client_id = serializers.CharField()
    title = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
    )
    expires_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )


# =========================================================================
# BRIEFING — reopen
# =========================================================================

class BriefingReopenSerializer(serializers.Serializer):
    new_expires_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=1000,
    )