"""
PinterestService — importação de imagens do Pinterest.

============================================================================
STATUS: PLACEHOLDER — NÃO É INTEGRAÇÃO FUNCIONAL
============================================================================

Este módulo NÃO implementa a integração real com o Pinterest.

Por quê:
    A API do Pinterest exige aprovação de app e fluxo OAuth próprio.
    Enquanto isso não existe, qualquer tentativa de importar um pin
    DEVE retornar erro explícito, e a UI NÃO deve apresentar o botão
    como "importação funcional".

O que está implementado:
    - is_connected(user): verifica se há SocialAccount Pinterest
    - list_pins(...): retorna [] (nunca chamado pela view real)
    - import_pins(...): levanta erro claro

O que NÃO está implementado:
    - fluxo OAuth Pinterest
    - chamada real à API
    - download de imagens dos pins
    - criação de Reference a partir de pin

Quando a integração real existir, este arquivo passa a se comportar
como o `gdrive_service.py`: valida token, chama API, faz download
e delega ao ReferenceService.upload.

Fluxo futuro:
    Pinterest → Selecionar → Importar → Reference (Clivo)

Uma vez importada, a imagem é propriedade do Clivo. Não sincroniza.
`source='pinterest'` e `source_url` guardam apenas o histórico.

============================================================================
"""

import logging
from typing import List, Dict

from apps.references.models import Reference
from apps.references.exceptions import ReferenceInvalidImageError

logger = logging.getLogger('references')


MSG_NOT_IMPLEMENTED = (
    'A integração com Pinterest ainda não está disponível. '
    'Enquanto isso, você pode baixar imagens do Pinterest e '
    'enviá-las pelo botão "Nova referência".'
)
MSG_NO_SOCIAL = (
    'Sua conta não está conectada ao Pinterest. '
    'Faça login com Pinterest novamente.'
)


class PinterestService:
    """
    Placeholder. Nenhum método aqui deve ser tratado como
    funcional pela camada de apresentação.
    """

    # ------------------------------------------------------------------
    # DIAGNÓSTICO
    # ------------------------------------------------------------------

    @staticmethod
    def is_connected(user) -> bool:
        """
        Existe SocialAccount Pinterest vinculada ao usuário?

        ATENÇÃO: `is_connected=True` NÃO significa que a importação
        funciona. Significa apenas que existe vínculo OAuth. O fluxo
        real de importação ainda não foi implementado.
        """
        try:
            from allauth.socialaccount.models import SocialAccount
        except ImportError:
            return False

        return SocialAccount.objects.filter(
            user=user, provider='pinterest'
        ).exists()

    @staticmethod
    def is_available() -> bool:
        """
        Use isto na view / no frontend para decidir se mostra o botão.

        Retorna SEMPRE False no P0. Quando a integração real existir,
        isso passa a refletir a disponibilidade do serviço.
        """
        return False

    # ------------------------------------------------------------------
    # PLACEHOLDER — sempre levantam erro claro
    # ------------------------------------------------------------------

    @staticmethod
    def list_pins(user, query: str = '', board_id: str = '') -> List[Dict]:
        """
        Placeholder. Retorna [] para não quebrar clientes antigos,
        mas a view real não deve chamar isto — deve checar
        `is_available()` antes e recusar.
        """
        return []

    @staticmethod
    def import_pin(
        *,
        workspace,
        user,
        pin_meta: Dict,
        folder=None,
    ) -> Reference:
        raise ReferenceInvalidImageError(MSG_NOT_IMPLEMENTED)

    @staticmethod
    def import_pins(
        *,
        workspace,
        user,
        pins_meta: List[Dict],
        folder=None,
    ) -> Dict:
        return {
            'imported': [],
            'errors': [{
                'name': 'pinterest',
                'error': MSG_NOT_IMPLEMENTED,
            }],
        }