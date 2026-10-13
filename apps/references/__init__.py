"""
References — imagens que o arquiteto escolheu para representar intenção.

============================================================================
REGRA ARQUITETURAL
============================================================================

`references` responde por:

    - armazenar imagens de referência (JPG, PNG, WEBP, GIF)
    - registrar título, descrição e categoria
    - organizar em pastas simples (uma camada, sem subpasta)
    - associar a cliente e/ou projeto (contexto opcional)
    - manter histórico de alterações

`references` NÃO responde por:

    - arquivos genéricos (PDF, DOCX, DWG)  → pertence a `documents`
    - identidade do usuário                → pertence a `accounts`
    - contexto do cliente                  → pertence a `clients`
    - projeto                              → pertence a `projects` (futuro)
    - timeline transversal                 → pertence a `timeline`
    - interpretação/IA                     → pertence a `intelligence`
    - importação externa (Pinterest, etc.) → NÃO existe no P0

============================================================================
PRINCÍPIO
============================================================================

    Imagem → significado → contexto → memória visual

References é a biblioteca visual do escritório.

O arquiteto sobe uma imagem, dá um título, explica por que ela importa,
e associa a um cliente e/ou projeto quando fizer sentido.

References NÃO é Pinterest. NÃO é moodboard editor. NÃO é marketplace.

É a memória visual do escritório.

============================================================================
MODELOS (P0)
============================================================================

    Reference           → uma imagem de referência
    ReferenceFolder     → agrupamento visual simples (1 camada)
    ReferenceHistory    → registro de cada alteração

O P0 tem TRÊS MODELOS. Não criamos antecipadamente:

    ❌ ReferenceTag           (tags são complexidade não pedida)
    ❌ ReferenceVersion       (versionamento não existe no P0;
                                substituição registra no histórico)
    ❌ ReferenceComment       (comentários não existem no P0)
    ❌ ReferenceApproval      (aprovação não existe no P0)
    ❌ ReferenceCollection    (board/moodboard não existe no P0)

Cada um nasce quando existir demanda real.

============================================================================
SOBRE A IMAGEM
============================================================================

A imagem é armazenada via `FileField`. O storage é o padrão do projeto
(`DEFAULT_FILE_STORAGE`). Se o projeto estiver com S3-compatible
(Backblaze B2, Cloudflare R2), usa o storage configurado. Se estiver
com `MEDIA_ROOT` local, usa local.

Aceitamos JPG, JPEG, PNG, WEBP e GIF.

Não bloqueamos por lista de extensões. A responsabilidade pela
validação é do serializer / presenter. O model aceita qualquer arquivo,
mas a semântica do domínio é: "isto é uma imagem".

PDF, DOCX, DWG e outros arquivos NÃO entram aqui. Esses são `Document`.

Isso mantém a fronteira limpa:

    Document  → arquivo do escritório (qualquer tipo)
    Reference → imagem de referência visual (só imagem)

============================================================================
SOBRE `project_id`
============================================================================

`project_id` é UUIDField solto, NÃO é FK, porque o app `projects`
ainda não existe.

    REGRA: este UUID representa `projects.Project.id`.
    Quando `projects` existir, isso vira ForeignKey.

Não transformar em `related_object_id`, `context_id` ou qualquer
nome genérico de pseudo-polimorfismo.

============================================================================
SOBRE PASTA
============================================================================

Uma `ReferenceFolder` é agrupamento VISUAL, não semântico.

A organização semântica continua sendo:
    Reference → Client → Project

Pasta é um atalho para "onde guardei isso", não "a que contexto pertence".

Regras:
    - Pasta pertence a UM workspace.
    - Pasta tem nome único por workspace.
    - Reference tem ZERO ou UMA pasta.
    - Excluir pasta NÃO exclui references — elas voltam a ficar soltas.
    - Sem subpastas no P0. Se um dia forem necessárias, adiciona-se `parent`.

============================================================================
SOBRE `category`
============================================================================

`category` é CharField com choices fixas. Não é FK para uma tabela
de categorias porque:

    - o conjunto é pequeno e estável
    - o usuário não cria categorias no P0
    - filtrar por escolha fixa é mais simples que gerenciar tabela

Se no futuro o usuário precisar criar categorias próprias, migra para FK.

============================================================================
SOBRE EXCLUSÃO
============================================================================

DELETE É DELETE. Sem soft delete. Sem lixeira. Sem restore.

Ao excluir uma Reference:
    - a imagem física é removida
    - o registro em `Reference` é removido
    - um `ReferenceHistory` com action='deleted' é criado ANTES da
      exclusão, com FK para o objeto prestes a ser apagado
    - após a exclusão, o FK de `ReferenceHistory` recebe SET_NULL
      automaticamente pelo Django

O histórico sobrevive. A imagem não.

============================================================================
FRONTEIRA CONGELADA (V1)
============================================================================

    accounts      → identidade e autenticação
    workspaces    → tenancy e membros
    console       → governança e capabilities
    clients       → contexto do cliente
    documents     → arquivos (qualquer tipo)
    references    → imagens de referência (este app)
    briefings     → descoberta/contexto (futuro)
    projects      → operação (futuro)
    timeline      → memória factual (futuro)
    intelligence  → interpretação (futuro)

References apenas armazena imagens e seu significado. Não interpreta.
Não versiona. Não comenta. Não aprova. Não cria boards.
"""

default_app_config = 'apps.references.apps.ReferencesConfig'