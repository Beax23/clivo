from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.documents'
    verbose_name = _('Arquivos')

    def ready(self):
        """
        Inicializa o módulo documents.

        Signals não são registrados por padrão. O módulo `documents`
        emite eventos de domínio quando os services existirem
        (fase seguinte). No P0, é apenas CRUD + histórico local.
        """
        # import apps.documents.signals  # noqa: F401
        pass