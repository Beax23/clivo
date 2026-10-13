"""
Views HTML do módulo references.

Página servida pelo shell (sidebar.html):
    /references/  → ReferencesView

A página consome a API do próprio módulo.

============================================================================
ENDPOINTS CONSUMIDOS PELO FRONTEND
============================================================================

REFERÊNCIAS
    GET    /api/references/
    POST   /api/references/
    GET    /api/references/<id>/
    PATCH  /api/references/<id>/
    DELETE /api/references/<id>/
    POST   /api/references/<id>/replace-image/
    POST   /api/references/<id>/move/
    POST   /api/references/<id>/visibility/
    GET    /api/references/<id>/download/
    GET    /api/references/<id>/history/
    POST   /api/references/<id>/associate-client/
    POST   /api/references/<id>/associate-project/
    GET    /api/references/storage-usage/

PASTAS
    GET    /api/reference-folders/
    POST   /api/reference-folders/
    GET    /api/reference-folders/<id>/
    PATCH  /api/reference-folders/<id>/
    DELETE /api/reference-folders/<id>/

CATEGORIAS
    GET    /api/reference-categories/
    POST   /api/reference-categories/
    GET    /api/reference-categories/<id>/
    PATCH  /api/reference-categories/<id>/
    DELETE /api/reference-categories/<id>/

ARMAZENAMENTO
    GET    /api/workspace/storage/

GOOGLE DRIVE
    GET    /api/drive/status/
    GET    /api/drive/files/
    POST   /api/drive/import/

PINTEREST  (placeholder — responde 503 enquanto indisponível)
    GET    /api/pinterest/status/
    GET    /api/pinterest/pins/
    POST   /api/pinterest/import/
============================================================================
"""

from django.shortcuts import render, redirect
from django.views import View


class ReferencesView(View):
    """
    Página de Referências.

    Exige login. O shell (sidebar.html) resolve o resto no client-side.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')

        return render(request, 'references.html')