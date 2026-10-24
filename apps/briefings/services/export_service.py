"""
BriefingExportService — extrai o briefing em PDF.

REGRA ARQUITETURAL
------------------
`briefings` só produz DADO BRUTO, mas em duas visões:

    mode='client'
        Visão do CLIENTE.
        - perguntas + respostas do cliente (texto / áudio / transcrição)
        - imagens escolhidas nas opções
        - imagens enviadas pelo cliente
        - moodboard pessoal (as imagens do cliente juntas)
        - sem referências do arquiteto, sem dados internos.

    mode='architect'
        Visão do ARQUITETO.
        - mesmo dado bruto do cliente
        - MAIS referências do arquiteto (imagens de apoio)
        - MAIS transcrições
        - MAIS audiência administrativa
        - MAIS informações de estado / progresso
        - sem notas privadas (Journal).

TEMPLATES
---------
Os templates de PDF vivem em `ui/templates/portal/`:
    briefing_raw_client_pdf.html
    briefing_raw_architect_pdf.html

Eles são HTML/CSS puro, sem JS. Os templates de navegador
(`briefing_raw_client.html` / `briefing_raw_architect.html`)
continuam independentes e não são usados aqui.

O `intelligence` (futuro) vai consumir esses mesmos dados e produzir
o material final (resumos, análises). `briefings` não faz isso.
"""

import logging
import os
import sys

from django.template.loader import render_to_string
from django.utils import timezone

from apps.briefings.services.briefing_service import BriefingService

logger = logging.getLogger('briefings')


