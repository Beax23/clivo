"""
Migração: WorkspaceSubscription passa a suportar múltiplas assinaturas
ao longo do tempo (histórico de trocas de plano).

Mudanças:
    1. `workspace` deixa de ser OneToOneField e vira ForeignKey com
       related_name='subscriptions'. A tabela `workspace_subscription`
       NÃO é recriada — o Django apenas altera a FK.
    2. Novos campos: `changed_by`, `changed_from`, `reason`.
    3. Nova constraint condicional: no máximo UMA assinatura ativa por
       workspace. Múltiplas inativas são permitidas (histórico).

O que NÃO muda:
    - Nenhum dado existente é apagado.
    - Nenhum `is_active`, `started_at`, `ended_at` é alterado.
    - Nenhum `plan` é trocado.

SOBRE O BACKFILL DE `reason`:
    O campo `reason` é adicionado com `default='initial'`. Em PostgreSQL
    (produção, Neon) e SQLite (testes), o `AddField` com `default` não
    nulo preenche automaticamente TODAS as linhas existentes com o valor
    default. Não é preciso `RunPython` para backfill.

SOBRE A DEPENDÊNCIA COM `console`:
    A dependência foi apontada para `console.0014_storageprovidersnapshot`
    (última migração APLICADA do console) em vez de `console.0015_...`
    (migração pendente do console, não relacionada a este commit).

    Motivo: a `workspaces.0004` referencia apenas `console.Plan`. O `Plan`
    não foi alterado por `console.0015` (que mexe em `Provider` e
    `StorageProviderSnapshot`). Manter a dependência em `0014` isola
    o Commit A da dívida pré-existente do `console`.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('console', '0014_storageprovidersnapshot'),
        ('workspaces', '0003_alter_workspaceinvitation_expires_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='workspacesubscription',
            name='changed_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Usuário que realizou a troca (NULL para criação inicial)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='plan_changes_made',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='workspacesubscription',
            name='changed_from',
            field=models.ForeignKey(
                blank=True,
                help_text='Assinatura anterior, quando esta é resultado de uma troca',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='changed_to',
                to='workspaces.workspacesubscription',
            ),
        ),
        migrations.AddField(
            model_name='workspacesubscription',
            name='reason',
            field=models.CharField(
                choices=[
                    ('initial', 'Criação inicial'),
                    ('upgrade', 'Upgrade'),
                    ('downgrade', 'Downgrade'),
                    ('manual', 'Ajuste manual'),
                    ('migration', 'Migração de dados'),
                    ('other', 'Outro'),
                ],
                default='initial',
                help_text='Motivo da criação desta assinatura',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='workspacesubscription',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace assinante',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='subscriptions',
                to='workspaces.workspace',
            ),
        ),
        migrations.AddConstraint(
            model_name='workspacesubscription',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_active', True)),
                fields=('workspace',),
                name='unique_active_subscription_per_workspace',
            ),
        ),
    ]