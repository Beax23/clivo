"""
BriefingExportService — gera PDF do briefing.

Dois modos:

    mode='architect' (padrão)
        PDF completo com dados brutos, sem notas privadas mas
        incluindo transcrições, anexos, referências e estado.

    mode='client'
        PDF resumido em formato moodboard, SEM notas internas,
        SEM info de progresso administrativo. Foco em perguntas
        e respostas, com imagens visíveis. Acompanha o e-mail de
        conclusão.

REGRA ARQUITETURAL
------------------
O PDF mostra os dados BRUTOS. Não substitui por resumos.
Não usa IA. Funciona mesmo se o provedor de IA estiver offline.
"""

import logging

from django.template.loader import render_to_string
from django.utils import timezone

from apps.briefings.services.briefing_service import BriefingService

logger = logging.getLogger('briefings')


class BriefingExportService:

    DEFAULT_TEMPLATE = 'briefings/export.html'
    CLIENT_TEMPLATE = 'briefings/export_client.html'

    @staticmethod
    def render_pdf(
        briefing,
        request=None,
        template_name: str = None,
        mode: str = 'architect',
    ) -> tuple:
        """
        Retorna (bytes, filename).

        `mode` decide o template padrão:
            'architect' → briefings/export.html
            'client'    → briefings/export_client.html

        `template_name` sobrescreve o padrão.
        """
        if template_name is None:
            template_name = (
                BriefingExportService.CLIENT_TEMPLATE
                if mode == 'client'
                else BriefingExportService.DEFAULT_TEMPLATE
            )

        context = BriefingExportService._build_context(
            briefing, request=request, mode=mode,
        )
        html = render_to_string(
            template_name,
            context,
            request=request,
        )

        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError(
                'WeasyPrint não instalado. Rode `pip install weasyprint` '
                'e certifique-se de que as bibliotecas de sistema '
                '(pango, cairo) estão disponíveis.'
            ) from exc

        base_url = (
            request.build_absolute_uri('/') if request else None
        )
        pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()

        return pdf_bytes, context['filename']

    # ------------------------------------------------------------------
    # CONTEXTO
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(briefing, request=None, mode='architect') -> dict:
        answers_by_qid = {
            str(a.question_id): a
            for a in briefing.answers.select_related(
                'latest_audio', 'latest_event',
            ).prefetch_related('attachments')
        }

        sections_payload = []
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
                answer = answers_by_qid.get(qid)

                refs = []
                for doc_id in (q.get('reference_document_ids') or []):
                    refs.append({'id': doc_id, 'url': ''})

                latest_content = ''
                latest_transcription = ''
                transcription_status = ''
                attachments = []
                audio_url = ''
                updated_at = None
                if answer is not None:
                    latest_content = answer.latest_content or ''
                    latest_transcription = answer.latest_transcription or ''
                    transcription_status = (
                        answer.get_transcription_status_display()
                    )
                    updated_at = answer.updated_at
                    for doc in answer.attachments.all():
                        attachments.append({
                            'id': str(doc.id),
                            'name': doc.full_name,
                            'url': BriefingExportService._doc_url(
                                doc, request,
                            ),
                        })
                    if answer.latest_audio:
                        audio_url = BriefingExportService._doc_url(
                            answer.latest_audio, request,
                        )

                questions_payload.append({
                    'id': qid,
                    'text': q.get('text', ''),
                    'instructions': q.get('instructions', ''),
                    'is_required': bool(q.get('is_required', True)),
                    'reference_documents': refs,
                    'state': answer.state if answer else 'pending',
                    'latest_content': latest_content,
                    'latest_transcription': latest_transcription,
                    'transcription_status': transcription_status,
                    'audio_url': audio_url,
                    'attachments': attachments,
                    'updated_at': updated_at,
                })
            sections_payload.append({
                'id': section.get('id'),
                'title': section.get('title', ''),
                'description': section.get('description', ''),
                'questions': questions_payload,
            })

        progress = BriefingService.compute_progress(briefing)

        now = timezone.now()
        slug = ''.join(
            c if c.isalnum() else '-'
            for c in (briefing.title or 'briefing').lower()
        ).strip('-') or 'briefing'
        filename = f"briefing-{slug}-{now:%Y%m%d}.pdf"

        return {
            'briefing': briefing,
            'client_name': briefing.client.name if briefing.client else '',
            'workspace_name': (
                briefing.workspace.name if briefing.workspace else ''
            ),
            'sections': sections_payload,
            'progress': progress,
            'generated_at': now,
            'filename': filename,
            'mode': mode,
        }

    @staticmethod
    def _doc_url(doc, request=None) -> str:
        try:
            if doc.file:
                return doc.file.url
        except Exception:
            pass
        if request is not None:
            return request.build_absolute_uri(
                f'/api/documents/{doc.id}/preview/'
            )
        return f'/api/documents/{doc.id}/preview/'