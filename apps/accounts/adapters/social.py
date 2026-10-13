"""
Adapter customizado para Social Accounts (Google, etc).

Responsável por:
1. Vincular automaticamente um SocialAccount (Google) a um User existente
   quando o email do Google corresponde a um email já cadastrado
   (ex: usuário foi criado via email/senha e agora entra com Google).
2. Sincronizar dados do perfil (nome, avatar) do Google para o User local.
3. Garantir que emails não verificados pelo Google sejam rejeitados.
4. Marcar o EmailAddress do allauth como verificado quando o Google
   confirma a posse do email — isso evita que o usuário fique preso em
   fluxos de confirmação por email.
5. Não interferir no redirecionamento pós-login — isso é responsabilidade
   de `LOGIN_REDIRECT_URL` / `PostLoginRedirectView`.

FLUXO:
    Google OAuth callback
        ↓
    pre_social_login()
        ├── já existe SocialAccount com este uid → sync + login
        ├── existe User com este email           → connect + sync + verify
        └── não existe User                      → save_user() cria
        ↓
    allauth redireciona para PostLoginRedirectView
        ↓
    /workspaces/entrar/ resolve o contexto
"""

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
import logging

logger = logging.getLogger('accounts')

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Adapter para conectar contas sociais (Google) a usuários existentes
    com o mesmo email, evitando duplicação de contas.
    """

    # ------------------------------------------------------------------
    # HOOK PRINCIPAL
    # ------------------------------------------------------------------

    def pre_social_login(self, request, sociallogin):
        """
        Chamado ANTES do allauth criar/logar o usuário.

        Casos:
            1. SocialAccount já existe com este uid → sync + login
            2. Existe User com este email            → connect + sync
            3. Não existe User                       → deixa o allauth criar
        """
        logger.debug(
            "pre_social_login | provider=%s uid=%s",
            sociallogin.account.provider,
            sociallogin.account.uid,
        )

        email = sociallogin.account.extra_data.get('email')
        email_verified = sociallogin.account.extra_data.get('email_verified', False)

        if not email:
            logger.warning("Google não retornou email no extra_data")
            raise ValidationError('Email não fornecido pelo Google')

        email = User.normalize_email(email)

        # ---------------------------------------------------------------
        # CASO 1: Já existe SocialAccount com este uid
        # ---------------------------------------------------------------
        existing_social = SocialAccount.objects.filter(
            provider=sociallogin.account.provider,
            uid=sociallogin.account.uid,
        ).first()

        if existing_social:
            logger.debug(
                "SocialAccount já existe para %s (user=%s)",
                email,
                existing_social.user.email,
            )
            self._sync_profile_from_google(
                existing_social.user,
                sociallogin.account.extra_data,
            )
            self._mark_email_verified(existing_social.user, email)
            return

        # ---------------------------------------------------------------
        # CASO 2: Existe User com este email, mas sem SocialAccount
        # (ex: criado via email/senha, agora entrando com Google)
        # ---------------------------------------------------------------
        user = User.objects.filter(email__iexact=email).first()

        if user:
            logger.debug(
                "User existente encontrado: %s (id=%s) — emparelhando com Google",
                user.email,
                user.id,
            )

            if not email_verified:
                logger.warning(
                    "Email %s não verificado pelo Google — emparelhamento recusado",
                    email,
                )
                raise ValidationError('Email não verificado pelo Google')

            # Se este User já tem OUTRO SocialAccount do mesmo provider,
            # não emparelha — evita que duas contas Google diferentes
            # disputem o mesmo User.
            other_social = SocialAccount.objects.filter(
                user=user,
                provider=sociallogin.account.provider,
            ).first()

            if other_social:
                logger.warning(
                    "User %s já tem SocialAccount do provider %s "
                    "(uid=%s) — emparelhamento recusado",
                    email,
                    sociallogin.account.provider,
                    other_social.uid,
                )
                raise ValidationError('Conta Google já vinculada a este usuário')

            with transaction.atomic():
                # Cria o SocialAccount e vincula ao User existente
                sociallogin.connect(request, user)
                self._sync_profile_from_google(user, sociallogin.account.extra_data)
                self._mark_email_verified(user, email)

            logger.info(
                "Emparelhamento Google → User existente: %s (id=%s)",
                user.email,
                user.id,
            )
            return

        # ---------------------------------------------------------------
        # CASO 3: Não existe User → allauth cria via save_user()
        # ---------------------------------------------------------------
        logger.debug("Novo usuário será criado para %s", email)

    # ------------------------------------------------------------------
    # CRIAÇÃO DE USUÁRIO NOVO
    # ------------------------------------------------------------------

    def save_user(self, request, sociallogin, form=None):
        """
        Chamado quando o allauth cria um novo User (CASO 3).
        Após criar, sincroniza o perfil com os dados do Google.
        """
        user = super().save_user(request, sociallogin, form)
        logger.info("User criado via social signup: %s (id=%s)", user.email, user.id)
        self._sync_profile_from_google(user, sociallogin.account.extra_data)
        self._mark_email_verified(user, user.email)
        return user

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _sync_profile_from_google(user, user_data):
        """
        Preenche campos vazios do User com dados do Google.
        NÃO sobrescreve dados já preenchidos localmente.
        """
        if not user or not user_data:
            return

        changed = False
        update_fields = []

        if not user.first_name:
            user.first_name = user_data.get('given_name', '') or ''
            changed = True
            update_fields.append('first_name')

        if not user.last_name:
            user.last_name = user_data.get('family_name', '') or ''
            changed = True
            update_fields.append('last_name')

        picture = user_data.get('picture')
        if picture and not user.avatar:
            user.avatar = picture
            changed = True
            update_fields.append('avatar')
            logger.debug("Avatar do Google sincronizado: %s", picture)

        if not user.is_active:
            user.is_active = True
            changed = True
            update_fields.append('is_active')

        if changed:
            user.save(update_fields=update_fields)
            logger.debug(
                "Perfil atualizado para %s: %s",
                user.email,
                update_fields,
            )

    @staticmethod
    def _mark_email_verified(user, email):
        """
        Marca o EmailAddress do allauth como verificado.

        O Google já confirmou que o usuário controla este email, então
        não faz sentido pedir confirmação por link depois.

        Se o EmailAddress não existir (fluxo antigo sem allauth.account),
        apenas ignora silenciosamente.
        """
        if not user or not email:
            return
        try:
            from allauth.account.models import EmailAddress
        except ImportError:
            # allauth.account não instalado — nada a fazer
            return

        try:
            ea, created = EmailAddress.objects.get_or_create(
                user=user,
                email__iexact=email,
                defaults={
                    'email': email,
                    'verified': True,
                    'primary': True,
                },
            )
            update_fields = []
            if not ea.verified:
                ea.verified = True
                update_fields.append('verified')
            if not ea.primary:
                ea.primary = True
                update_fields.append('primary')
            if update_fields:
                ea.save(update_fields=update_fields)
                logger.debug(
                    "EmailAddress marcado como verificado: %s (user=%s)",
                    email,
                    user.email,
                )
        except Exception as exc:
            # Nunca deixa isso quebrar o login
            logger.warning(
                "Falha ao marcar EmailAddress como verificado para %s: %s",
                email,
                exc,
            )