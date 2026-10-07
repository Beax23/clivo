"""
Adapter customizado para Social Accounts (Google, etc).

Responsável por:
1. Vincular automaticamente um SocialAccount (Google) a um User existente
   quando o email do Google corresponde a um email já cadastrado
   (ex: usuário foi adicionado como membro de um Workspace por email).
2. Sincronizar dados do perfil (nome, avatar) do Google para o User local.
3. Garantir que emails não verificados pelo Google sejam rejeitados.
4. Não interferir no redirecionamento pós-login — isso é responsabilidade
   de `LOGIN_REDIRECT_URL`, que aponta para /workspaces/entrar/.

FLUXO:
    Google OAuth callback
        ↓
    pre_social_login()
        ├── já existe SocialAccount com este uid → sync + login
        ├── existe User com este email           → connect + sync
        └── não existe User                      → save_user() cria
        ↓
    allauth redireciona para LOGIN_REDIRECT_URL
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

    def pre_social_login(self, request, sociallogin):
        """
        Chamado ANTES do allauth criar/logar o usuário.

        Fluxo:
        1. Se já existe SocialAccount com este uid → apenas sincroniza perfil.
        2. Se existe User com este email (ex: criado por "adicionar membro")
           → faz o connect (vincula SocialAccount ao User existente).
        3. Se não existe → deixa o allauth criar (save_user).
        """
        logger.debug(
            f"pre_social_login | provider={sociallogin.account.provider} "
            f"uid={sociallogin.account.uid}"
        )

        email = sociallogin.account.extra_data.get('email')
        email_verified = sociallogin.account.extra_data.get('email_verified', False)

        if not email:
            logger.warning("Google não retornou email no extra_data")
            raise ValidationError('Email não fornecido pelo Google')

        email = User.objects.normalize_email(email)

        # ---------------------------------------------------------------
        # CASO 1: Já existe SocialAccount com este uid
        # ---------------------------------------------------------------
        existing_social = SocialAccount.objects.filter(
            provider=sociallogin.account.provider,
            uid=sociallogin.account.uid,
        ).first()

        if existing_social:
            logger.debug(
                f"SocialAccount já existe para {email} "
                f"(user={existing_social.user.email})"
            )
            self._sync_profile_from_google(
                existing_social.user,
                sociallogin.account.extra_data,
            )
            return

        # ---------------------------------------------------------------
        # CASO 2: Existe User com este email, mas sem SocialAccount
        # (ex: adicionado como membro do Console/Workspace por email)
        # ---------------------------------------------------------------
        user = User.objects.filter(email__iexact=email).first()

        if user:
            logger.debug(f"User existente encontrado: {user.email} (id={user.id})")

            if not email_verified:
                logger.warning(f"Email {email} não verificado pelo Google")
                raise ValidationError('Email não verificado pelo Google')

            # Verifica se este User já tem OUTRO SocialAccount do mesmo provider
            other_social = SocialAccount.objects.filter(
                user=user,
                provider=sociallogin.account.provider,
            ).first()

            if other_social:
                logger.warning(
                    f"User {email} já tem SocialAccount do provider "
                    f"{sociallogin.account.provider}"
                )
                raise ValidationError('Conta Google já vinculada a este usuário')

            with transaction.atomic():
                # sociallogin.connect() cria o SocialAccount e vincula ao User
                sociallogin.connect(request, user)
                self._sync_profile_from_google(user, sociallogin.account.extra_data)
                logger.info(
                    f"Account linking realizado: Google → {user.email} (id={user.id})"
                )
            return

        # ---------------------------------------------------------------
        # CASO 3: Não existe User → allauth criará via save_user()
        # ---------------------------------------------------------------
        logger.debug(f"Novo usuário será criado para {email}")

    def save_user(self, request, sociallogin, form=None):
        """
        Chamado quando o allauth cria um novo User (CASO 3).
        Após criar, sincroniza o perfil com os dados do Google.
        """
        user = super().save_user(request, sociallogin, form)
        logger.info(f"User criado via social signup: {user.email} (id={user.id})")
        self._sync_profile_from_google(user, sociallogin.account.extra_data)
        return user

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
            logger.debug(f"Avatar do Google sincronizado: {picture}")

        if not user.is_active:
            user.is_active = True
            changed = True
            update_fields.append('is_active')

        if changed:
            user.save(update_fields=update_fields)
            logger.debug(f"Perfil atualizado para {user.email}: {update_fields}")