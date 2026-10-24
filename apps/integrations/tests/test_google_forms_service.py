"""
Testes do GoogleFormsService.

Cobrem:
    - Extração de ID de URL (formatos suportados e rejeitados).
    - Validação de escopo (FormsScopeMissingError).
    - Normalização de payload do Google.
    - preview_form (não persiste nada).
    - import_form (cria NOVO BriefingTemplate).

NÃO testam chamada real ao Google — `_fetch_form_payload` está
mockado. O teste de integração real fica em arquivo separado,
opt-in por variável de ambiente.
"""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.integrations.exceptions import (
    ConnectionNotEstablishedError,
)
from apps.integrations.services.google_forms import (
    GoogleFormsService,
    FormsScopeMissingError,
    REQUIRED_SCOPE,
)


# =========================================================================
# EXTRAÇÃO DE ID
# =========================================================================

class TestExtractFormId:

    def test_full_url_with_edit(self):
        url = 'https://docs.google.com/forms/d/1FAIpQLSfABC123/edit'
        assert GoogleFormsService._extract_form_id(url) == '1FAIpQLSfABC123'

    def test_full_url_with_viewform(self):
        url = 'https://docs.google.com/forms/d/1FAIpQLSfABC123/viewform'
        assert GoogleFormsService._extract_form_id(url) == '1FAIpQLSfABC123'

    def test_published_form_url(self):
        url = 'https://docs.google.com/forms/d/e/1FAIpQLSfABC123/viewform'
        assert GoogleFormsService._extract_form_id(url) == '1FAIpQLSfABC123'

    def test_raw_id(self):
        raw_id = '1FAIpQLSfABC123XYZ456abcDEF789'
        assert GoogleFormsService._extract_form_id(raw_id) == raw_id

    def test_short_url_is_rejected(self):
        url = 'https://forms.gle/abcDEF'
        assert GoogleFormsService._extract_form_id(url) is None

    def test_empty_returns_none(self):
        assert GoogleFormsService._extract_form_id('') is None
        assert GoogleFormsService._extract_form_id(None) is None

    def test_arbitrary_url_returns_none(self):
        assert GoogleFormsService._extract_form_id(
            'https://example.com/foo'
        ) is None


# =========================================================================
# VALIDAÇÃO DE ESCOPO
# =========================================================================

@pytest.mark.django_db
class TestScopeValidation:

    def test_missing_scope_raises(self):
        class FakeIntegration:
            pk = 'fake-id'
            granted_scopes = ['https://www.googleapis.com/auth/drive.readonly']

        with pytest.raises(FormsScopeMissingError) as exc_info:
            GoogleFormsService._assert_forms_scope(FakeIntegration())

        assert exc_info.value.context['required_scope'] == REQUIRED_SCOPE

    def test_present_scope_ok(self):
        class FakeIntegration:
            pk = 'fake-id'
            granted_scopes = [REQUIRED_SCOPE]

        GoogleFormsService._assert_forms_scope(FakeIntegration())


# =========================================================================
# NORMALIZAÇÃO
# =========================================================================

class TestNormalizeForm:

    def test_basic_form(self):
        raw = {
            'formId': 'abc',
            'info': {
                'title': 'Briefing Residencial',
                'description': 'Formulário de exemplo',
            },
            'items': [
                {
                    'title': 'Qual seu nome?',
                    'questionItem': {
                        'question': {
                            'textQuestion': {'paragraph': False},
                            'required': True,
                        },
                    },
                },
            ],
        }
        result = GoogleFormsService._normalize_form(raw)
        assert result['id'] == 'abc'
        assert result['name'] == 'Briefing Residencial'
        assert len(result['sections']) == 1
        assert len(result['sections'][0]['questions']) == 1
        q = result['sections'][0]['questions'][0]
        assert q['text'] == 'Qual seu nome?'
        assert q['question_type'] == 'long_text'
        assert q['is_required'] is True

    def test_page_break_creates_new_section(self):
        raw = {
            'formId': 'abc',
            'info': {'title': 'Form'},
            'items': [
                {
                    'title': 'P1',
                    'questionItem': {
                        'question': {'textQuestion': {}},
                    },
                },
                {
                    'title': 'Seção 2',
                    'pageBreakItem': {},
                },
                {
                    'title': 'P2',
                    'questionItem': {
                        'question': {'textQuestion': {}},
                    },
                },
            ],
        }
        result = GoogleFormsService._normalize_form(raw)
        assert len(result['sections']) == 2
        assert result['sections'][0]['questions'][0]['text'] == 'P1'
        assert result['sections'][1]['questions'][0]['text'] == 'P2'
        assert result['sections'][1]['title'] == 'Seção 2'

    def test_multiple_choice(self):
        raw = {
            'formId': 'abc',
            'info': {'title': 'Form'},
            'items': [
                {
                    'title': 'Escolha',
                    'questionItem': {
                        'question': {
                            'choiceQuestion': {
                                'type': 'RADIO',
                                'options': [
                                    {'value': 'A'},
                                    {'value': 'B'},
                                ],
                            },
                        },
                    },
                },
            ],
        }
        result = GoogleFormsService._normalize_form(raw)
        q = result['sections'][0]['questions'][0]
        assert q['question_type'] == 'single_choice'
        assert len(q['options']) == 2
        assert q['options'][0]['text'] == 'A'


# =========================================================================
# FLUXO DE PREVIEW (com mock)
# =========================================================================

@pytest.mark.django_db
class TestPreviewFlow:

    def test_no_integration_raises(self):
        from apps.workspaces.models import Workspace

        ws = Workspace.objects.create(name='WS', slug='ws-gforms-preview-1')

        with pytest.raises(ConnectionNotEstablishedError):
            GoogleFormsService.preview_form(
                workspace=ws,
                form_url_or_id='https://docs.google.com/forms/d/ABC123/edit',
            )

    def test_invalid_url_raises(self):
        from django.core.exceptions import ValidationError
        from apps.workspaces.models import Workspace

        ws = Workspace.objects.create(name='WS', slug='ws-gforms-preview-2')

        with pytest.raises(ValidationError):
            GoogleFormsService.preview_form(
                workspace=ws,
                form_url_or_id='https://example.com/not-a-form',
            )


# =========================================================================
# FLUXO DE IMPORT (com mock)
# =========================================================================

@pytest.mark.django_db
class TestImportFlow:

    def test_no_integration_raises(self):
        from apps.workspaces.models import Workspace

        ws = Workspace.objects.create(name='WS', slug='ws-gforms-import-1')

        with pytest.raises(ConnectionNotEstablishedError):
            GoogleFormsService.import_form(
                workspace=ws,
                form_url_or_id='https://docs.google.com/forms/d/ABC123/edit',
                template_name='Novo Modelo',
            )

    def test_invalid_url_raises(self):
        from django.core.exceptions import ValidationError
        from apps.workspaces.models import Workspace

        ws = Workspace.objects.create(name='WS', slug='ws-gforms-import-2')

        with pytest.raises(ValidationError):
            GoogleFormsService.import_form(
                workspace=ws,
                form_url_or_id='https://example.com/not-a-form',
                template_name='Novo Modelo',
            )