class BriefingExportService:

    CLIENT_TEMPLATE = 'portal/briefing_raw_client_pdf.html'
    ARCHITECT_TEMPLATE = 'portal/briefing_raw_architect_pdf.html'

    # ------------------------------------------------------------------
    # Bootstrap do WeasyPrint no Windows
    # ------------------------------------------------------------------
    _weasyprint_bootstrapped = False

    @classmethod
    def _bootstrap_weasyprint(cls):
        """
        No Windows, o WeasyPrint precisa carregar DLLs do GTK3 via cffi.
        O Python não herda o PATH do sistema em runtime, então registramos
        o diretório das DLLs manualmente (os.add_dll_directory, Python 3.8+)
        antes do primeiro import. É idempotente.
        """
        if cls._weasyprint_bootstrapped:
            return
        cls._weasyprint_bootstrapped = True

        if sys.platform != 'win32':
            return

        candidate_dirs = [
            os.environ.get('WEASYPRINT_DLL_DIRECTORIES', ''),
            r'C:\Program Files\GTK3-Runtime Win64\bin',
            r'C:\Program Files (x86)\GTK3-Runtime Win64\bin',
        ]

        for d in candidate_dirs:
            if d and os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                    logger.info(
                        'WeasyPrint: DLL directory registrado: %s', d,
                    )
                    break
                except Exception:
                    logger.exception(
                        'WeasyPrint: falha ao registrar DLL dir %s', d,
                    )

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------
    @staticmethod
    def render_pdf(
        briefing,
        request=None,
        mode: str = 'client',
        template_name: str = None,
    ) -> tuple:
        """
        Retorna (bytes, filename).

        `mode`: 'client' ou 'architect'.
        `template_name`: opcional. Quando informado, sobrepõe o template
        derivado de `mode`. Aceito por compatibilidade com chamadores
        antigos (NotificationService, BriefingSendService).

        Levanta RuntimeError com mensagem CLARA se o WeasyPrint
        não estiver disponível (para o frontend exibir ao usuário).
        """
        if not template_name:
            template_name = (
                BriefingExportService.CLIENT_TEMPLATE
                if mode == 'client'
                else BriefingExportService.ARCHITECT_TEMPLATE
            )

        context = BriefingExportService._build_context(
            briefing, request=request, mode=mode,
        )
        html = render_to_string(
            template_name, context, request=request,
        )

        BriefingExportService._bootstrap_weasyprint()

        try:
            from weasyprint import HTML
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                'WeasyPrint não conseguiu carregar as bibliotecas nativas. '
                'No Windows, instale o GTK3 Runtime e adicione '
                'C:\\Program Files\\GTK3-Runtime Win64\\bin ao PATH, '
                'ou defina WEASYPRINT_DLL_DIRECTORIES apontando para essa '
                f'pasta. Erro original: {exc}'
            ) from exc

        try:
            base_url = (
                request.build_absolute_uri('/') if request else None
            )
            pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
        except Exception as exc:
            logger.exception('Falha ao gerar PDF com WeasyPrint')
            raise RuntimeError(
                f'WeasyPrint falhou ao gerar o PDF: {exc}'
            ) from exc

        return pdf_bytes, context['filename']

    @staticmethod
    def _build_context(briefing, request=None, mode='client') -> dict:
        answers_by_qid = {
            str(a.question_id): a
            for a in briefing.answers.select_related(
                'latest_audio', 'latest_event',
            ).prefetch_related('attachments')
        }

        from apps.documents.models import Document

        def _docs_by_id(ids):
            ids = [str(x) for x in (ids or []) if x]
            if not ids:
                return {}
            docs = Document.objects.filter(id__in=ids).only(
                'id', 'name', 'mime_type', 'file',
            )
            return {str(d.id): d for d in docs}

        def _doc_url(doc):
            if not doc or not doc.file:
                return ''
            try:
                url = doc.file.url
            except Exception:
                return ''
            if not url:
                return ''
            if request is not None and not url.startswith(
                ('http://', 'https://'),
            ):
                try:
                    url = request.build_absolute_uri(url)
                except Exception:
                    pass
            return url

        sections_payload = []
        client_images_all = []
        architect_references_all = []

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

                reference_images = []
                ref_ids = list(q.get('reference_document_ids') or [])
                if ref_ids:
                    refs_map = _docs_by_id(ref_ids)
                    for rid in ref_ids:
                        d = refs_map.get(str(rid))
                        if not d:
                            continue
                        url = _doc_url(d)
                        if not url:
                            continue
                        entry = {
                            'id': str(d.id),
                            'name': d.name or '',
                            'url': url,
                        }
                        reference_images.append(entry)
                        architect_references_all.append(entry)

                chosen_images = []
                if answer is not None:
                    options = q.get('options') or []
                    content = (answer.latest_content or '').strip()
                    if isinstance(options, list) and content:
                        chosen_texts = {
                            t.strip() for t in content.split(',')
                            if t.strip()
                        }
                        doc_ids = [
                            str(o.get('image_document_id'))
                            for o in options
                            if isinstance(o, dict)
                            and o.get('image_document_id')
                        ]
                        docs_map = _docs_by_id(doc_ids)
                        for o in options:
                            if not isinstance(o, dict):
                                continue
                            opt_text = (o.get('text') or '').strip()
                            if opt_text not in chosen_texts:
                                continue
                            doc_id = o.get('image_document_id')
                            if not doc_id:
                                continue
                            d = docs_map.get(str(doc_id))
                            if not d:
                                continue
                            url = _doc_url(d)
                            if not url:
                                continue
                            entry = {
                                'id': str(d.id),
                                'text': opt_text,
                                'name': d.name or '',
                                'url': url,
                            }
                            chosen_images.append(entry)
                            client_images_all.append(entry)

                attachments = []
                if answer is not None:
                    for doc in answer.attachments.all():
                        url = _doc_url(doc)
                        if not url:
                            continue
                        entry = {
                            'id': str(doc.id),
                            'name': doc.full_name,
                            'url': url,
                        }
                        attachments.append(entry)
                        client_images_all.append(entry)

                latest_content = ''
                latest_transcription = ''
                transcription_status = ''
                audio_url = ''
                updated_at = None
                if answer is not None:
                    latest_content = answer.latest_content or ''
                    latest_transcription = answer.latest_transcription or ''
                    transcription_status = (
                        answer.get_transcription_status_display()
                    )
                    updated_at = answer.updated_at
                    if answer.latest_audio:
                        audio_url = _doc_url(answer.latest_audio)

                questions_payload.append({
                    'id': qid,
                    'text': q.get('text', ''),
                    'instructions': q.get('instructions', ''),
                    'question_type': q.get('question_type', 'text'),
                    'is_required': bool(q.get('is_required', True)),
                    'position': q.get('position', 0),
                    'is_custom': bool(q.get('is_custom', False)),
                    'state': answer.state if answer else 'pending',
                    'latest_content': latest_content,
                    'latest_transcription': latest_transcription,
                    'transcription_status': transcription_status,
                    'audio_url': audio_url,
                    'reference_images': reference_images,
                    'chosen_images': chosen_images,
                    'attachments': attachments,
                    'updated_at': updated_at,
                })
            sections_payload.append({
                'id': section.get('id'),
                'title': section.get('title', ''),
                'description': section.get('description', ''),
                'position': section.get('position', 0),
                'questions': questions_payload,
            })

        progress = BriefingService.compute_progress(briefing)

        now = timezone.now()
        slug = ''.join(
            c if c.isalnum() else '-'
            for c in (briefing.title or 'briefing').lower()
        ).strip('-') or 'briefing'
        suffix = 'cliente' if mode == 'client' else 'arquiteto'
        filename = f"briefing-{slug}-{suffix}-{now:%Y%m%d}.pdf"

        from django.conf import settings
        portal_url = ''
        try:
            base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
            if not base and request is not None:
                base = request.build_absolute_uri('/').rstrip('/')
            if base:
                portal_url = f'{base}/portal/briefings/{briefing.id}/'
        except Exception:
            portal_url = ''

        return {
            'briefing': briefing,
            'client_name': briefing.client.name if briefing.client else '',
            'workspace_name': (
                briefing.workspace.name if briefing.workspace else ''
            ),
            'portal_url': portal_url,
            'intro_message': briefing.intro_message or '',
            'sections': sections_payload,
            'progress': progress,
            'generated_at': now,
            'filename': filename,
            'mode': mode,
            'client_images_all': client_images_all,
            'architect_references_all': architect_references_all,
        }