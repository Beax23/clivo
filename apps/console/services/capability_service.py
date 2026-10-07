"""
ConsoleCapabilityService — descobre capabilities declaradas pelos apps.

REGRA ARQUITETURAL:
    Nenhuma capability nasce no Console.
    Toda capability nasce no domínio que a executa.

Cada app pode declarar suas capabilities em:
    apps/<app_name>/capabilities.py
"""

from importlib import import_module
from typing import List, Dict, Optional
import logging

from django.apps import apps
from django.db import transaction

from apps.console.models import ConsoleCapability
from apps.console.exceptions.console_exceptions import CapabilityNotFoundError

logger = logging.getLogger('console')


class ConsoleCapabilityService:
    """Descobre, sincroniza e consulta capabilities do catálogo."""

    # ==================================================================
    # DESCOBERTA
    # ==================================================================

    @staticmethod
    def discover_capabilities() -> List[Dict]:
        discovered: List[Dict] = []
        seen_codes: Dict[str, str] = {}

        for app_config in apps.get_app_configs():
            module_path = f"{app_config.name}.capabilities"

            try:
                module = import_module(module_path)
            except ModuleNotFoundError as exc:
                if exc.name == module_path:
                    continue
                raise

            capabilities = getattr(module, 'CAPABILITIES', None)
            if capabilities is None:
                logger.warning(
                    "App '%s' tem capabilities.py mas não define CAPABILITIES",
                    app_config.label,
                )
                continue

            if not isinstance(capabilities, list):
                raise TypeError(
                    f"{module_path}.CAPABILITIES deve ser uma lista, "
                    f"recebido {type(capabilities).__name__}"
                )

            for raw in capabilities:
                cap = ConsoleCapabilityService._normalize_capability(
                    raw=raw,
                    source_app=app_config.label,
                    module_path=module_path,
                )

                existing = seen_codes.get(cap['code'])
                if existing is not None:
                    raise ValueError(
                        f"Capability duplicada '{cap['code']}': "
                        f"declarada em '{existing}' e '{cap['source_app']}'"
                    )
                seen_codes[cap['code']] = cap['source_app']

                discovered.append(cap)

        logger.info(
            "discover_capabilities: %d capabilities em %d apps",
            len(discovered),
            len({c['source_app'] for c in discovered}),
        )
        return discovered

    @staticmethod
    def _normalize_capability(raw, source_app: str, module_path: str) -> Dict:
        if not isinstance(raw, dict):
            raise TypeError(
                f"{module_path}: cada item de CAPABILITIES deve ser dict, "
                f"recebido {type(raw).__name__}"
            )

        code = (raw.get('code') or '').strip()
        name = (raw.get('name') or '').strip()
        description = (raw.get('description') or '').strip()

        if not code:
            raise ValueError(f"{module_path}: capability sem 'code'")
        if not name:
            raise ValueError(f"{module_path}: capability '{code}' sem 'name'")

        parts = code.split('.')
        if len(parts) < 3:
            raise ValueError(
                f"{module_path}: code '{code}' deve ser "
                f"'<app>.<recurso>.<ação>'"
            )
        if parts[0] != source_app:
            raise ValueError(
                f"{module_path}: code '{code}' começa com '{parts[0]}', "
                f"mas o app é '{source_app}'"
            )

        return {
            'code': code,
            'name': name,
            'description': description,
            'source_app': source_app,
        }

    # ==================================================================
    # SINCRONIZAÇÃO
    # ==================================================================

    @staticmethod
    @transaction.atomic
    def sync_capabilities() -> Dict[str, int]:
        discovered = ConsoleCapabilityService.discover_capabilities()
        discovered_codes = {c['code'] for c in discovered}

        stats = {
            'discovered': len(discovered),
            'created': 0,
            'updated': 0,
            'unchanged': 0,
            'deactivated': 0,
            'reactivated': 0,
        }

        for cap_data in discovered:
            try:
                capability = ConsoleCapability.objects.get(code=cap_data['code'])
            except ConsoleCapability.DoesNotExist:
                ConsoleCapability.objects.create(
                    code=cap_data['code'],
                    name=cap_data['name'],
                    description=cap_data['description'],
                    source_app=cap_data['source_app'],
                    is_active=True,
                )
                stats['created'] += 1
                continue

            changed_fields = []
            if capability.name != cap_data['name']:
                capability.name = cap_data['name']
                changed_fields.append('name')
            if capability.description != cap_data['description']:
                capability.description = cap_data['description']
                changed_fields.append('description')
            if capability.source_app != cap_data['source_app']:
                capability.source_app = cap_data['source_app']
                changed_fields.append('source_app')
            if not capability.is_active:
                capability.is_active = True
                changed_fields.append('is_active')
                stats['reactivated'] += 1

            if changed_fields:
                capability.save(update_fields=changed_fields)
                stats['updated'] += 1
            else:
                stats['unchanged'] += 1

        stale = ConsoleCapability.objects.filter(
            is_active=True,
        ).exclude(code__in=discovered_codes)

        for capability in stale:
            capability.is_active = False
            capability.save(update_fields=['is_active'])
            stats['deactivated'] += 1
            logger.warning(
                "Capability '%s' não é mais declarada por nenhum app — "
                "marcada como inativa",
                capability.code,
            )

        logger.info("sync_capabilities: %s", stats)
        return stats

    # ==================================================================
    # CONSULTAS
    # ==================================================================

    @staticmethod
    def get_all_capabilities(include_inactive: bool = False) -> List[ConsoleCapability]:
        qs = ConsoleCapability.objects.all()
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return list(qs.order_by('source_app', 'name'))

    @staticmethod
    def get_capabilities_by_app(source_app: str) -> List[ConsoleCapability]:
        return list(
            ConsoleCapability.objects.filter(
                source_app=source_app,
                is_active=True,
            ).order_by('name')
        )

    @staticmethod
    def get_capability_by_code(code: str) -> Optional[ConsoleCapability]:
        try:
            return ConsoleCapability.objects.get(code=code)
        except ConsoleCapability.DoesNotExist:
            return None

    @staticmethod
    def get_capability_or_raise(code: str) -> ConsoleCapability:
        capability = ConsoleCapabilityService.get_capability_by_code(code)
        if capability is None:
            raise CapabilityNotFoundError(
                f'Capability com código "{code}" não encontrada'
            )
        return capability