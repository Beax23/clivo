"""
Views HTML do módulo documents.

Página servida pelo shell (sidebar.html):
    /documents/  → DocumentsView

A página consome a API do próprio módulo:
    GET    /api/documents/
    POST   /api/documents/
    GET    /api/documents/<id>/
    PATCH  /api/documents/<id>/
    DELETE /api/documents/<id>/
    POST   /api/documents/<id>/replace/
    GET    /api/documents/<id>/download/
    GET    /api/documents/<id>/history/
    POST   /api/documents/<id>/associate-client/
    POST   /api/documents/<id>/associate-project/
"""

from django.shortcuts import render, redirect
from django.views import View


class DocumentsView(View):
    """
    Página de Arquivos.

    Exige login. O shell (sidebar.html) resolve o resto no client-side.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        return render(request, 'documents.html')