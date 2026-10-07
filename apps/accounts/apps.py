from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = _('Contas e Autenticação')

    def ready(self):
        # Importa signals para registrar o user_logged_in handler
        import apps.accounts.signals  # noqa: F401