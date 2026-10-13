"""
GDriveService — importação de imagens do Google Drive.

============================================================================
FILOSOFIA
============================================================================

O Google Drive é uma FONTE, não uma biblioteca paralela.

Fluxo:
    Google Drive → Selecionar → Importar → Reference (Clivo)

Uma vez importada, a imagem é propriedade do Clivo. Não sincroniza.
A `source='gdrive'` e `source_url` guardam apenas o histórico de onde
veio, para o usuário saber a origem.

============================================================================
AUTENTICAÇÃO
============================================================================

Usamos o `SocialToken` do AllAuth (provider='google').
Para isso funcionar, `SOCIALACCOUNT_STORE_TOKENS` precisa ser `True`
no settings. Sem isso, o AllAuth autentica mas não guarda o token
e a Drive API não pode ser chamada.

Para o refresh funcionar (access token expira em 1h), é OBRIGATÓRIO
que o settings tenha:

    'AUTH_PARAMS': {
        'access_type': 'offline',
        'prompt': 'consent',
    },

Sem isso, o Google só devolve access_token e o `token_secret` (refresh)
fica vazio. Quando o access expira, a renovação falha.

============================================================================
CAPABILITIES
============================================================================

Esta camada NÃO checa capabilities — quem decide se o usuário pode
listar/importar é a view (`DriveFilesView`, `DriveImportView`), via
`_require_capability(workspace, 'references.reference.upload')`.
"""

import io
import logging
from typing import List, Dict, Optional

from django.core.files.base import ContentFile

from apps.references.models import Reference
from apps.references.services.reference_service import ReferenceService
from apps.references.exceptions import ReferenceInvalidImageError

logger = logging.getLogger('references')


DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
]


MSG_NO_SOCIAL = (
    'Sua conta não está conectada ao Google. '
    'Faça login com Google novamente.'
)
MSG_NO_TOKEN = (
    'O Clivo não tem permissão para acessar seu Google Drive. '
    'Faça login com Google novamente para autorizar.'
)
MSG_NO_REFRESH = (
    'Sua conexão com o Google está incompleta. '
    'Por favor, reconecte sua conta Google para permitir '
    'que o Clivo acesse seu Drive.'
)
MSG_NO_LIBS = (
    'Integração com Google Drive indisponível no servidor. '
    'Contate o suporte.'
)
MSG_BUILD_FAIL = (
    'Falha ao conectar ao Google Drive. Tente novamente.'
)
MSG_LIST_FAIL = (
    'Falha ao listar arquivos do Google Drive. '
    'Verifique se a permissão de leitura foi concedida.'
)
MSG_DOWNLOAD_FAIL = (
    'Falha ao baixar o arquivo do Google Drive.'
)


