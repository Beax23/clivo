"""
Briefings — conversa estruturada entre arquiteto e cliente.

============================================================================
REGRA ARQUITETURAL
============================================================================

`briefings` responde por:

    - modelos reutilizáveis de briefing (template)
    - execução de um briefing para um cliente específico
    - histórico imutável de eventos da conversa
    - projeção do estado atual de cada pergunta
    - transcrição e análise (IA) rastreáveis

`briefings` NÃO responde por:

    - identidade do usuário           → pertence a `accounts`
    - contexto do cliente             → pertence a `clients`
    - armazenamento de arquivos       → pertence a `documents`
    - projetos                        → pertence a `projects` (futuro)
    - timeline transversal            → pertence a `timeline` (futuro)

============================================================================
PRINCÍPIOS
============================================================================

1. Separação modelo / execução
   BriefingTemplate é reutilizável. Briefing é uma execução imutável
   para um cliente. Alterar o template NÃO altera execuções existentes
   (estrutura é copiada para um snapshot no momento da criação).

2. Tipo da pergunta ≠ formato da resposta
   `question_type` descreve a intenção do arquiteto.
   `allowed_response_formats` define o que o cliente pode enviar.

3. Histórico append-only
   BriefingEvent nunca é editado nem apagado. Cada resposta, dúvida,
   pedido de revisão ou intervenção é um novo evento.

4. Estado atual é projeção
   BriefingAnswer é a projeção do estado atual de uma pergunta.
   É derivada dos eventos, mas mantida explicitamente para consulta
   rápida. Respostas anteriores permanecem no histórico de eventos.

5. Transcrição e análise têm estado próprio
   Uma falha na transcrição NÃO invalida a resposta original.
   Uma análise antiga nunca parece atual (campo `is_stale`).

6. Rastreabilidade
   Cada item da análise aponta para a pergunta e o evento de origem.

============================================================================
MODELOS (V1)
============================================================================

BriefingTemplate        → modelo reutilizável criado pelo arquiteto
BriefingSection         → agrupamento de perguntas dentro do template
BriefingQuestion        → pergunta dentro de uma sessão do template

Briefing                → execução de um template para um cliente
BriefingAnswer          → projeção do estado atual de uma pergunta
BriefingEvent           → histórico imutável de eventos da conversa

============================================================================
FRONTEIRA CONGELADA (V1)
============================================================================

    accounts      → identidade
    workspaces    → tenancy
    console       → governança, capabilities, planos
    clients       → cliente e portal
    documents     → armazenamento de arquivos (imagens, áudio)
    briefings     → este app
    projects      → operação (futuro)
    timeline      → memória factual (futuro)
    intelligence  → interpretação (futuro)

"""

default_app_config = 'apps.briefings.apps.BriefingsConfig'