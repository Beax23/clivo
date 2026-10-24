"""
Views DRF para a API de Google Forms.

Endpoints:

    GET  /api/integrations/google/forms/search/
        Lista formulários da conta conectada.
        Se não houver integração ativa → 428 Precondition Required.

    POST /api/integrations/google/forms/preview/
        Busca o resumo de um formulário SEM persistir nada.
        Usado pelo frontend para montar a tela de confirmação
        antes de criar o template.

    POST /api/integrations/google/forms/import/
        Cria um NOVO BriefingTemplate com as sessões e perguntas
        do formulário. Devolve o `template_id` criado.
        Se não houver integração ativa → 428 Precondition Required.

SOBRE 428:
    Usamos HTTP 428 (Precondition Required) para sinalizar que
    falta uma condição prévia (integração conectada). O frontend
    trata 428 como "ofereça conectar o Google".

SOBRE O WORKSPACE:
    O workspace é resolvido a partir da sessão
    (`current_workspace_id`). NÃO aceitamos `workspace_id` no body
    — o tenant é sempre contextual.
"""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.api.serializers import (
    FormSummarySerializer,
    FormsSearchQuerySerializer,
    FormPreviewSerializer,
    FormPreviewResultSerializer,
    FormImportSerializer,
    FormImportResultSerializer,
)
from apps.integrations.exceptions import (
    AmbiguousConnectionError,
    ConnectionNotEstablishedError,
    ConnectionExpiredError,
    ConnectionRevokedError,
    IntegrationInactiveError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitError,
)
from apps.integrations.services.google_forms import (
    GoogleFormsService,
    FormsScopeMissingError,
)
from apps.workspaces.queries import WorkspaceQueries

logger = logging.getLogger('integrations')


# =========================================================================
# BASE
# =========================================================================

