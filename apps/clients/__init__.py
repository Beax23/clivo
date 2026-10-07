"""
Clients — identidade, contexto e relacionamento com o cliente.

REGRA ARQUITETURAL
------------------
Clients responde por:

    - identidade persistente do cliente
    - contatos ligados ao cliente
    - anotações internas da equipe
    - portal externo do cliente (acesso, sessão, convite, feedback)

Clients NÃO responde por:

    - timeline transversal  → pertence ao domínio `timeline`
    - tarefas genéricas     → não existe task manager na V1
    - inteligência/IA       → pertence a `intelligence`
    - briefings             → pertence a `briefings`
    - projetos              → pertence a `projects`
    - documentos            → pertence a `documents`
    - propostas             → pertence a `proposals`
    - cálculos financeiros  → pertence a `finance`

O QUE O CLIENT POSSUI
---------------------

    Client
        ├── identidade (name, email, phone)
        ├── public_code (identificação pública — NÃO é senha)
        ├── context (JSONField — projeção publicada)
        └── status (active / inactive / suspended)

    ClientContact          → pessoas ligadas ao cliente
    ClientNote             → anotação interna da equipe

    ClientPortalAccess     → observabilidade do Portal
    ClientPortalSession    → sessão temporária de autenticação do Portal
    ClientPortalInvitation → registro de envio de acesso ao Portal
    ClientPortalFeedback   → feedback de experiência do Portal

EVENTOS DO DOMÍNIO
------------------

    ClientEventEmitter

Emite eventos de domínio via Signal Django. NÃO persiste timeline
localmente. O armazenamento é responsabilidade do domínio transversal
`timeline`, que ainda será construído.

REGRA DE EXCLUSÃO
-----------------

    DELETE é DELETE. Sem soft delete.

REGRA DE STATUS
---------------

    `status` é estado comercial/relacional definido pelo arquiteto:
        active / inactive / suspended

    NÃO é mecanismo de arquivamento. NÃO existe archive/unarchive.
    `status` é editável via capability `clients.client.update`.
"""

default_app_config = 'apps.clients.apps.ClientsConfig'