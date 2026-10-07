from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from apps.accounts.services.account import AccountService


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Adapter para SocialAccount (Google OAuth).
    """
    
    def pre_social_login(self, request, sociallogin):
        from allauth.socialaccount.models import SocialAccount
        
        email = sociallogin.account.extra_data.get('email')
        email_verified = sociallogin.account.extra_data.get('email_verified', False)
        
        if not email:
            raise ValidationError(_('Email não fornecido pelo Google'))
        
        email = AccountService.normalize_email(email)
        
        existing_social = SocialAccount.objects.filter(
            provider=sociallogin.account.provider,
            uid=sociallogin.account.uid
        ).first()
        
        if existing_social:
            return
        
        user = AccountService.get_user_by_email(email)
        
        if user:
            if not email_verified:
                raise ValidationError(_('Email não verificado pelo Google'))
            
            other_social = SocialAccount.objects.filter(
                user=user,
                provider=sociallogin.account.provider
            ).first()
            
            if other_social:
                raise ValidationError(_('Conta Google já vinculada a este usuário'))
            
            with transaction.atomic():
                sociallogin.connect(request, user)
            return
    
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        
        user_data = sociallogin.account.extra_data
        
        if 'given_name' in user_data:
            user.first_name = user_data['given_name']
        if 'family_name' in user_data:
            user.last_name = user_data['family_name']
        if 'picture' in user_data:
            user.avatar = user_data['picture']
        
        user.save()
        return user


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Adapter para Account (Email/Password).
    """
    pass