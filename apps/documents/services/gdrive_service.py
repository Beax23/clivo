"""
GDriveService — importação de arquivos do Google Drive.

============================================================================
FILOSOFIA
============================================================================

O Google Drive é uma FONTE, não um sistema de arquivos paralelo.

Fluxo:
    Google Drive → Selecionar → Importar → Document (Clivo)

Uma vez importado, o arquivo é propriedade do Clivo. Não sincroniza.
A `source='gdrive'` e `source_url` guardam apenas o histórico de onde
veio, para o usuário saber a origem.

============================================================================
AUTENTICAÇÃO
============================================================================

Usamos o `SocialToken` do AllAuth (provider='google').
Para isso funcionar, `SOCIALACCOUNT_STORE_TOKENS` precisa ser `True`
no settings. Sem isso, o AllAuth autentica mas não guarda o token
e a Drive API não pode ser chamada.

Escopos necessários:
    - https://www.googleapis.com/auth/drive.readonly
    (ou drive.file, para acesso somente aos arquivos escolhidos pelo usuário)

Se o token não existir ou estiver sem o escopo correto, devolvemos
uma mensagem CLARA para o usuário saber o que fazer.
"""

import io
import logging
from typing import List, Dict

from django.core.files.base import ContentFile

from apps.documents.models import Document
from apps.documents.services.document_service import DocumentService
from apps.documents.exceptions import DocumentInvalidUploadError

logger = logging.getLogger('documents')


# Escopo mínimo necessário para listar e baixar arquivos do Drive.
# Se o token OAuth do usuário não tiver esse escopo, a chamada falha.
DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
]


class GDriveService:

    # ------------------------------------------------------------------
    # AUTENTICAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    def _get_credentials(user):
        """
        Recupera as credenciais OAuth do Google Drive para o usuário.

        Retorna um objeto `google.oauth2.credentials.Credentials` ou None.
        """
        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            logger.warning('allauth não disponível — GDrive desabilitado')
            return None

        social = SocialAccount.objects.filter(
            user=user, provider='google'
        ).first()
        if not social:
            return None

        token = SocialToken.objects.filter(
            account=social
        ).first()
        if not token or not token.token:
            logger.info(
                'GDrive: SocialToken ausente para user=%s. '
                'SOCIALACCOUNT_STORE_TOKENS está True?',
                user.pk,
            )
            return None

        try:
            from google.oauth2.credentials import Credentials
        except ImportError:
            logger.warning('google-auth não instalado')
            return None

        # Recupera o client_id/secret do settings para permitir refresh
        try:
            from django.conf import settings
            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or ''
            client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '') or ''
        except Exception:
            client_id = ''
            client_secret = ''

        creds = Credentials(
            token=token.token,
            refresh_token=token.token_secret or None,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=DRIVE_SCOPES,
        )
        return creds

    @staticmethod
    def _get_service(user):
        """
        Cria o cliente da Google Drive API v3 para o usuário.
        Retorna None se não for possível autenticar.

        Erros são distinguidos para dar mensagem clara ao frontend.
        """
        # 1. Tem SocialAccount Google?
        try:
            from allauth.socialaccount.models import SocialAccount, SocialToken
        except ImportError:
            raise DocumentInvalidUploadError(
                'Integração com Google indisponível no servidor.'
            )

        social = SocialAccount.objects.filter(
            user=user, provider='google'
        ).first()
        if not social:
            raise DocumentInvalidUploadError(
                'Sua conta não está conectada ao Google. '
                'Faça login com Google novamente.'
            )

        token = SocialToken.objects.filter(account=social).first()
        if not token or not token.token:
            raise DocumentInvalidUploadError(
                'O Clivo não tem permissão para acessar seu Google Drive. '
                'Faça login com Google novamente para autorizar.'
            )

        # 2. Bibliotecas instaladas?
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            logger.exception('google-auth/google-api-python-client não instalados')
            raise DocumentInvalidUploadError(
                'Integração com Google Drive indisponível no servidor. '
                'Contate o suporte.'
            )

        creds = GDriveService._get_credentials(user)
        if creds is None:
            raise DocumentInvalidUploadError(
                'Não foi possível usar sua credencial do Google. '
                'Faça login com Google novamente.'
            )

        try:
            return build('drive', 'v3', credentials=creds, cache_discovery=False)
        except Exception as exc:
            logger.exception('Falha ao construir cliente do Drive: %s', exc)
            raise DocumentInvalidUploadError(
                'Falha ao conectar ao Google Drive. Tente novamente.'
            )

    # ------------------------------------------------------------------
    # LISTAGEM
    # ------------------------------------------------------------------

    @staticmethod
    def list_files(user, query: str = '', page_size: int = 50) -> List[Dict]:
        """
        Lista arquivos do Drive do usuário.

        Retorna uma lista de dicts:
            { id, name, mimeType, size, iconLink, webViewLink, modifiedTime }
        """
        service = GDriveService._get_service(user)

        q_parts = ["trashed = false"]
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
            raise DocumentInvalidUploadError(
                'Falha ao listar arquivos do Google Drive. '
                'Verifique se a permissão de leitura foi concedida.'
            )

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
        client=None,
        project_id=None,
    ) -> Document:
        service = GDriveService._get_service(user)

        file_id = file_meta.get('id')
        if not file_id:
            raise DocumentInvalidUploadError('Arquivo do Drive sem id.')

        file_name = file_meta.get('name') or 'arquivo'
        mime_type = file_meta.get('mimeType') or ''
        web_view_link = file_meta.get('webViewLink') or ''

        try:
            from googleapiclient.http import MediaIoBaseDownload
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
        except Exception as exc:
            logger.exception('Falha ao baixar arquivo do Drive: %s', exc)
            raise DocumentInvalidUploadError(
                f'Falha ao baixar "{file_name}" do Google Drive.'
            )

        content = ContentFile(fh.read())
        content.name = file_name
        try:
            content.size = len(content.file.getvalue())
        except Exception:
            pass

        return DocumentService.upload(
            workspace=workspace,
            uploaded_file=content,
            name=Document.extract_name(file_name),
            client=client,
            project_id=project_id,
            created_by=user,
            source=Document.SOURCE_GDRIVE,
            source_url=web_view_link,
        )

    # ------------------------------------------------------------------
    # IMPORTAÇÃO EM LOTE
    # ------------------------------------------------------------------

    @staticmethod
    def import_files(
        *,
        workspace,
        user,
        files_meta: List[Dict],
        client=None,
        project_id=None,
    ) -> Dict:
        imported = []
        errors = []

        for meta in files_meta:
            try:
                doc = GDriveService.import_file(
                    workspace=workspace,
                    user=user,
                    file_meta=meta,
                    client=client,
                    project_id=project_id,
                )
                imported.append(doc)
            except Exception as exc:
                logger.exception('Falha ao importar arquivo do Drive')
                errors.append({
                    'name': meta.get('name') or 'arquivo',
                    'error': str(exc),
                })

        return {'imported': imported, 'errors': errors}