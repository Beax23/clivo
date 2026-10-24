"""
GoogleFormsService — buscar, pré-visualizar e importar formulários
Google Forms.

RESPONSABILIDADES
-----------------
1. `search_forms(workspace, query)` — lista os formulários via
   Google Drive API (filtrando pelo MIME type
   `application/vnd.google-apps.form`), porque a Forms API não
   tem endpoint para listar.

2. `preview_form(workspace, form_url_or_id)` — busca o payload
   do formulário e devolve um resumo SEM persistir nada.

3. `import_form(workspace, form_url_or_id, template_name, actor)` —
   cria um NOVO BriefingTemplate no workspace, populando com
   sessões, perguntas E imagens (baixadas do Google e salvas
   como Documents no workspace).

MAPEAMENTO DE TIPOS
-------------------
Todos os 12 tipos nativos do Google Forms são mapeados para
tipos correspondentes no Clivo:

    Forms                             Clivo
    ─────────────────────────────────────────────────────
    Resposta curta                    short_text
    Parágrafo                         long_text
    Múltipla escolha (RADIO)          single_choice
    Caixas de seleção (CHECKBOX)      multiple_choice
    Lista suspensa (DROP_DOWN)        dropdown
    Escala linear                     scale
    Classificação                     rating
    Grade de múltipla escolha         grid_single
    Grade da caixa de seleção         grid_multiple
    Data                              date
    Horário                           time
    Upload de arquivo                 file_upload

IMAGENS
-------
As imagens são baixadas via `contentUri` da Forms API e salvas
como `Document` no workspace, então referenciadas pelos campos
`image_document_id` (em options) ou `reference_document_ids`
(imagem da pergunta).
"""

import logging
import re
from typing import Optional

import httpx

from apps.integrations.exceptions import (
    ConnectionNotEstablishedError,
    ConnectionExpiredError,
    IntegrationError,
    InsufficientScopesError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitError,
    UnsupportedResourceError,
)
from apps.integrations.models import WorkspaceIntegration
from apps.integrations.services.access import WorkspaceIntegrationService
from apps.integrations.services.integration_service import IntegrationService

logger = logging.getLogger('integrations')


# =========================================================================
# CONSTANTES
# =========================================================================

PROVIDER_KEY = 'google'

DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
GOOGLE_FORMS_MIME_TYPE = 'application/vnd.google-apps.form'
FORMS_GET_URL_TEMPLATE = 'https://forms.googleapis.com/v1/forms/{form_id}'

HTTP_TIMEOUT_SECONDS = 15.0
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 30.0

REQUIRED_SCOPE = 'https://www.googleapis.com/auth/forms.body.readonly'
MAX_TEMPLATE_NAME_LENGTH = 200


_FORMS_ID_PATTERN = re.compile(
    r'docs\.google\.com/forms/d/(?:e/)?([A-Za-z0-9_-]+)',
)
_FORMS_SHORT_URL_PATTERN = re.compile(
    r'^https?://forms\.gle/[A-Za-z0-9]+/?$',
)


# =========================================================================
# ERRO DE ESCOPO INSUFICIENTE
# =========================================================================

class FormsScopeMissingError(InsufficientScopesError):
    """A integração Google existe, mas não tem o escopo de Forms."""
    pass


# =========================================================================
# SERVIÇO
# =========================================================================

