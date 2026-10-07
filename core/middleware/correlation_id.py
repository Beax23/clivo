import uuid
from django.utils.deprecation import MiddlewareMixin


class CorrelationIdMiddleware(MiddlewareMixin):
    """
    Middleware para adicionar correlation_id às requisições.
    """

    def process_request(self, request):
        correlation_id = request.headers.get('X-Correlation-ID')
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        request.correlation_id = correlation_id
        request.META['CORRELATION_ID'] = correlation_id

    def process_response(self, request, response):
        if hasattr(request, 'correlation_id'):
            response['X-Correlation-ID'] = request.correlation_id
        return response