from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Custom exception handler para o Clivo.
    """
    response = exception_handler(exc, context)
    
    if response is not None:
        # Adiciona estrutura consistente de erro
        response.data = {
            'error': response.data.get('detail', str(response.data)),
            'status_code': response.status_code
        }
    
    return response