class GoogleFormsService:

    # =====================================================================
    # BUSCA
    # =====================================================================

    @staticmethod
    def search_forms(*, workspace, query: str = '') -> list[dict]:
        """Lista os formulários da conta Google conectada."""
        integration = WorkspaceIntegrationService.get_for_workspace(
            workspace=workspace,
            provider_key=PROVIDER_KEY,
        )
        access_token = IntegrationService.get_valid_access_token(integration)
        GoogleFormsService._assert_forms_scope(integration)

        raw_forms = GoogleFormsService._fetch_forms_list(access_token)
        forms = [
            GoogleFormsService._normalize_form_summary(f)
            for f in raw_forms
        ]

        if query:
            q = query.strip().lower()
            if q:
                forms = [
                    f for f in forms
                    if q in (f.get('name') or '').lower()
                ]
        return forms

    # =====================================================================
    # PREVIEW
    # =====================================================================

    @staticmethod
    def preview_form(*, workspace, form_url_or_id: str) -> dict:
        """Pré-visualiza um formulário SEM persistir nada."""
        from django.core.exceptions import ValidationError

        form_id = GoogleFormsService._extract_form_id(form_url_or_id)
        if not form_id:
            raise ValidationError(
                'URL do Google Forms inválida. Cole o link do formulário.'
            )

        integration = WorkspaceIntegrationService.get_for_workspace(
            workspace=workspace,
            provider_key=PROVIDER_KEY,
        )
        access_token = IntegrationService.get_valid_access_token(integration)
        GoogleFormsService._assert_forms_scope(integration)

        raw_form = GoogleFormsService._fetch_form_payload(
            access_token=access_token,
            form_id=form_id,
        )
        normalized = GoogleFormsService._normalize_form(raw_form)

        total_questions = sum(
            len(sec.get('questions', []))
            for sec in normalized.get('sections', [])
        )

        return {
            'form_id': form_id,
            'form_name': normalized['name'],
            'form_description': normalized['description'],
            'sections_count': len(normalized.get('sections', [])),
            'questions_count': total_questions,
        }

    # =====================================================================
    # IMPORTAÇÃO
    # =====================================================================

    @staticmethod
    def import_form(
        *,
        workspace,
        form_url_or_id: str,
        template_name: str = '',
        actor=None,
    ) -> dict:
        """Importa um formulário criando um NOVO BriefingTemplate."""
        from django.core.exceptions import ValidationError

        form_id = GoogleFormsService._extract_form_id(form_url_or_id)
        if not form_id:
            raise ValidationError(
                'URL do Google Forms inválida. Cole o link do formulário.'
            )

        integration = WorkspaceIntegrationService.get_for_workspace(
            workspace=workspace,
            provider_key=PROVIDER_KEY,
        )
        access_token = IntegrationService.get_valid_access_token(integration)
        GoogleFormsService._assert_forms_scope(integration)

        raw_form = GoogleFormsService._fetch_form_payload(
            access_token=access_token,
            form_id=form_id,
        )
        normalized = GoogleFormsService._normalize_form(raw_form)

        final_name = (template_name or '').strip()
        if not final_name:
            final_name = normalized['name']
        final_name = final_name[:MAX_TEMPLATE_NAME_LENGTH]

        result = GoogleFormsService._create_template_from_form(
            workspace=workspace,
            normalized_form=normalized,
            template_name=final_name,
            actor=actor,
            access_token=access_token,
        )

        return {
            'imported': True,
            'form_id': form_id,
            'template_id': str(result['template_id']),
            'template_name': result['template_name'],
            'sections_created': result['sections_created'],
            'questions_created': result['questions_created'],
        }

    # =====================================================================
    # HELPERS DE URL
    # =====================================================================

    @staticmethod
    def _extract_form_id(url_or_id: str) -> Optional[str]:
        if not url_or_id:
            return None
        value = url_or_id.strip()

        match = _FORMS_ID_PATTERN.search(value)
        if match:
            return match.group(1)

        if _FORMS_SHORT_URL_PATTERN.match(value):
            logger.info(
                'URL encurtada do Forms (não suportada no V1): %s', value,
            )
            return None

        if re.match(r'^[A-Za-z0-9_-]{20,}$', value):
            return value

        return None

    # =====================================================================
    # CHAMADAS À API DO GOOGLE
    # =====================================================================

    @staticmethod
    def _fetch_forms_list(access_token: str) -> list[dict]:
        """Lista os formulários do usuário via Drive API."""
        params = {
            'q': (
                f"mimeType='{GOOGLE_FORMS_MIME_TYPE}' and trashed=false"
            ),
            'fields': (
                'files(id,name,description,webViewLink,'
                'createdTime,modifiedTime),nextPageToken'
            ),
            'pageSize': 100,
            'orderBy': 'modifiedTime desc',
        }

        all_files: list = []
        page_token = None

        while True:
            if page_token:
                params['pageToken'] = page_token
            else:
                params.pop('pageToken', None)

            try:
                response = httpx.get(
                    DRIVE_FILES_URL,
                    headers={'Authorization': f'Bearer {access_token}'},
                    params=params,
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(
                    'A API do Google Drive não respondeu a tempo.',
                    context={
                        'provider_key': PROVIDER_KEY,
                        'timeout_s': int(HTTP_TIMEOUT_SECONDS),
                    },
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderServerError(
                    'Falha de rede ao consultar o Google Drive.',
                    context={'provider_key': PROVIDER_KEY},
                ) from exc

            GoogleFormsService._raise_for_status(response)

            try:
                data = response.json()
            except ValueError:
                logger.warning(
                    'Google Drive retornou payload não-JSON em /files'
                )
                return all_files

            files = data.get('files') or []
            if isinstance(files, list):
                all_files.extend(files)

            page_token = data.get('nextPageToken')
            if not page_token:
                break

        normalized = []
        for f in all_files:
            normalized.append({
                'formId': f.get('id', ''),
                'info': {
                    'title': f.get('name', ''),
                    'description': f.get('description', ''),
                },
                'responderUri': f.get('webViewLink', ''),
            })

        logger.info(
            'Drive API retornou %d formulários', len(normalized),
        )
        return normalized

    @staticmethod
    def _fetch_form_payload(*, access_token: str, form_id: str) -> dict:
        """Busca o payload completo de um formulário (Forms API get)."""
        url = FORMS_GET_URL_TEMPLATE.format(form_id=form_id)

        try:
            response = httpx.get(
                url,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                'A API do Google Forms não respondeu a tempo.',
                context={
                    'provider_key': PROVIDER_KEY,
                    'form_id': form_id,
                    'timeout_s': int(HTTP_TIMEOUT_SECONDS),
                },
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderServerError(
                'Falha de rede ao consultar o Google Forms.',
                context={'provider_key': PROVIDER_KEY, 'form_id': form_id},
            ) from exc

        GoogleFormsService._raise_for_status(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise IntegrationError(
                'O Google Forms devolveu uma resposta inválida.',
                context={
                    'provider_key': PROVIDER_KEY,
                    'form_id': form_id,
                    'error_type': 'invalid_json',
                },
            ) from exc

        if not isinstance(data, dict):
            raise IntegrationError(
                'O Google Forms devolveu um payload inesperado.',
                context={
                    'provider_key': PROVIDER_KEY,
                    'form_id': form_id,
                    'error_type': 'unexpected_payload_type',
                },
            )

        items = data.get('items') or []
        info = data.get('info') or {}
        logger.info(
            'Form payload obtido | form_id=%s | title=%r | items=%d',
            form_id,
            info.get('title', ''),
            len(items) if isinstance(items, list) else 0,
        )
        return data

    @staticmethod
    def _download_image_bytes(
        *,
        access_token: str,
        image_payload: dict,
    ) -> Optional[tuple]:
        """
        Baixa os bytes de uma imagem do Google Forms.

        Aceita `contentUri` (link temporário baixável) ou
        `sourceUri` (referência interna). Retorna (bytes, mime_type)
        ou None se falhar.
        """
        if not isinstance(image_payload, dict):
            return None

        url = (
            image_payload.get('contentUri')
            or image_payload.get('sourceUri')
        )
        if not url:
            return None

        try:
            response = httpx.get(
                url,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                'Falha de rede ao baixar imagem do Forms: %s',
                type(exc).__name__,
            )
            return None

        if response.status_code != 200:
            logger.warning(
                'Google devolveu %s ao baixar imagem do Forms',
                response.status_code,
            )
            return None

        content_type = (
            response.headers.get('Content-Type')
            or 'image/png'
        )
        content_type = content_type.split(';')[0].strip()

        return response.content, content_type

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code

        if 200 <= status < 300:
            return

        if status == 401:
            raise ConnectionExpiredError(
                'A credencial do Google foi recusada. Reconecte.',
                context={'provider_key': PROVIDER_KEY, 'status_code': 401},
            )

        if status == 403:
            raise FormsScopeMissingError(
                'A conta Google conectada não tem permissão para '
                'acessar os formulários. Reconecte autorizando o '
                'acesso ao Google Forms.',
                context={'provider_key': PROVIDER_KEY, 'status_code': 403},
            )

        if status == 404:
            raise IntegrationError(
                'Recurso não encontrado no Google.',
                context={'provider_key': PROVIDER_KEY, 'status_code': 404},
            )

        if status == 429:
            retry_after = response.headers.get('Retry-After')
            try:
                retry_after_s = int(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after_s = None
            raise RateLimitError(
                'A API do Google está limitando requisições.',
                context={
                    'provider_key': PROVIDER_KEY,
                    'retry_after_s': retry_after_s,
                },
            )

        if 500 <= status < 600:
            raise ProviderServerError(
                f'Erro {status} na API do Google.',
                context={'provider_key': PROVIDER_KEY, 'status_code': status},
            )

        raise IntegrationError(
            f'Erro {status} na API do Google.',
            context={'provider_key': PROVIDER_KEY, 'status_code': status},
        )

    # =====================================================================
    # NORMALIZAÇÃO
    # =====================================================================

    @staticmethod
    def _normalize_form_summary(raw: dict) -> dict:
        form_id = str(raw.get('formId') or '')
        info = raw.get('info') or {}
        name = (info.get('title') or '').strip()
        description = (info.get('description') or '').strip()
        url = raw.get('responderUri') or ''

        if not url and form_id:
            url = f'https://docs.google.com/forms/d/{form_id}/viewform'

        return {
            'id': form_id,
            'name': name or f'Formulário {form_id[:8]}',
            'description': description,
            'url': url,
        }

    @staticmethod
    def _normalize_form(raw: dict) -> dict:
        """
        Converte o payload completo de um formulário no contrato
        interno do Clivo.

        Preserva as imagens das opções no campo `_raw_image` (dict
        cru vindo do Google). O download real acontece depois, na
        criação do template.
        """
        info = raw.get('info') or {}
        items = raw.get('items') or []

        sections = []
        current = {
            'title': (info.get('title') or '').strip() or 'Formulário',
            'description': (info.get('description') or '').strip(),
            'questions': [],
        }

        for item in items:
            title = (item.get('title') or '').strip()

            if 'pageBreakItem' in item:
                if current['questions'] or sections:
                    sections.append(current)
                current = {
                    'title': title or f'Seção {len(sections) + 1}',
                    'description': (item.get('description') or '').strip(),
                    'questions': [],
                }
                continue

            if 'questionGroupItem' in item:
                grid_questions = (
                    GoogleFormsService._normalize_question_group(item)
                )
                current['questions'].extend(grid_questions)
                continue

            question = GoogleFormsService._normalize_question(item)
            if question is not None:
                current['questions'].append(question)

        if current['questions'] or not sections:
            sections.append(current)

        return {
            'id': str(raw.get('formId') or ''),
            'name': (
                (info.get('title') or '').strip()
                or 'Formulário importado'
            ),
            'description': (info.get('description') or '').strip(),
            'sections': sections,
        }

    @staticmethod
    def _normalize_question(item: dict) -> Optional[dict]:
        """Converte um item de pergunta em uma pergunta do Clivo."""
        qi = item.get('questionItem')
        if not qi:
            return None

        question = qi.get('question') or {}
        title = (item.get('title') or '').strip()
        description = (item.get('description') or '').strip()

        if not title:
            return None

        is_required = bool(question.get('required', False))
        question_type, options = GoogleFormsService._map_question_type(
            question,
        )

        raw_q_image = (
            qi.get('image') if isinstance(qi.get('image'), dict)
            else None
        )

        return {
            'text': title,
            'instructions': description,
            'question_type': question_type,
            'allowed_response_formats': (
                GoogleFormsService._formats_for_type(question_type)
            ),
            'options': options,
            'is_required': is_required,
            '_raw_question_image': raw_q_image,
            '_is_grid': False,
        }

    @staticmethod
    def _normalize_question_group(item: dict) -> list:
        """
        Converte um QuestionGroupItem em perguntas do Clivo.

        Caso A — GRID: gera UMA pergunta `grid_single` ou
                 `grid_multiple` com options {rows, columns}.
        Caso B — agrupamento visual: processa cada pergunta
                 interna individualmente.
        """
        qgi = item.get('questionGroupItem') or {}
        group_title = (item.get('title') or '').strip()
        group_description = (item.get('description') or '').strip()

        # -------- CASO A: GRID --------
        if 'grid' in qgi:
            grid = qgi['grid'] or {}
            columns = grid.get('columns') or {}
            col_type = columns.get('type', 'RADIO')
            raw_col_options = columns.get('options') or []

            clean_columns = []
            for opt in raw_col_options:
                text = (opt.get('value') or '').strip()
                if not text:
                    continue
                clean_columns.append({
                    'text': text,
                    '_raw_image': (
                        opt.get('image')
                        if isinstance(opt.get('image'), dict)
                        else None
                    ),
                })

            clean_rows = []
            for row in (qgi.get('questions') or []):
                row_title = (
                    (row.get('rowQuestion') or {}).get('title') or ''
                ).strip()
                if row_title:
                    clean_rows.append(row_title)

            clivo_type = (
                'grid_multiple' if col_type == 'CHECKBOX'
                else 'grid_single'
            )

            return [{
                'text': group_title or 'Grade',
                'instructions': group_description,
                'question_type': clivo_type,
                'allowed_response_formats': ['text'],
                'options': {
                    'rows': clean_rows,
                    'columns': clean_columns,
                },
                'is_required': False,
                '_raw_question_image': None,
                '_is_grid': True,
            }]

        # -------- CASO B: agrupamento visual --------
        result = []
        for question in (qgi.get('questions') or []):
            q_type, q_opts = GoogleFormsService._map_question_type(question)
            title = (
                (question.get('rowQuestion') or {}).get('title')
                or group_title
            )
            if not title:
                continue
            result.append({
                'text': title,
                'instructions': group_description,
                'question_type': q_type,
                'allowed_response_formats': (
                    GoogleFormsService._formats_for_type(q_type)
                ),
                'options': q_opts,
                'is_required': bool(question.get('required', False)),
                '_raw_question_image': None,
                '_is_grid': False,
            })
        return result

    @staticmethod
    def _map_question_type(question: dict) -> tuple:
        """
        Mapeia o tipo do Google Forms para (question_type, options).

        Referência:
            textQuestion (paragraph=false) → short_text
            textQuestion (paragraph=true)  → long_text
            choiceQuestion RADIO           → single_choice
            choiceQuestion CHECKBOX        → multiple_choice
            choiceQuestion DROP_DOWN       → dropdown
            scaleQuestion                  → scale
            ratingQuestion                 → rating
            dateQuestion                   → date
            timeQuestion                   → time
            fileUploadQuestion             → file_upload
            rowQuestion                    → text (pergunta interna)
        """
        if 'scaleQuestion' in question:
            return 'scale', []

        if 'dateQuestion' in question:
            return 'date', []

        if 'timeQuestion' in question:
            return 'time', []

        if 'fileUploadQuestion' in question:
            return 'file_upload', []

        if 'ratingQuestion' in question:
            return 'rating', []

        if 'choiceQuestion' in question:
            cq = question['choiceQuestion']
            g_type = cq.get('type', 'RADIO')
            options = []
            for opt in (cq.get('options') or []):
                text = (opt.get('value') or '').strip()
                if not text:
                    continue
                options.append({
                    'text': text,
                    '_raw_image': (
                        opt.get('image')
                        if isinstance(opt.get('image'), dict)
                        else None
                    ),
                })

            if g_type == 'CHECKBOX':
                return 'multiple_choice', options
            if g_type == 'DROP_DOWN':
                return 'dropdown', options
            return 'single_choice', options

        if 'textQuestion' in question:
            tq = question['textQuestion']
            if tq.get('paragraph'):
                return 'long_text', []
            return 'short_text', []

        if 'rowQuestion' in question:
            return 'text', []

        return 'text', []

    @staticmethod
    def _formats_for_type(question_type: str) -> list:
        """
        Formatos de resposta aceitos por tipo.

        Tipos ESTRUTURADOS (escolha, escala, classificação, data,
        horário, número, sim/não, URL, upload, grid) só aceitam
        `text`. Tipos ABERTOS (texto curto, texto longo, texto
        livre) aceitam texto, áudio e imagem.
        """
        structured = {
            'single_choice',
            'multiple_choice',
            'dropdown',
            'choice',
            'scale',
            'rating',
            'number',
            'grid_single',
            'grid_multiple',
            'date',
            'time',
            'yes_no',
            'url',
            'file_upload',
        }
        if question_type in structured:
            return ['text']
        return ['text', 'audio', 'image']

    # =====================================================================
    # PERSISTÊNCIA — CRIAÇÃO DE NOVO TEMPLATE
    # =====================================================================

    @staticmethod
    def _create_template_from_form(
        *,
        workspace,
        normalized_form: dict,
        template_name: str,
        actor=None,
        access_token: str = '',
    ) -> dict:
        """
        Cria um novo BriefingTemplate no workspace e o popula com
        sessões, perguntas e imagens das opções.
        """
        from apps.briefings.services import BriefingTemplateService

        template = BriefingTemplateService.create_template(
            workspace=workspace,
            name=template_name,
            description=normalized_form.get('description', '') or '',
            category='',
            actor=actor,
        )

        sections_created = 0
        questions_created = 0
        images_imported = 0

        for section_spec in normalized_form.get('sections', []):
            section = BriefingTemplateService.add_section(
                template=template,
                title=section_spec.get('title') or 'Seção',
                description=section_spec.get('description') or '',
                actor=actor,
            )
            sections_created += 1

            for question_spec in section_spec.get('questions', []):
                is_grid = bool(question_spec.get('_is_grid'))
                raw_options = question_spec.get('options')

                # --------------------------------------------------
                # GRID: options é dict {rows, columns}.
                # Precisa baixar imagens das COLUNAS.
                # --------------------------------------------------
                if is_grid and isinstance(raw_options, dict):
                    clean_columns = []
                    for col in (raw_options.get('columns') or []):
                        col_text = (col.get('text') or '').strip()
                        if not col_text:
                            continue
                        col_doc_id = None
                        raw_image = col.get('_raw_image')
                        if raw_image and access_token:
                            col_doc_id = (
                                GoogleFormsService._import_image_as_document(
                                    access_token=access_token,
                                    image_payload=raw_image,
                                    workspace=workspace,
                                    actor=actor,
                                    fallback_name=(
                                        f'{template.name} — coluna '
                                        f'"{col_text[:40]}"'
                                    ),
                                )
                            )
                            if col_doc_id:
                                images_imported += 1
                        clean_columns.append({
                            'text': col_text,
                            'image_document_id': col_doc_id,
                        })

                    grid_options = {
                        'rows': list(raw_options.get('rows') or []),
                        'columns': clean_columns,
                    }

                    BriefingTemplateService.add_question(
                        section=section,
                        text=question_spec.get('text') or '',
                        instructions=question_spec.get('instructions') or '',
                        question_type=question_spec.get(
                            'question_type', 'grid_single',
                        ),
                        allowed_response_formats=question_spec.get(
                            'allowed_response_formats',
                        ),
                        options=grid_options,
                        is_required=question_spec.get('is_required', True),
                        reference_document_ids=None,
                        actor=actor,
                    )
                    questions_created += 1
                    continue

                # --------------------------------------------------
                # Escolha / outros: options é list.
                # --------------------------------------------------
                clean_options = []
                for raw_opt in (raw_options or []):
                    opt_text = (raw_opt.get('text') or '').strip()
                    if not opt_text:
                        continue
                    doc_id = None
                    raw_image = raw_opt.get('_raw_image')
                    if raw_image and access_token:
                        doc_id = (
                            GoogleFormsService._import_image_as_document(
                                access_token=access_token,
                                image_payload=raw_image,
                                workspace=workspace,
                                actor=actor,
                                fallback_name=(
                                    f'{template.name} — opção '
                                    f'"{opt_text[:40]}"'
                                ),
                            )
                        )
                        if doc_id:
                            images_imported += 1
                    clean_options.append({
                        'text': opt_text,
                        'image_document_id': doc_id,
                    })

                # Baixa imagem da pergunta em si (se houver).
                raw_q_image = question_spec.get('_raw_question_image')
                question_image_doc_id = None
                if raw_q_image and access_token:
                    question_image_doc_id = (
                        GoogleFormsService._import_image_as_document(
                            access_token=access_token,
                            image_payload=raw_q_image,
                            workspace=workspace,
                            actor=actor,
                            fallback_name=(
                                f'{template.name} — pergunta '
                                f'"{(question_spec.get("text") or "")[:40]}"'
                            ),
                        )
                    )
                    if question_image_doc_id:
                        images_imported += 1

                ref_ids = (
                    [question_image_doc_id] if question_image_doc_id else None
                )

                BriefingTemplateService.add_question(
                    section=section,
                    text=question_spec.get('text') or '',
                    instructions=question_spec.get('instructions') or '',
                    question_type=question_spec.get(
                        'question_type', 'text',
                    ),
                    allowed_response_formats=question_spec.get(
                        'allowed_response_formats',
                    ),
                    options=clean_options,
                    is_required=question_spec.get('is_required', True),
                    reference_document_ids=ref_ids,
                    actor=actor,
                )
                questions_created += 1

        logger.info(
            'Template importado do Forms | template=%s | sections=%d | '
            'questions=%d | images=%d',
            template.id, sections_created, questions_created,
            images_imported,
        )

        return {
            'template_id': template.id,
            'template_name': template.name,
            'sections_created': sections_created,
            'questions_created': questions_created,
            'images_imported': images_imported,
        }

    @staticmethod
    def _import_image_as_document(
        *,
        access_token: str,
        image_payload: dict,
        workspace,
        actor=None,
        fallback_name: str = 'Imagem importada do Forms',
    ) -> Optional[str]:
        """
        Baixa uma imagem do Google Forms e a salva como Document
        no workspace. Retorna o ID (str) do Document, ou None se
        falhar. Nunca levanta exceção — uma imagem que falha não
        deve interromper a importação do template.
        """
        from apps.documents.models import Document
        from django.core.files.base import ContentFile

        downloaded = GoogleFormsService._download_image_bytes(
            access_token=access_token,
            image_payload=image_payload,
        )
        if downloaded is None:
            return None

        image_bytes, mime_type = downloaded

        ext_map = {
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/gif': 'gif',
            'image/webp': 'webp',
            'image/bmp': 'bmp',
        }
        extension = ext_map.get(mime_type, 'png')

        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '-', fallback_name)[:80]
        file_name = f'{safe_name}.{extension}'

        try:
            document = Document.objects.create(
                workspace=workspace,
                name=fallback_name[:200],
                file=ContentFile(image_bytes, name=file_name),
                extension=extension,
                mime_type=mime_type,
                size=len(image_bytes),
                created_by=actor if (
                    actor and getattr(actor, 'is_authenticated', False)
                ) else None,
            )
        except Exception:
            logger.exception(
                'Falha ao salvar imagem como Document (name=%s)',
                fallback_name,
            )
            return None

        return str(document.id)

    # =====================================================================
    # VALIDAÇÕES
    # =====================================================================

    @staticmethod
    def _assert_forms_scope(integration: WorkspaceIntegration) -> None:
        granted = set(integration.granted_scopes or [])
        if REQUIRED_SCOPE not in granted:
            raise FormsScopeMissingError(
                'A conta Google conectada não autorizou acesso ao '
                'Google Forms. Reconecte autorizando esta permissão.',
                context={
                    'integration_id': str(integration.pk),
                    'required_scope': REQUIRED_SCOPE,
                    'granted_scopes': list(granted),
                },
            )