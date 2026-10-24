"""
Capabilities declaradas pelo módulo integrations.

REGRA: capability nasce no app que executa a ação.
O Console descobre, cataloga e permite que Governanças selecionem.

Formato: <app>.<resource>.<action> — o primeiro segmento DEVE ser
o label do AppConfig ('integrations').

ESTADO ATUAL (V1):
    NÃO há capabilities declaradas.

    Motivo: conectar uma conta Google é parte de operar o workspace,
    e qualquer membro pode fazê-lo. Não faz sentido gate-keeping.
    Quando existir uma página de integrações (administração de contas
    conectadas) ou política de "só admins podem conectar", esta
    decisão muda — e a capability apropriada volta a ser declarada.

    Hoje o único ponto de entrada para uma integração é o botão
    "Importar Forms" no Fluxo, que é gated por
    `briefings.template.manage` (a capability real da ação).
"""

CAPABILITIES = []