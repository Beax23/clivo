from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceInvitation,
)
from apps.workspaces.queries import WorkspaceQueries
from apps.workspaces.public_id import encode_workspace_id
from apps.workspaces.api.serializers import (
    WorkspaceSerializer,
    WorkspaceCreateSerializer,
    WorkspaceUpdateSerializer,
    WorkspaceMembershipSerializer,
    WorkspaceMembershipCreateSerializer,
    WorkspaceMembershipUpdateSerializer,
    WorkspaceSubscriptionSerializer,
    WorkspaceInvitationSerializer,
    WorkspaceInvitationCreateSerializer,
    WorkspaceInvitationUpdateSerializer,
)
from apps.workspaces.services import (
    WorkspaceService,
    WorkspaceMembershipService,
    WorkspaceSubscriptionService,
    WorkspaceInvitationService,
)
from apps.workspaces.permissions import (
    IsWorkspaceMember,
    IsWorkspaceOwner,
)
from apps.workspaces.exceptions import (
    DefaultPlanNotFoundError,
    DefaultPlanAmbiguousError,
    ProprietarioGovernanceNotFoundError,
    WorkspaceUserNotActiveError,
    DuplicateMembershipError,
    UserNotActiveError,
    GovernanceNotFoundError,
    GovernanceScopeError,
    LastOwnerError,
    WorkspaceInvitationError,
    InvitationResendLimitError,
)


