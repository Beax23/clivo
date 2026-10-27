"""
Testes unitários do AICallService.

Todos usam mock da biblioteca `openai`. Nenhuma chamada real.

O teste de integração real fica em `test_call_ai_integration.py`
(opt-in via env var).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.console.models import (
    Provider, UsageMetric, UsageRecord, ProviderLog,
)
from apps.console.services.ai_call_service import (
    AICallService, AICallError,
)


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def openai_provider(db):
    return Provider.objects.create(
        key='openai', name='OpenAI', category='ai', is_active=True,
    )


@pytest.fixture
def ai_metric(db):
    return UsageMetric.objects.create(
        key='ai.credits', name='AI Credits', unit='token',
        kind='counter', origin='recorded', is_active=True,
    )


@pytest.fixture
def workspace(db):
    from apps.workspaces.models import Workspace
    return Workspace.objects.create(name='WS', slug='ws-ai-call')


# =========================================================================
# HELPERS
# =========================================================================

def _mock_openai_response(content='{"insights": []}', in_tok=100, out_tok=50, rid='req-abc'):
    response = MagicMock()
    response.id = rid
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage = MagicMock()
    response.usage.prompt_tokens = in_tok
    response.usage.completion_tokens = out_tok
    return response


def _allow_quota(mocker):
    """Força `QuotaService.check` a permitir."""
    from apps.console.services.quota_service import QuotaCheckResult
    mocker.patch(
        'apps.console.services.ai_call_service.AICallService._assert_quota_allows',
        return_value=None,
    )


def _allow_quota_via_service(mocker):
    from apps.console.services.quota_service import QuotaCheckResult
    mocker.patch(
        'apps.console.services.quota_service.QuotaService.check',
        return_value=QuotaCheckResult(
            status='ok', allowed=True, quota_bytes=10000, used_bytes=0,
            remaining_bytes=10000, percent=0.0, behavior='hard_limit',
            period='monthly', feature_key='ai', plan_key='pro',
        ),
    )


# =========================================================================
# SUCESSO
# =========================================================================

@pytest.mark.django_db
class TestCallAISuccess:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_call_returns_normalized_payload(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch(
            'openai.OpenAI',
        )
        client = mock_create.return_value
        client.chat.completions.create.return_value = _mock_openai_response()

        result = AICallService.call(
            workspace=workspace,
            operation='intelligence.analysis',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'hi'}],
            request_id='req-1',
        )

        assert result['raw_content'] == '{"insights": []}'
        assert result['input_tokens'] == 100
        assert result['output_tokens'] == 50
        assert result['duration_ms'] >= 0
        assert result['usage_record_id'] is not None
        assert result['provider_request_id'] == 'req-abc'

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_call_creates_usage_record(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        AICallService.call(
            workspace=workspace,
            operation='intelligence.analysis',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-2',
        )

        rec = UsageRecord.objects.get(request_id='req-2')
        assert rec.provider_id == openai_provider.id
        assert rec.metric_id == ai_metric.id
        assert rec.quantity == Decimal('150')
        assert rec.unit == 'token'

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_call_creates_provider_log(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        AICallService.call(
            workspace=workspace,
            operation='intelligence.analysis',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-3',
        )

        log = ProviderLog.objects.get(request_id='req-3')
        assert log.status == 'success'
        assert log.input_units == 100
        assert log.output_units == 50
        assert log.operation == 'intelligence.analysis'


# =========================================================================
# ERROS
# =========================================================================

@pytest.mark.django_db
class TestCallAIErrors:

    def test_no_request_id_raises(
        self, openai_provider, workspace,
    ):
        with pytest.raises(AICallError, match='request_id'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='',
            )

    def test_quota_blocked_raises(
        self, mocker, openai_provider, workspace,
    ):
        from apps.console.services.quota_service import QuotaCheckResult
        mocker.patch(
            'apps.console.services.ai_call_service.AICallService._assert_quota_allows',
            side_effect=AICallError('quota bloqueada'),
        )
        with pytest.raises(AICallError, match='quota'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-x',
            )

    def test_provider_not_found_raises(
        self, mocker, workspace, ai_metric,
    ):
        _allow_quota(mocker)
        with pytest.raises(AICallError, match='não está cadastrado'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='inexistente',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-y',
            )

    def test_provider_inactive_raises(
        self, mocker, ai_metric, workspace,
    ):
        Provider.objects.create(
            key='openai', name='OpenAI', category='ai', is_active=False,
        )
        _allow_quota(mocker)
        with pytest.raises(AICallError, match='inativo'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-z',
            )

    def test_missing_metric_raises(
        self, mocker, openai_provider, workspace,
    ):
        _allow_quota(mocker)
        with pytest.raises(AICallError, match='ai.credits'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-w',
            )

    def test_missing_api_key_raises(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        with override_settings(OPENAI_API_KEY=None):
            with pytest.raises(AICallError, match='OPENAI_API_KEY'):
                AICallService.call(
                    workspace=workspace,
                    operation='op',
                    provider_key='openai',
                    model='m',
                    prompt_version='v1',
                    messages=[],
                    request_id='req-k',
                )

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_provider_failure_does_not_create_usage(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        mock_create.return_value.chat.completions.create.side_effect = (
            RuntimeError('timeout')
        )
        with pytest.raises(AICallError, match='Falha na chamada'):
            AICallService.call(
                workspace=workspace,
                operation='op',
                provider_key='openai',
                model='m',
                prompt_version='v1',
                messages=[],
                request_id='req-fail',
            )
        assert not UsageRecord.objects.filter(
            request_id='req-fail',
        ).exists()
        # Mas ProviderLog de falha foi criado
        assert ProviderLog.objects.filter(
            request_id='req-fail', status='failed',
        ).exists()


# =========================================================================
# IDEMPOTÊNCIA
# =========================================================================

@pytest.mark.django_db
class TestCallAIIdempotency:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_same_request_id_does_not_call_provider_twice(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        provider_client = mock_create.return_value
        provider_client.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        # 1ª chamada
        r1 = AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-idem',
        )
        # 2ª chamada com mesmo request_id
        r2 = AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            request_id='req-idem',
        )

        # Provider foi chamado UMA vez
        assert provider_client.chat.completions.create.call_count == 1
        # Ambos devolvem o mesmo usage_record_id
        assert r1['usage_record_id'] == r2['usage_record_id']
        # Um único UsageRecord
        assert UsageRecord.objects.filter(request_id='req-idem').count() == 1


# =========================================================================
# MULTIMODAL
# =========================================================================

@pytest.mark.django_db
class TestCallAIMultimodal:

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_images_attached_to_last_user_message(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        provider_client = mock_create.return_value
        provider_client.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[
                {'role': 'system', 'content': 'sys'},
                {'role': 'user', 'content': 'text content'},
            ],
            images=[
                {'url': 'https://example.com/img1.jpg', 'mime_type': 'image/jpeg'},
                {'url': 'https://example.com/img2.png', 'mime_type': 'image/png'},
            ],
            request_id='req-img',
        )

        call_args = provider_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        user_msg = messages[-1]
        assert isinstance(user_msg['content'], list)
        assert user_msg['content'][0] == {
            'type': 'text', 'text': 'text content',
        }
        assert user_msg['content'][1] == {
            'type': 'image_url',
            'image_url': {'url': 'https://example.com/img1.jpg'},
        }
        assert user_msg['content'][2] == {
            'type': 'image_url',
            'image_url': {'url': 'https://example.com/img2.png'},
        }

    @override_settings(OPENAI_API_KEY='sk-test')
    def test_invalid_image_url_discarded(
        self, mocker, openai_provider, ai_metric, workspace,
    ):
        _allow_quota(mocker)
        mock_create = mocker.patch('openai.OpenAI')
        provider_client = mock_create.return_value
        provider_client.chat.completions.create.return_value = (
            _mock_openai_response()
        )

        AICallService.call(
            workspace=workspace,
            operation='op',
            provider_key='openai',
            model='gpt-4o-mini',
            prompt_version='v1',
            messages=[{'role': 'user', 'content': 'x'}],
            images=[
                {'url': 'file:///etc/passwd'},
                {'url': 'https://ok.com/i.jpg'},
            ],
            request_id='req-bad-img',
        )

        call_args = provider_client.chat.completions.create.call_args
        user_msg = call_args.kwargs['messages'][-1]
        assert len(user_msg['content']) == 2  # texto + 1 imagem válida