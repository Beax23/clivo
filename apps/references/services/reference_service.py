"""
ReferenceService — ciclo de vida completo da Reference.
"""

import logging
from typing import Optional, List

from django.db import transaction

from apps.references.models import (
    Reference, ReferenceHistory, ReferenceFolder, ReferenceCategory,
)
from apps.references.exceptions import (
    ReferenceNotFoundError,
    ReferenceInvalidImageError,
    ReferenceClientNotFoundError,
    ReferenceProjectNotFoundError,
    ReferenceFolderNotFoundError,
    ReferenceStorageError,
)
from apps.references.queries import ReferenceQueries
from apps.references.services.history_service import ReferenceHistoryService
from apps.references.services.image_validation import (
    validate_image_content,
    ImageValidationError,
)

logger = logging.getLogger('references')

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'jfif', 'png', 'webp', 'gif'}


class ReferenceService:

    # ------------------------------------------------------------------
    # CATEGORIAS — resolução segura
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_categories(workspace, category_ids):
        """
        Dado uma lista de UUIDs de categoria, devolve uma lista de
        instâncias de ReferenceCategory do mesmo workspace.
        Ignora IDs inexistentes/fora do workspace.
        """
        if not category_ids:
            return []
        ids = [str(c) for c in category_ids if c]
        if not ids:
            return []
        return list(
            ReferenceCategory.objects.filter(
                workspace=workspace, id__in=ids,
            )
        )

    # ------------------------------------------------------------------
    # CRIAÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def upload(
        *,
        workspace,
        uploaded_file,
        title: str,
        description: str = '',
        category_ids: Optional[List] = None,
        client=None,
        project_id=None,
        folder=None,
        created_by=None,
        source: str = Reference.SOURCE_UPLOAD,
        source_url: str = '',
        visible_to_client: bool = False,
    ) -> Reference:
        ReferenceService._validate_and_detect(uploaded_file)

        title = (title or '').strip()
        if not title:
            raise ReferenceInvalidImageError(
                'O título da referência é obrigatório.'
            )

        description = (description or '').strip()

        if client is not None:
            ReferenceService._validate_client(workspace, client)
        if folder is not None:
            ReferenceService._validate_folder(workspace, folder)
        if source not in dict(Reference.SOURCE_CHOICES):
            source = Reference.SOURCE_UPLOAD

        original_name = uploaded_file.name or ''
        extension = Reference.extract_extension(original_name)
        size = getattr(uploaded_file, 'size', 0) or 0

        reference = Reference(
            workspace=workspace,
            title=title,
            description=description,
            client=client,
            project_id=project_id,
            folder=folder,
            source=source,
            source_url=(source_url or '')[:1000],
            visible_to_client=bool(visible_to_client),
            extension=extension,
            size=size,
            created_by=created_by,
            updated_by=created_by,
        )

        try:
            reference.image.save(original_name, uploaded_file, save=False)
        except Exception as exc:
            raise ReferenceStorageError(
                'Falha ao salvar a imagem no storage.'
            ) from exc

        reference.save()

        cats = ReferenceService._resolve_categories(workspace, category_ids)
        if cats:
            reference.categories.set(cats)

        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_CREATED,
            user=created_by,
            previous_value=None,
            new_value={
                'title': reference.title,
                'category_ids': [str(c.id) for c in cats],
                'client_id': str(reference.client_id) if reference.client_id else None,
                'project_id': str(reference.project_id) if reference.project_id else None,
                'folder_id': str(reference.folder_id) if reference.folder_id else None,
                'source': reference.source,
                'source_url': reference.source_url or None,
                'visible_to_client': reference.visible_to_client,
                'extension': reference.extension,
                'size': reference.size,
            },
        )
        return reference

    # ------------------------------------------------------------------
    # LEITURA
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_raise(reference_id, workspace) -> Reference:
        ref = ReferenceQueries.get_by_id_in_workspace(reference_id, workspace)
        if ref is None:
            raise ReferenceNotFoundError('Referência não encontrada.')
        return ref

    # ------------------------------------------------------------------
    # EDIÇÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def edit(
        *,
        reference: Reference,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category_ids: Optional[List] = None,
        actor=None,
    ) -> Reference:
        changed = []
        prev = {}
        new = {}

        if title is not None:
            new_title = title.strip()
            if not new_title:
                raise ReferenceInvalidImageError(
                    'O título da referência é obrigatório.'
                )
            if new_title != reference.title:
                prev['title'] = reference.title
                new['title'] = new_title
                reference.title = new_title
                changed.append('title')

        if description is not None:
            new_desc = description.strip()
            if new_desc != reference.description:
                prev['description'] = reference.description
                new['description'] = new_desc
                reference.description = new_desc
                changed.append('description')

        if changed:
            reference.updated_by = actor
            reference.save(update_fields=changed + ['updated_by', 'updated_at'])

        if 'title' in prev:
            ReferenceHistoryService.log(
                reference=reference,
                action=ReferenceHistory.ACTION_RENAMED,
                user=actor,
                previous_value={'title': prev['title']},
                new_value={'title': new['title']},
            )
        other_prev = {k: v for k, v in prev.items() if k != 'title'}
        other_new = {k: v for k, v in new.items() if k != 'title'}
        if other_prev:
            ReferenceHistoryService.log(
                reference=reference,
                action=ReferenceHistory.ACTION_EDITED,
                user=actor,
                previous_value=other_prev,
                new_value=other_new,
            )

        # Categorias: substitui o conjunto inteiro
        if category_ids is not None:
            new_cats = ReferenceService._resolve_categories(
                reference.workspace, category_ids,
            )
            old_ids = sorted(str(c.id) for c in reference.categories.all())
            new_ids = sorted(str(c.id) for c in new_cats)
            if old_ids != new_ids:
                reference.categories.set(new_cats)
                ReferenceHistoryService.log(
                    reference=reference,
                    action=ReferenceHistory.ACTION_EDITED,
                    user=actor,
                    previous_value={'category_ids': old_ids},
                    new_value={'category_ids': new_ids},
                )

        return reference

    @staticmethod
    @transaction.atomic
    def set_categories(
        *,
        reference: Reference,
        category_ids: List,
        actor=None,
    ) -> Reference:
        new_cats = ReferenceService._resolve_categories(
            reference.workspace, category_ids or [],
        )
        old_ids = sorted(str(c.id) for c in reference.categories.all())
        new_ids = sorted(str(c.id) for c in new_cats)

        if old_ids == new_ids:
            return reference

        reference.categories.set(new_cats)
        reference.updated_by = actor
        reference.save(update_fields=['updated_by', 'updated_at'])

        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_EDITED,
            user=actor,
            previous_value={'category_ids': old_ids},
            new_value={'category_ids': new_ids},
        )
        return reference

    # ------------------------------------------------------------------
    # MOVER PARA PASTA
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def move_to_folder(
        *, reference, folder: Optional[ReferenceFolder], actor=None,
    ) -> Reference:
        if folder is not None:
            ReferenceService._validate_folder(reference.workspace, folder)

        prev_id = str(reference.folder_id) if reference.folder_id else None
        new_id = str(folder.id) if folder else None
        if prev_id == new_id:
            return reference

        reference.folder = folder
        reference.updated_by = actor
        reference.save(update_fields=['folder', 'updated_by', 'updated_at'])

        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_FOLDER_CHANGED,
            user=actor,
            previous_value={'folder_id': prev_id},
            new_value={'folder_id': new_id},
        )
        return reference

    # ------------------------------------------------------------------
    # VISIBILIDADE
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def set_visibility(
        *, reference, visible_to_client: bool, actor=None,
    ) -> Reference:
        new_value = bool(visible_to_client)
        if reference.visible_to_client == new_value:
            return reference

        prev = reference.visible_to_client
        reference.visible_to_client = new_value
        reference.updated_by = actor
        reference.save(update_fields=[
            'visible_to_client', 'updated_by', 'updated_at',
        ])

        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_VISIBILITY_CHANGED,
            user=actor,
            previous_value={'visible_to_client': prev},
            new_value={'visible_to_client': new_value},
        )
        return reference

    # ------------------------------------------------------------------
    # ASSOCIAÇÕES
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def associate_client(*, reference, client, actor=None) -> Reference:
        ReferenceService._validate_client(reference.workspace, client)
        if reference.client_id == client.id:
            return reference
        prev = str(reference.client_id) if reference.client_id else None
        reference.client = client
        reference.updated_by = actor
        reference.save(update_fields=['client', 'updated_by', 'updated_at'])
        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_CLIENT_ASSOCIATED,
            user=actor,
            previous_value={'client_id': prev},
            new_value={'client_id': str(client.id)},
        )
        return reference

    @staticmethod
    @transaction.atomic
    def dissociate_client(*, reference, actor=None) -> Reference:
        if reference.client_id is None:
            return reference
        prev = str(reference.client_id)
        reference.client = None
        reference.updated_by = actor
        reference.save(update_fields=['client', 'updated_by', 'updated_at'])
        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_CLIENT_REMOVED,
            user=actor,
            previous_value={'client_id': prev},
            new_value={'client_id': None},
        )
        return reference

    @staticmethod
    @transaction.atomic
    def associate_project(*, reference, project_id, actor=None) -> Reference:
        if project_id is None:
            raise ReferenceInvalidImageError(
                'project_id é obrigatório para associação.'
            )
        if reference.project_id == project_id:
            return reference
        prev = str(reference.project_id) if reference.project_id else None
        reference.project_id = project_id
        reference.updated_by = actor
        reference.save(update_fields=['project_id', 'updated_by', 'updated_at'])
        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_PROJECT_ASSOCIATED,
            user=actor,
            previous_value={'project_id': prev},
            new_value={'project_id': str(project_id)},
        )
        return reference

    @staticmethod
    @transaction.atomic
    def dissociate_project(*, reference, actor=None) -> Reference:
        if reference.project_id is None:
            return reference
        prev = str(reference.project_id)
        reference.project_id = None
        reference.updated_by = actor
        reference.save(update_fields=['project_id', 'updated_by', 'updated_at'])
        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_PROJECT_REMOVED,
            user=actor,
            previous_value={'project_id': prev},
            new_value={'project_id': None},
        )
        return reference

    # ------------------------------------------------------------------
    # INTEGRIDADE
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_image_present(reference: Reference) -> None:
        try:
            if not reference.image or not reference.image.storage.exists(reference.image.name):
                raise ReferenceStorageError(
                    'A imagem física não foi encontrada no storage.'
                )
        except ReferenceStorageError:
            raise
        except Exception as exc:
            raise ReferenceStorageError(
                'Falha ao verificar a presença da imagem no storage.'
            ) from exc

    # ------------------------------------------------------------------
    # ESTATÍSTICAS
    # ------------------------------------------------------------------

    @staticmethod
    def storage_usage(workspace) -> dict:
        from django.conf import settings
        from django.db.models import Sum

        total_bytes = (
            Reference.objects
            .filter(workspace=workspace)
            .aggregate(total=Sum('size'))
            .get('total') or 0
        )
        total_bytes = int(total_bytes)

        quota_bytes = int(
            getattr(settings, 'REFERENCES_STORAGE_QUOTA_BYTES', 5 * 1024 ** 3)
        )
        if quota_bytes <= 0:
            quota_bytes = 5 * 1024 ** 3

        percent = min(100.0, (total_bytes / quota_bytes) * 100.0) if quota_bytes else 0.0

        return {
            'used_bytes': total_bytes,
            'quota_bytes': quota_bytes,
            'percent': round(percent, 2),
        }

    # ------------------------------------------------------------------
    # EXCLUSÃO
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def delete(reference: Reference, actor=None) -> None:
        ref_id = reference.pk
        ref_title = reference.title
        ws_id = reference.workspace_id

        image_name = reference.image.name if reference.image else None
        image_storage = reference.image.storage if reference.image else None

        ReferenceHistoryService.log(
            reference=reference,
            action=ReferenceHistory.ACTION_DELETED,
            user=actor,
            previous_value={
                'title': reference.title,
                'category_ids': [str(c.id) for c in reference.categories.all()],
                'client_id': str(reference.client_id) if reference.client_id else None,
                'project_id': str(reference.project_id) if reference.project_id else None,
                'folder_id': str(reference.folder_id) if reference.folder_id else None,
                'source': reference.source,
                'visible_to_client': reference.visible_to_client,
                'extension': reference.extension,
                'size': reference.size,
            },
            new_value=None,
        )

        reference.delete()

        if image_name and image_storage is not None:
            try:
                image_storage.delete(image_name)
            except Exception:
                logger.exception(
                    'ORPHAN_DELETE: falha ao remover imagem após excluir '
                    'reference=%s image=%s', ref_id, image_name,
                )

        logger.info(
            'Reference excluída: workspace=%s reference=%s title=%s',
            ws_id, ref_id, ref_title,
        )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_and_detect(uploaded_file) -> str:
        if uploaded_file is None:
            raise ReferenceInvalidImageError('Nenhuma imagem foi enviada.')
        name = getattr(uploaded_file, 'name', None)
        if not name:
            raise ReferenceInvalidImageError(
                'A imagem enviada não possui nome.'
            )
        extension = Reference.extract_extension(name)
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ReferenceInvalidImageError(
                'Formato inválido. Envie uma imagem JPG, JPEG, JFIF, PNG, WEBP ou GIF.'
            )
        try:
            kind = validate_image_content(uploaded_file)
        except ImageValidationError as exc:
            raise ReferenceInvalidImageError(str(exc)) from exc
        return kind

    @staticmethod
    def _validate_client(workspace, client) -> None:
        if client is None:
            return
        if getattr(client, 'workspace_id', None) != workspace.id:
            raise ReferenceClientNotFoundError(
                'Cliente não encontrado neste workspace.'
            )

    @staticmethod
    def _validate_folder(workspace, folder) -> None:
        if folder is None:
            return
        if getattr(folder, 'workspace_id', None) != workspace.id:
            raise ReferenceFolderNotFoundError(
                'Pasta não encontrada neste workspace.'
            )