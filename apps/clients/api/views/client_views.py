"""
ClientViewSet — CRUD completo + actions de negócio.

Regras:
    - Views finas.
    - Regra de negócio nos Services.
    - Tenant isolation em todos os endpoints.
    - Capabilities aplicadas via `_require_capability`.
    - Sem archive/unarchive: cliente é criado, editado ou excluído.
    - `status` é editável via `clients.client.update`.
    - Sem timeline local. Eventos vão para `ClientEventEmitter`.

O envio do código de acesso na criação fica em
`ClientService.create_client` (com auditoria em
`ClientPortalInvitation`). A view NÃO envia e-mail diretamente.

O endpoint `portal/send-access` continua usando
`PortalInvitationService.send_access` (fluxo com token/sessão).
A ação `send-code` usa `ClientService._send_access_code` (só código,
sem sessão, com auditoria) — é o mesmo fluxo que roda no `create`.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.clients.models import (
    Client,
    ClientNote,
    ClientContact,
)
from apps.clients.api.serializers import (
    ClientListSerializer,
    ClientDetailSerializer,
    ClientCreateSerializer,
    ClientUpdateSerializer,
    ClientContextUpdateSerializer,
    ClientContactSerializer,
    ClientContactCreateSerializer,
    ClientContactUpdateSerializer,
    ClientNoteSerializer,
    ClientNoteCreateSerializer,
    ClientNoteUpdateSerializer,
    PortalSessionSerializer,
    PortalInvitationSerializer,
    PortalFeedbackSerializer,
)
from apps.clients.services import (
    ClientService,
    ContactService,
    NoteService,
    PortalService,
    PortalInvitationService,
)
from apps.clients.exceptions import (
    ClientDuplicateEmailError,
    ClientNotFoundError,
    ContactNotFoundError,
    NoteNotFoundError,
    PortalEmailMissingError,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.models import WorkspaceMembership
from apps.console.models import ConsoleGovernanceCapability

logger = logging.getLogger('clients')


class ClientViewSet(viewsets.ModelViewSet):
    """
    ViewSet de Client.

    Resolve automaticamente o Workspace ativo da sessão e aplica
    tenant isolation + capability.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    # ------------------------------------------------------------------
    # CONTEXTO
    # ------------------------------------------------------------------

    def _current_workspace(self):
        workspace_id = self.request.session.get('current_workspace_id')
        if not workspace_id:
            return None
        return WorkspaceQueries.get_for_user(workspace_id, self.request.user)

    def _require_capability(self, workspace, capability_code):
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=self.request.user,
        ).select_related('governance').first()

        if membership is None:
            return Response(
                {'error': 'Você não é membro deste Workspace'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if membership.governance.key == 'proprietario':
            return None

        has = ConsoleGovernanceCapability.objects.filter(
            governance=membership.governance,
            capability__code=capability_code,
            capability__is_active=True,
        ).exists()

        if not has:
            return Response(
                {'error': f'Sua governança não permite esta ação ({capability_code}).'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    # ------------------------------------------------------------------
    # QUERYSET
    # ------------------------------------------------------------------

    def get_queryset(self):
        workspace = self._current_workspace()
        if workspace is None:
            return Client.objects.none()
        return Client.objects.filter(workspace=workspace).order_by('-created_at')

    def _get_client_or_404(self, client_id):
        workspace = self._current_workspace()
        if workspace is None:
            return None
        return Client.objects.filter(id=client_id, workspace=workspace).first()

    # ------------------------------------------------------------------
    # SERIALIZER
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == 'create':
            return ClientCreateSerializer
        if self.action in ('update', 'partial_update'):
            return ClientUpdateSerializer
        if self.action == 'list':
            return ClientListSerializer
        return ClientDetailSerializer

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'clients.client.view')
        if err is not None:
            return err

        qs = self.get_queryset()
        serializer = ClientListSerializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'clients.client.create')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            client = ClientService.create_client(
                workspace=workspace,
                name=serializer.validated_data['name'],
                created_by=request.user,
                email=serializer.validated_data.get('email', ''),
                phone=serializer.validated_data.get('phone', ''),
                request=request,
            )
        except ClientDuplicateEmailError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)

        # O envio do código de acesso (com auditoria em
        # ClientPortalInvitation) já foi feito pelo service.
        # A view NÃO envia e-mail diretamente.

        return Response(
            ClientDetailSerializer(client).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        client = self._get_client_or_404(kwargs.get('id'))
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.client.view')
        if err is not None:
            return err

        return Response(ClientDetailSerializer(client).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        client = self._get_client_or_404(kwargs.get('id'))
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.client.update')
        if err is not None:
            return err

        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            client = ClientService.update_client(
                client=client,
                actor=request.user,
                name=serializer.validated_data.get('name'),
                email=serializer.validated_data.get('email'),
                phone=serializer.validated_data.get('phone'),
                status=serializer.validated_data.get('status'),
                request=request,
            )
        except ClientDuplicateEmailError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        return Response(ClientDetailSerializer(client).data)

    def destroy(self, request, *args, **kwargs):
        client = self._get_client_or_404(kwargs.get('id'))
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.client.delete')
        if err is not None:
            return err

        ClientService.delete_client(client, actor=request.user, request=request)
        return Response(
            {'detail': 'Cliente excluído com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    # ------------------------------------------------------------------
    # ACTION: check-email
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='check-email')
    def check_email(self, request):
        """
        Verifica se um email já existe no workspace.

        GET /api/clients/check-email/?email=joao@exemplo.com

        Resposta:
            {"exists": true, "client": {"id", "name", "email", "public_code"}}
            ou
            {"exists": false}
        """
        workspace = self._current_workspace()
        if workspace is None:
            return Response({'error': 'Nenhum workspace ativo'}, status=400)

        err = self._require_capability(workspace, 'clients.client.view')
        if err is not None:
            return err

        email = (request.query_params.get('email') or '').strip().lower()
        if not email:
            return Response({'exists': False})

        client = Client.objects.filter(
            workspace=workspace,
            email__iexact=email,
        ).first()

        if client is None:
            return Response({'exists': False})

        return Response({
            'exists': True,
            'client': {
                'id': str(client.id),
                'name': client.name,
                'email': client.email,
                'public_code': client.public_code,
            },
        })

    # ------------------------------------------------------------------
    # ACTION: context
    # ------------------------------------------------------------------

    @action(detail=True, methods=['patch'], url_path='context')
    def update_context(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.client.update')
        if err is not None:
            return err

        serializer = ClientContextUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = ClientService.update_context(
            client=client,
            context=serializer.validated_data['context'],
            actor=request.user,
            request=request,
        )
        return Response(ClientDetailSerializer(client).data)

            # ==================================================================
    # CONTACTS
    # ==================================================================

    @action(detail=True, methods=['get', 'post'], url_path='contacts')
    def contacts(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        if request.method == 'GET':
            err = self._require_capability(client.workspace, 'clients.client.view')
            if err is not None:
                return err
            contacts = ContactService.list_for_client(client)
            return Response(ClientContactSerializer(contacts, many=True).data)

        err = self._require_capability(client.workspace, 'clients.contact.manage')
        if err is not None:
            return err

        serializer = ClientContactCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = ContactService.create_contact(
            client=client,
            name=serializer.validated_data['name'],
            role=serializer.validated_data.get('role', 'other'),
            email=serializer.validated_data.get('email', ''),
            phone=serializer.validated_data.get('phone', ''),
            notes=serializer.validated_data.get('notes', ''),
        )
        return Response(
            ClientContactSerializer(contact).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['get', 'patch', 'delete'],
        url_path=r'contacts/(?P<contact_id>[^/.]+)',
    )
    def contact_detail(self, request, id=None, contact_id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        try:
            contact = ContactService.get_for_client(client, contact_id)
        except ContactNotFoundError as e:
            return Response({'error': str(e)}, status=404)

        if request.method == 'GET':
            err = self._require_capability(client.workspace, 'clients.client.view')
            if err is not None:
                return err
            return Response(ClientContactSerializer(contact).data)

        err = self._require_capability(client.workspace, 'clients.contact.manage')
        if err is not None:
            return err

        if request.method == 'PATCH':
            serializer = ClientContactUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            contact = ContactService.update_contact(
                contact=contact,
                name=serializer.validated_data.get('name'),
                role=serializer.validated_data.get('role'),
                email=serializer.validated_data.get('email'),
                phone=serializer.validated_data.get('phone'),
                notes=serializer.validated_data.get('notes'),
            )
            return Response(ClientContactSerializer(contact).data)

        ContactService.delete_contact(contact)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ==================================================================
    # NOTES
    # ==================================================================

    @action(detail=True, methods=['get', 'post'], url_path='notes')
    def notes(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        if request.method == 'GET':
            err = self._require_capability(client.workspace, 'clients.client.view')
            if err is not None:
                return err
            notes = NoteService.list_for_client(client)
            return Response(ClientNoteSerializer(notes, many=True).data)

        err = self._require_capability(client.workspace, 'clients.note.create')
        if err is not None:
            return err

        serializer = ClientNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = NoteService.create_note(
            client=client,
            author=request.user,
            content=serializer.validated_data['content'],
            is_pinned=serializer.validated_data.get('is_pinned', False),
            request=request,
        )
        return Response(
            ClientNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['get', 'patch', 'delete'],
        url_path=r'notes/(?P<note_id>[^/.]+)',
    )
    def note_detail(self, request, id=None, note_id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        try:
            note = NoteService.get_for_client(client, note_id)
        except NoteNotFoundError as e:
            return Response({'error': str(e)}, status=404)

        if request.method == 'GET':
            err = self._require_capability(client.workspace, 'clients.client.view')
            if err is not None:
                return err
            return Response(ClientNoteSerializer(note).data)

        if request.method == 'PATCH':
            err = self._require_capability(client.workspace, 'clients.note.update')
            if err is not None:
                return err
            serializer = ClientNoteUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            note = NoteService.update_note(
                note=note,
                actor=request.user,
                content=serializer.validated_data.get('content'),
                is_pinned=serializer.validated_data.get('is_pinned'),
                request=request,
            )
            return Response(ClientNoteSerializer(note).data)

        err = self._require_capability(client.workspace, 'clients.note.delete')
        if err is not None:
            return err
        NoteService.delete_note(note, actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ==================================================================
    # PORTAL
    # ==================================================================

    @action(detail=True, methods=['get'], url_path='portal/sessions')
    def portal_sessions(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.view')
        if err is not None:
            return err

        sessions = PortalService.list_active_sessions(client)
        return Response(PortalSessionSerializer(sessions, many=True).data)

    @action(detail=True, methods=['get'], url_path='portal/invitations')
    def portal_invitations(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.view')
        if err is not None:
            return err

        from apps.clients.models import ClientPortalInvitation
        invitations = (
            ClientPortalInvitation.objects
            .filter(client=client)
            .select_related('sent_by')
            .order_by('-sent_at')
        )
        return Response(PortalInvitationSerializer(invitations, many=True).data)

    @action(
        detail=True,
        methods=['post'],
        url_path='portal/send-access',
    )
    def portal_send_access(self, request, id=None):
        """
        Envia acesso com TOKEN/SESSÃO temporária.

        Fluxo diferente do `send-code`:
            - cria `ClientPortalSession`;
            - revoga sessões anteriores do cliente;
            - e-mail aponta para link com `?t=<token>`.

        Uso: quando o arquiteto quer mandar o cliente DIRETO para o
        briefing (por exemplo, para responder complementares), sem
        exigir que ele digite o código de novo.
        """
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.share')
        if err is not None:
            return err

        try:
            invitation = PortalInvitationService.send_access(
                client=client,
                actor=request.user,
                request=request,
            )
        except PortalEmailMissingError as e:
            return Response({'error': str(e)}, status=400)
        except Exception:
            logger.exception(
                'Falha ao enviar acesso do portal (client=%s)', client.id,
            )
            return Response(
                {'error': 'Falha ao enviar acesso'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            PortalInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['post'],
        url_path=r'portal/sessions/(?P<session_id>[^/.]+)/revoke',
    )
    def portal_revoke_session(self, request, id=None, session_id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.share')
        if err is not None:
            return err

        session = PortalService.get_session_or_none(session_id)
        if session is None or session.client_id != client.id:
            return Response({'error': 'Sessão não encontrada'}, status=404)

        PortalService.revoke_session(session)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ==================================================================
    # FEEDBACK
    # ==================================================================

    @action(detail=True, methods=['get'], url_path='feedback')
    def list_feedback(self, request, id=None):
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.view')
        if err is not None:
            return err

        feedbacks = PortalService.list_feedbacks(client)
        return Response(PortalFeedbackSerializer(feedbacks, many=True).data)

    # ==================================================================
    # SEND CODE (reenvio com auditoria, SEM sessão)
    # ==================================================================

    @action(
        detail=True,
        methods=['post'],
        url_path='send-code',
    )
    def send_code(self, request, id=None):
        """
        Envia (ou reenvia) o CÓDIGO de acesso por e-mail.

        Mesmo fluxo do `create`: `ClientService._send_access_code`.
        NÃO cria sessão. NÃO revoga sessões. Grava
        `ClientPortalInvitation` com o resultado (auditoria).

        Uso: quando o cliente perdeu o e-mail original e o arquiteto
        quer reenviar o código sem gerar link com token.
        """
        client = self._get_client_or_404(id)
        if client is None:
            return Response({'error': 'Cliente não encontrado'}, status=404)

        err = self._require_capability(client.workspace, 'clients.portal.share')
        if err is not None:
            return err

        if not client.email:
            return Response(
                {'error': 'O cliente não possui email cadastrado.'},
                status=400,
            )

        # O service grava ClientPortalInvitation('sent'|'failed') e
        # não levanta para falha de SMTP. A view não precisa (e não
        # deve) inspecionar exceção de e-mail.
        ClientService._send_access_code(
            client=client,
            actor=request.user,
        )

        return Response(
            {'detail': 'Código enviado com sucesso'},
            status=status.HTTP_200_OK,
        )
        