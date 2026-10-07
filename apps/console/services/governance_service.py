from typing import Optional, List
from django.db import transaction

from apps.console.models import (
    ConsoleGovernance,
    ConsoleGovernanceCapability,
    ConsoleCapability,
)
from apps.console.exceptions.console_exceptions import (
    GovernanceError,
    GovernanceNotFoundError,
    GovernanceProtectedError,
    CapabilityNotFoundError,
)


class ConsoleGovernanceService:
    """Serviço para gerenciamento de governanças do Console."""

    @staticmethod
    @transaction.atomic
    def create_governance(
        key: str,
        name: str,
        description: str,
        created_by,
        scope: str = 'console',
        is_system: bool = False,
        is_protected: bool = False,
    ):
        if ConsoleGovernance.objects.filter(key=key).exists():
            raise GovernanceError(f'Chave "{key}" já está em uso')

        if is_system and not is_protected:
            is_protected = True

        governance = ConsoleGovernance.objects.create(
            key=key,
            name=name,
            description=description,
            scope=scope,
            is_system=is_system,
            is_protected=is_protected,
            created_by=created_by,
        )
        return governance

    @staticmethod
    def update_governance(
        governance: ConsoleGovernance,
        name: Optional[str] = None,
        description: Optional[str] = None,
        updated_by=None,
    ) -> ConsoleGovernance:
        """
        Atualiza `name` e `description` de uma governança.

        Governanças de sistema PODEM ser editadas.
        O bloqueio existe apenas para exclusão.
        """
        changed = []
        if name is not None and governance.name != name:
            governance.name = name
            changed.append('name')
        if description is not None and governance.description != description:
            governance.description = description
            changed.append('description')

        if changed:
            governance.save(update_fields=changed)
        return governance

    @staticmethod
    def delete_governance(governance: ConsoleGovernance) -> None:
        """
        Exclui uma governança.

        Bloqueia apenas governanças protegidas ou de sistema.
        """
        if governance.is_protected:
            raise GovernanceProtectedError(
                'Não é possível excluir uma governança protegida'
            )
        if governance.is_system:
            raise GovernanceProtectedError(
                'Não é possível excluir uma governança de sistema'
            )

        governance.delete()

    @staticmethod
    def get_governance_by_key(key: str) -> Optional[ConsoleGovernance]:
        try:
            return ConsoleGovernance.objects.get(key=key)
        except ConsoleGovernance.DoesNotExist:
            return None

    @staticmethod
    def get_governance_or_raise(key: str) -> ConsoleGovernance:
        governance = ConsoleGovernanceService.get_governance_by_key(key)
        if not governance:
            raise GovernanceNotFoundError(
                f'Governança com key "{key}" não encontrada'
            )
        return governance

    @staticmethod
    def get_all_governances() -> List[ConsoleGovernance]:
        return list(ConsoleGovernance.objects.all())

    @staticmethod
    def get_governances_for_scope(scope: str) -> List[ConsoleGovernance]:
        """Lista governanças de um escopo específico."""
        return list(
            ConsoleGovernance.objects.filter(scope=scope).order_by('name')
        )

    @staticmethod
    def get_governance_capabilities(
        governance: ConsoleGovernance,
        include_inactive: bool = False,
    ) -> List[ConsoleCapability]:
        qs = ConsoleCapability.objects.filter(
            governances_relation__governance=governance
        )
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return list(qs)

    @staticmethod
    @transaction.atomic
    def set_governance_capabilities(
        governance: ConsoleGovernance,
        capability_codes: List[str],
        updated_by=None,
    ) -> None:
        capabilities = []
        for code in capability_codes:
            try:
                cap = ConsoleCapability.objects.get(code=code)
            except ConsoleCapability.DoesNotExist:
                raise CapabilityNotFoundError(
                    f'Capability com código "{code}" não encontrada'
                )
            if not cap.is_active:
                raise CapabilityNotFoundError(
                    f'Capability "{code}" está inativa e não pode ser atribuída'
                )
            capabilities.append(cap)

        ConsoleGovernanceCapability.objects.filter(governance=governance).delete()

        ConsoleGovernanceCapability.objects.bulk_create([
            ConsoleGovernanceCapability(
                governance=governance,
                capability=cap,
                created_by=updated_by,
            )
            for cap in capabilities
        ])