class WorkspaceViewSet(viewsets.ModelViewSet):
    lookup_field = 'id'

    def get_permissions(self):
        if self.action in [
            'list', 'create', 'current', 'my_workspaces', 'governances',
            'my_capabilities',
        ]:
            return [IsAuthenticated()]
        if self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsWorkspaceOwner()]
        return [IsAuthenticated(), IsWorkspaceMember()]

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkspaceCreateSerializer
        if self.action in ['update', 'partial_update']:
            return WorkspaceUpdateSerializer
        return WorkspaceSerializer

    def get_queryset(self):
        return WorkspaceQueries.list_for_user_with_plan(self.request.user)

    # ==================================================================
    # AUTORIZAÇÃO
    # ==================================================================

    @staticmethod
    def _capabilities_for_membership(membership) -> list:
        from apps.console.models import ConsoleGovernanceCapability

        if membership is None:
            return []

        # Proprietário é a invariante estrutural do tenant.
        # Ele sempre tem todas as capabilities, sem precisar
        # que o operador configure isso no Console UI.
        if membership.governance.key == 'proprietario':
            return ['*']

        return list(
            ConsoleGovernanceCapability.objects
            .filter(
                governance=membership.governance,
                capability__is_active=True,
            )
            .values_list('capability__code', flat=True)
            .distinct()
        )

    def _has_capability(self, request, workspace, capability_code) -> bool:
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).select_related('governance').first()

        if membership is None:
            return False

        caps = self._capabilities_for_membership(membership)
        if '*' in caps:
            return True
        return capability_code in caps

    def _require_capability(self, request, workspace, capability_code):
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=request.user,
        ).select_related('governance').first()

        if membership is None:
            return Response(
                {'error': 'Você não é membro deste Workspace'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not self._has_capability(request, workspace, capability_code):
            return Response(
                {
                    'error': (
                        f'Sua governança não permite esta ação '
                        f'({capability_code}).'
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    # ==================================================================
    # CRUD
    # ==================================================================

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            workspace = WorkspaceService.create_workspace(
                name=serializer.validated_data['name'],
                created_by=request.user,
                cnpj=serializer.validated_data.get('cnpj', ''),
                city=serializer.validated_data.get('city', ''),
                state=serializer.validated_data.get('state', ''),
            )
        except (
            DefaultPlanNotFoundError,
            DefaultPlanAmbiguousError,
            ProprietarioGovernanceNotFoundError,
        ) as e:
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except WorkspaceUserNotActiveError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        workspace = WorkspaceQueries.get_with_subscription(workspace.id)
        request.session['current_workspace_id'] = str(workspace.id)

        # Mantém `last_access_at` coerente para `get_last_accessed_for_user`.
        # Sem isso, o Workspace recém-criado entra com last_access_at=NULL
        # e perde a prioridade na ordenação por último acesso.
        WorkspaceMembershipService.touch_last_access(workspace, request.user)

        return Response(
            WorkspaceSerializer(workspace).data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        workspace = self.get_object()
        WorkspaceMembershipService.touch_last_access(workspace, request.user)
        serializer = self.get_serializer(workspace)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        workspace = self.get_object()
        err = self._require_capability(
            request, workspace, 'workspaces.workspace.update'
        )
        if err is not None:
            return err

        serializer = self.get_serializer(workspace, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WorkspaceSerializer(workspace).data)

    def destroy(self, request, *args, **kwargs):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.workspace.delete')
        if err is not None:
            return err
        WorkspaceService.delete_workspace(workspace)
        return Response(
            {'detail': 'Workspace excluído com sucesso'},
            status=status.HTTP_204_NO_CONTENT,
        )

    # ==================================================================
    # WORKSPACE ATUAL / MEU / GOVERNANÇAS / CAPABILITIES
    # ==================================================================

    @action(detail=False, methods=['get'], url_path='current')
    def current(self, request):
        workspace_id = request.session.get('current_workspace_id')
        workspace = None
        if workspace_id:
            workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            workspace = WorkspaceQueries.get_last_accessed_for_user(request.user)
        if workspace is None:
            return Response(
                {'error': 'Nenhum Workspace acessível para este usuário'},
                status=status.HTTP_404_NOT_FOUND,
            )
        request.session['current_workspace_id'] = str(workspace.id)
        WorkspaceMembershipService.touch_last_access(workspace, request.user)
        return Response(WorkspaceSerializer(workspace).data)

    @action(detail=False, methods=['get'], url_path='my')
    def my_workspaces(self, request):
        memberships = (
            WorkspaceMembership.objects
            .filter(user=request.user, workspace__is_active=True)
            .select_related('workspace', 'governance')
            .order_by('-last_access_at', '-joined_at')
        )
        current_id = request.session.get('current_workspace_id')
        results = []
        for m in memberships:
            results.append({
                'id': str(m.workspace.id),
                'public_id': encode_workspace_id(m.workspace.id),
                'name': m.workspace.name,
                'slug': m.workspace.slug,
                'governance_key': m.governance.key,
                'governance_name': m.governance.name,
                'is_current': str(m.workspace.id) == str(current_id) if current_id else False,
            })
        return Response(results)

    @action(
        detail=False,
        methods=['get'],
        url_path='governances',
        url_name='governances',
    )
    def governances(self, request):
        from apps.console.models import ConsoleGovernance, ConsoleGovernanceCapability

        governances = ConsoleGovernance.objects.filter(scope='workspace').order_by('name')
        results = []
        for g in governances:
            caps = (
                ConsoleGovernanceCapability.objects
                .filter(governance=g, capability__is_active=True)
                .select_related('capability')
            )
            capabilities = [
                {
                    'code': c.capability.code,
                    'name': c.capability.name,
                    'description': c.capability.description or '',
                }
                for c in caps
            ]
            results.append({
                'key': g.key,
                'name': g.name,
                'description': g.description or '',
                'is_system': g.is_system,
                'is_protected': g.is_protected,
                'capabilities': capabilities,
                'capabilities_count': len(capabilities),
            })
        return Response(results)

    @action(
        detail=False,
        methods=['get'],
        url_path='my-capabilities',
        url_name='my-capabilities',
    )
    def my_capabilities(self, request):
        workspace_id = request.session.get('current_workspace_id')
        workspace = None
        if workspace_id:
            workspace = WorkspaceQueries.get_for_user(workspace_id, request.user)
        if workspace is None:
            workspace = WorkspaceQueries.get_last_accessed_for_user(request.user)

        if workspace is None:
            return Response({
                'workspace_id': None,
                'governance_key': None,
                'governance_name': None,
                'capabilities': [],
                'is_owner': False,
            })

        membership = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user
        ).select_related('governance').first()

        if membership is None:
            return Response({
                'workspace_id': str(workspace.id),
                'governance_key': None,
                'governance_name': None,
                'capabilities': [],
                'is_owner': False,
            })

        caps = self._capabilities_for_membership(membership)
        return Response({
            'workspace_id': str(workspace.id),
            'governance_key': membership.governance.key,
            'governance_name': membership.governance.name,
            'capabilities': caps,
            'is_owner': membership.governance.key == 'proprietario',
        })

    # ==================================================================
    # MEMBERS
    # ==================================================================

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='members',
        url_name='members',
    )
    def members(self, request, id=None):
        workspace = self.get_object()

        if request.method == 'GET':
            err = self._require_capability(
                request, workspace, 'workspaces.member.view'
            )
            if err is not None:
                return err
            memberships = WorkspaceMembershipService.list_members(workspace)
            return Response(WorkspaceMembershipSerializer(memberships, many=True).data)

        # POST
        err = self._require_capability(
            request, workspace, 'workspaces.member.invite'
        )
        if err is not None:
            return err

        serializer = WorkspaceMembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = WorkspaceMembershipService.add_member(
                workspace=workspace,
                user=serializer.validated_data['user'],
                governance_key=serializer.validated_data['governance_key'],
            )
        except UserNotActiveError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateMembershipError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except GovernanceScopeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except GovernanceNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            WorkspaceMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'members/(?P<membership_id>[^/.]+)',
        url_name='member-detail',
    )
    def update_member(self, request, id=None, membership_id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.member.change_governance')
        if err is not None:
            return err

        try:
            membership = WorkspaceMembership.objects.get(id=membership_id, workspace=workspace)
        except (WorkspaceMembership.DoesNotExist, ValueError):
            return Response({'error': 'Membro não encontrado'}, status=status.HTTP_404_NOT_FOUND)

        serializer = WorkspaceMembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = WorkspaceMembershipService.change_governance(
                membership=membership,
                governance_key=serializer.validated_data['governance_key'],
            )
        except GovernanceNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except GovernanceScopeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except LastOwnerError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)

        return Response(WorkspaceMembershipSerializer(membership).data)

    @action(
        detail=True,
        methods=['delete'],
        url_path=r'members/(?P<membership_id>[^/.]+)',
        url_name='member-remove',
    )
    def remove_member(self, request, id=None, membership_id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.member.remove')
        if err is not None:
            return err

        try:
            membership = WorkspaceMembership.objects.get(id=membership_id, workspace=workspace)
        except (WorkspaceMembership.DoesNotExist, ValueError):
            return Response({'error': 'Membro não encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            WorkspaceMembershipService.remove_member(membership)
        except LastOwnerError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({'detail': 'Membro removido com sucesso'}, status=status.HTTP_204_NO_CONTENT)

    # ==================================================================
    # INVITATIONS
    # ==================================================================

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='invitations',
        url_name='invitations',
    )
    def invitations(self, request, id=None):
        workspace = self.get_object()

        if request.method == 'GET':
            err = self._require_capability(
                request, workspace, 'workspaces.member.view'
            )
            if err is not None:
                return err
            invitations = WorkspaceInvitationService.list_pending_for_workspace(workspace)
            return Response(WorkspaceInvitationSerializer(invitations, many=True).data)

        # POST
        err = self._require_capability(
            request, workspace, 'workspaces.member.invite'
        )
        if err is not None:
            return err

        serializer = WorkspaceInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = WorkspaceInvitationService.create_invitation(
                workspace=workspace,
                email=serializer.validated_data['email'],
                governance_key=serializer.validated_data['governance_key'],
                invited_by=request.user,
            )
        except DuplicateMembershipError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except GovernanceNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except GovernanceScopeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except WorkspaceInvitationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            WorkspaceInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'invitations/(?P<invitation_id>[^/.]+)',
        url_name='invitation-detail',
    )
    def update_invitation(self, request, id=None, invitation_id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.member.change_governance')
        if err is not None:
            return err

        invitation = WorkspaceInvitationService.get_by_id(invitation_id)
        if invitation is None or invitation.workspace_id != workspace.id:
            return Response({'error': 'Convite não encontrado'}, status=status.HTTP_404_NOT_FOUND)

        serializer = WorkspaceInvitationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = WorkspaceInvitationService.change_governance(
                invitation=invitation,
                governance_key=serializer.validated_data['governance_key'],
            )
        except GovernanceNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except GovernanceScopeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except WorkspaceInvitationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WorkspaceInvitationSerializer(invitation).data)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'invitations/(?P<invitation_id>[^/.]+)/resend',
        url_name='invitation-resend',
    )
    def resend_invitation(self, request, id=None, invitation_id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.member.invite')
        if err is not None:
            return err

        invitation = WorkspaceInvitationService.get_by_id(invitation_id)
        if invitation is None or invitation.workspace_id != workspace.id:
            return Response({'error': 'Convite não encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            invitation = WorkspaceInvitationService.resend_invitation(invitation)
        except InvitationResendLimitError as e:
            return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except WorkspaceInvitationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WorkspaceInvitationSerializer(invitation).data)

    @action(
        detail=True,
        methods=['delete'],
        url_path=r'invitations/(?P<invitation_id>[^/.]+)',
        url_name='invitation-cancel',
    )
    def cancel_invitation(self, request, id=None, invitation_id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.member.remove')
        if err is not None:
            return err

        invitation = WorkspaceInvitationService.get_by_id(invitation_id)
        if invitation is None or invitation.workspace_id != workspace.id:
            return Response({'error': 'Convite não encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            WorkspaceInvitationService.cancel_invitation(invitation)
        except WorkspaceInvitationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Convite cancelado'}, status=status.HTTP_204_NO_CONTENT)

    # ==================================================================
    # SUBSCRIPTION
    # ==================================================================

    @action(detail=True, methods=['get'], url_path='subscription')
    def get_subscription(self, request, id=None):
        workspace = self.get_object()
        err = self._require_capability(request, workspace, 'workspaces.subscription.view')
        if err is not None:
            return err
        subscription = WorkspaceSubscriptionService.get_subscription(workspace)
        if not subscription:
            return Response({'error': 'Assinatura não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkspaceSubscriptionSerializer(subscription).data)