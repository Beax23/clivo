"""
Views HTML do módulo clients.
"""

from django.shortcuts import render, redirect
from django.views import View


class ClientesView(View):
    """
    Página HTML de clientes.

    Exige login. O sidebar resolve a sessão no client-side,
    mas a view garante que o HTML só é servido para autenticados.
    """

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('/login/')
        return render(request, 'cliente.html')


class ClientPortalEntryView(View):
    """
    Entry point HTML do Portal do Cliente.

    Recebe o public_code no path e o token via query string.
    V1: placeholder.
    """

    def get(self, request, public_code):
        return render(request, 'portal/entry.html', {
            'public_code': public_code,
        }, status=200)