class _GoogleFormsBaseView(APIView):
    """
    Comportamento comum: resolve workspace da sessão, traduz
    exceções para respostas HTTP.
    """

    permission_classes = [IsAuthenticated]

    def _current_workspace(self):
        ws_id = self.request.session.get('current_workspace_id')
        if not ws_id:
            return None
        return WorkspaceQueries.get_for_user(ws_id, self.request.user)

    def _require_workspace(self):
        """
        Retorna (workspace, None) ou (None, Response de erro).
        """
        ws = self._current_workspace()
        if ws is None:
            return None, Response(
                {'error': 'Nenhum workspace ativo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return ws, None

    def _handle_domain_error(self, exc) -> Response:
        """
        Traduz exceções do serviço em respostas HTTP.

        Retorna sempre uma Response — nunca None.
        """
        if isinstance(exc, ConnectionNotEstablishedError):
            return Response(
                {
                    'error': (
                        'Nenhuma conta Google conectada a este '
                        'workspace. Conecte uma para continuar.'
                    ),
                    'code': 'google_not_connected',
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        if isinstance(exc, FormsScopeMissingError):
            return Response(
                {
                    'error': (
                        'A conta Google conectada não autorizou '
                        'acesso ao Google Forms. Reconecte autorizando '
                        'esta permissão.'
                    ),
                    'code': 'google_forms_scope_missing',
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        if isinstance(exc, ConnectionExpiredError):
            return Response(
                {
                    'error': (
                        'A credencial do Google expirou. Reconecte '
                        'a conta para continuar.'
                    ),
                    'code': 'google_expired',
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        if isinstance(exc, ConnectionRevokedError):
            return Response(
                {
                    'error': (
                        'A conta Google foi revogada. Reconecte '
                        'para continuar.'
                    ),
                    'code': 'google_revoked',
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        if isinstance(exc, AmbiguousConnectionError):
            return Response(
                {
                    'error': (
                        'Há múltiplas contas Google conectadas sem '
                        'uma preferida. Escolha uma para continuar.'
                    ),
                    'code': 'google_ambiguous',
                },
                status=status.HTTP_409_CONFLICT,
            )

        if isinstance(exc, IntegrationInactiveError):
            return Response(
                {
                    'error': 'A integração Google não está ativa.',
                    'code': 'google_inactive',
                },
                status=status.HTTP_428_PRECONDITION_REQUIRED,
            )

        if isinstance(exc, RateLimitError):
            return Response(
                {
                    'error': (
                        'A API do Google está limitando requisições. '
                        'Tente novamente em alguns instantes.'
                    ),
                    'code': 'google_rate_limited',
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if isinstance(exc, ProviderTimeoutError):
            return Response(
                {
                    'error': (
                        'A API do Google não respondeu a tempo. '
                        'Tente novamente.'
                    ),
                    'code': 'google_timeout',
                },
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        if isinstance(exc, ProviderServerError):
            return Response(
                {
                    'error': (
                        'Erro temporário na API do Google. '
                        'Tente novamente em alguns instantes.'
                    ),
                    'code': 'google_server_error',
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if isinstance(exc, DjangoValidationError):
            messages = getattr(exc, 'messages', None) or [str(exc)]
            return Response(
                {'error': messages[0], 'code': 'validation_error'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(exc, NotImplementedError):
            return Response(
                {
                    'error': (
                        'A leitura de formulários ainda não está '
                        'disponível. Estamos finalizando esta '
                        'integração.'
                    ),
                    'code': 'not_implemented_yet',
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        logger.exception('Erro inesperado em GoogleFormsView')
        return Response(
            {'error': 'Erro interno. Tente novamente.', 'code': 'internal'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# =========================================================================
# SEARCH
# =========================================================================

class GoogleFormsSearchView(_GoogleFormsBaseView):
    """
    GET /api/integrations/google/forms/search/?q=<query>

    Lista formulários da conta Google conectada, filtrados por
    nome se `q` for fornecido.

    Resposta 200:
        {
            "results": [
                {"id", "name", "description", "url"},
                ...
            ],
            "count": N
        }

    Resposta 428:
        Sem integração conectada / escopo faltando / credencial
        expirada.
    """

    def get(self, request):
        workspace, err = self._require_workspace()
        if err is not None:
            return err

        query_serializer = FormsSearchQuerySerializer(
            data=request.query_params,
        )
        query_serializer.is_valid(raise_exception=True)
        q = query_serializer.validated_data.get('q') or ''

        try:
            results = GoogleFormsService.search_forms(
                workspace=workspace,
                query=q,
            )
        except Exception as exc:
            return self._handle_domain_error(exc)

        return Response({
            'results': FormSummarySerializer(results, many=True).data,
            'count': len(results),
        })


# =========================================================================
# PREVIEW
# =========================================================================

class GoogleFormsPreviewView(_GoogleFormsBaseView):
    """
    POST /api/integrations/google/forms/preview/

    Body:
        { "form": "<URL ou ID do formulário>" }

    Resposta 200:
        {
            "form_id": "...",
            "form_name": "...",          # nome sugerido
            "form_description": "...",
            "sections_count": N,
            "questions_count": M
        }

    Este endpoint NÃO cria nada. Serve para o frontend montar a
    tela de confirmação antes de criar o template novo.
    """

    def post(self, request):
        workspace, err = self._require_workspace()
        if err is not None:
            return err

        serializer = FormPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form_value = serializer.validated_data['form']

        try:
            result = GoogleFormsService.preview_form(
                workspace=workspace,
                form_url_or_id=form_value,
            )
        except Exception as exc:
            return self._handle_domain_error(exc)

        return Response(FormPreviewResultSerializer(result).data)


# =========================================================================
# IMPORT
# =========================================================================

class GoogleFormsImportView(_GoogleFormsBaseView):
    """
    POST /api/integrations/google/forms/import/

    Body:
        {
            "form": "<URL ou ID do formulário>",
            "template_name": "<nome escolhido pelo usuário>"  # opcional
        }

    Resposta 200:
        {
            "imported": true,
            "form_id": "...",
            "template_id": "<uuid do NOVO template criado>",
            "template_name": "...",
            "sections_created": N,
            "questions_created": M
        }

    Resposta 400:
        URL/ID inválido.

    Resposta 428:
        Sem integração conectada / escopo faltando / credencial
        expirada.

    Resposta 501:
        Chamada real ao Google ainda não implementada (V1).
    """

    def post(self, request):
        workspace, err = self._require_workspace()
        if err is not None:
            return err

        serializer = FormImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        form_value = serializer.validated_data['form']
        template_name = serializer.validated_data.get('template_name', '')

        try:
            result = GoogleFormsService.import_form(
                workspace=workspace,
                form_url_or_id=form_value,
                template_name=template_name,
                actor=request.user,
            )
        except Exception as exc:
            return self._handle_domain_error(exc)

        return Response(FormImportResultSerializer(result).data)