class GDriveService:

    # ------------------------------------------------------------------
    # DIAGNÓSTICO
    # ------------------------------------------------------------------

    @staticmethod
    def is_connected(user) -> bool:
        """
        Retorna True só se o usuário tem SocialAccount Google E refresh
        token válido E credenciais configuradas. Mesma régua usada por
        `_get_service`.
        """
        try:
            return GDriveService._get_credentials(user) is not None
        except Exception:
            return False

    @staticmethod
    def connection_status(user) -> Dict:
        """
        Diagnóstico completo para o frontend decidir o que mostrar.
        Retorna um dict com flags independentes.
        """
        result = {
            'connected': False,
            'has_social': False,
            'has_token': False,
            'has_refresh': False,
            'needs_reconnect': False,
            'user_email': None,
        }

        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            return result

        social = SocialAccount.objects.filter(
            user=user, provider='google'
        ).first()
        if not social:
            return result

        result['has_social'] = True
        result['user_email'] = social.user.email

        token = SocialToken.objects.filter(account=social).first()
        if not token or not token.token:
            return result

        result['has_token'] = True
        result['has_refresh'] = bool(token.token_secret)

        if result['has_refresh']:
            result['connected'] = True
        else:
            result['needs_reconnect'] = True

        return result

    # ------------------------------------------------------------------
    # AUTENTICAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def _get_credentials(user):
        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            logger.warning('allauth não disponível — GDrive desabilitado')
            return None

        social = SocialAccount.objects.filter(
            user=user, provider='google'
        ).first()
        if not social:
            logger.info('GDrive: usuário %s sem SocialAccount Google.', user.pk)
            return None

        token = SocialToken.objects.filter(account=social).first()
        if not token or not token.token:
            logger.info(
                'GDrive: SocialToken ausente para user=%s. '
                'SOCIALACCOUNT_STORE_TOKENS está True?',
                user.pk,
            )
            return None

        refresh_token = token.token_secret or None
        if not refresh_token:
            logger.warning(
                'GDrive: usuário %s tem access token mas SEM refresh_token. '
                'Reconecte a conta Google com access_type=offline + prompt=consent.',
                user.pk,
            )
            return None

        try:
            from google.oauth2.credentials import Credentials
        except ImportError:
            logger.warning('google-auth não instalado')
            return None

        try:
            from django.conf import settings
            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or ''
            client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '') or ''
        except Exception:
            client_id = ''
            client_secret = ''

        if not client_id or not client_secret:
            logger.warning(
                'GDrive: GOOGLE_CLIENT_ID ou GOOGLE_CLIENT_SECRET ausente.'
            )
            return None

        creds = Credentials(
            token=token.token,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=DRIVE_SCOPES,
        )
        return creds

    @staticmethod
    def _get_service(user):
        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            raise ReferenceInvalidImageError(
                'Integração com Google indisponível no servidor.'
            )

        social = SocialAccount.objects.filter(
            user=user, provider='google'
        ).first()
        if not social:
            raise ReferenceInvalidImageError(MSG_NO_SOCIAL)

        token = SocialToken.objects.filter(account=social).first()
        if not token or not token.token:
            raise ReferenceInvalidImageError(MSG_NO_TOKEN)

        if not token.token_secret:
            raise ReferenceInvalidImageError(MSG_NO_REFRESH)

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            logger.exception('google-auth/google-api-python-client não instalados')
            raise ReferenceInvalidImageError(MSG_NO_LIBS)

        creds = GDriveService._get_credentials(user)
        if creds is None:
            raise ReferenceInvalidImageError(MSG_NO_REFRESH)

        try:
            return build('drive', 'v3', credentials=creds, cache_discovery=False)
        except Exception as exc:
            logger.exception('Falha ao construir cliente do Drive: %s', exc)
            raise ReferenceInvalidImageError(MSG_BUILD_FAIL)

    # ------------------------------------------------------------------
    # LISTAGEM
    # ------------------------------------------------------------------

    @staticmethod
    def list_files(user, query: str = '', page_size: int = 50) -> List[Dict]:
        """
        Lista imagens do Drive do usuário.

        Só imagens — o Drive serve como fonte visual para references.
        Arquivos nativos do Google (Docs, Sheets, ...) são ignorados.
        """
        service = GDriveService._get_service(user)

        q_parts = ["trashed = false"]
        q_parts.append("mimeType contains 'image/'")
        if query:
            safe_query = query.replace("'", "\\'")
            q_parts.append(f"name contains '{safe_query}'")
        q = " and ".join(q_parts)

        try:
            response = service.files().list(
                q=q,
                pageSize=page_size,
                fields='files(id,name,mimeType,size,iconLink,webViewLink,modifiedTime)',
                orderBy='modifiedTime desc',
            ).execute()
        except Exception as exc:
            logger.exception('Falha ao listar arquivos do Drive: %s', exc)
            raise ReferenceInvalidImageError(MSG_LIST_FAIL)

        files = response.get('files', []) or []

        native_mimes = {
            'application/vnd.google-apps.document',
            'application/vnd.google-apps.spreadsheet',
            'application/vnd.google-apps.presentation',
            'application/vnd.google-apps.form',
            'application/vnd.google-apps.drawing',
            'application/vnd.google-apps.folder',
        }
        return [f for f in files if f.get('mimeType') not in native_mimes]

    # ------------------------------------------------------------------
    # IMPORTAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def import_file(
        *,
        workspace,
        user,
        file_meta: Dict,
        folder=None,
    ) -> Reference:
        service = GDriveService._get_service(user)

        file_id = file_meta.get('id')
        if not file_id:
            raise ReferenceInvalidImageError('Arquivo do Drive sem id.')

        file_name = file_meta.get('name') or 'imagem'
        web_view_link = file_meta.get('webViewLink') or ''

        try:
            from googleapiclient.http import MediaIoBaseDownload
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
            fh.seek(0)
        except Exception as exc:
            logger.exception('Falha ao baixar arquivo do Drive: %s', exc)
            raise ReferenceInvalidImageError(
                f'Falha ao baixar "{file_name}" do Google Drive.'
            )

        content = ContentFile(fh.read())
        content.name = file_name
        try:
            content.size = len(content.file.getvalue())
        except Exception:
            pass

        title = Reference.extract_name(file_name) or 'Referência'

        return ReferenceService.upload(
            workspace=workspace,
            uploaded_file=content,
            title=title,
            description='',
            category='',
            folder=folder,
            created_by=user,
            source=Reference.SOURCE_GDRIVE,
            source_url=web_view_link,
            visible_to_client=False,
        )

    @staticmethod
    def import_files(
        *,
        workspace,
        user,
        files_meta: List[Dict],
        folder=None,
    ) -> Dict:
        imported = []
        errors = []

        for meta in files_meta:
            try:
                ref = GDriveService.import_file(
                    workspace=workspace,
                    user=user,
                    file_meta=meta,
                    folder=folder,
                )
                imported.append(ref)
            except Exception as exc:
                logger.exception('Falha ao importar arquivo do Drive')
                errors.append({
                    'name': meta.get('name') or 'imagem',
                    'error': str(exc),
                })

        return {'imported': imported, 'errors': errors}