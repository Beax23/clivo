"""
Documents — arquivos que o Clivo conhece.

============================================================================
REGRA ARQUITETURAL
============================================================================

`documents` responde por:

    - armazenar arquivos
    - registrar quem subiu, quem alterou, quando
    - associar arquivos a contexto (cliente, projeto futuro)
    - manter histórico de todas as alterações

`documents` NÃO responde por:

    - identidade do usuário           → pertence a `accounts`
    - contexto do cliente             → pertence a `clients`
    - briefing                        → pertence a `briefings`
    - projeto                         → pertence a `projects` (futuro)
    - timeline transversal            → pertence a `timeline`
    - interpretação/IA                → pertence a `intelligence`
    - integrações externas            → pertence a `references` (futuro)
                                         Pinterest/Unsplash como fontes
                                         ficam em `references.providers`
    - versionamento real de arquivo   → NÃO existe na V1

============================================================================
PRINCÍPIO
============================================================================

    Arquivo → armazenamento → contexto → rastreabilidade

Documents é o armazenamento canônico de arquivos do Clivo.

O arquiteto sobe um arquivo uma vez. O Clivo conhece aquele arquivo
em qualquer contexto que ele seja usado (cliente, briefing, projeto).

Documents não é Google Drive. Não é Office. Não é um sistema de
edição de conteúdo. É o cofre de arquivos do escritório.

============================================================================
MODELOS (P0)
============================================================================

    Document
        └── um arquivo conhecido pelo Clivo

    DocumentHistory
        └── registro de cada alteração no arquivo

O P0 tem DOIS MODELOS. Não criamos antecipadamente:

    ❌ DocumentTag             (sistema de tags é complexidade não pedida)
    ❌ DocumentFolder          (pastas complexas não existem na V1)
    ❌ DocumentVersion         (versionamento separado não existe na V1;
                                substituição registra no histórico)
    ❌ DocumentPermission      (permissões individuais por documento não
                                existem na V1; capability + workspace
                                resolvem)
    ❌ DocumentComment         (comentários não existem na V1)
    ❌ DocumentApproval        (aprovação não existe na V1)
    ❌ DocumentOCR             (OCR não existe na V1)

Cada um nasce quando existir demanda real.

============================================================================
SOBRE O ARQUIVO
============================================================================

O arquivo físico é armazenado via `FileField`, usando o storage padrão
do Django (`DEFAULT_FILE_STORAGE`). Se o projeto estiver configurado
com Cloudinary ou S3, usa o storage configurado. Se estiver em
`MEDIA_ROOT` local, usa local.

Documents NÃO amarra lógica específica de Cloudinary, S3, ou qualquer
provider. Trocar storage é decisão de infraestrutura, não deste módulo.

============================================================================
SOBRE A EXTENSÃO E O MIME TYPE
============================================================================

Documents NÃO possui lista de extensões permitidas.

O sistema aceita arquivos de todos os tipos. O que armazenamos é:

    - name         → nome sem extensão
    - extension    → extensão em minúsculas (ex: "pdf", "m4a")
    - mime_type    → MIME type reportado pelo upload
    - size         → tamanho em bytes
    - file         → arquivo físico

A visualização depende do tipo. Se o navegador não conseguir
visualizar, oferece download. Isso é responsabilidade da camada
de apresentação, não do model.

============================================================================
SOBRE O HISTÓRICO
============================================================================

`DocumentHistory` registra TODA alteração no documento.

Ações:
    created
    renamed
    replaced
    client_associated
    client_removed
    project_associated
    project_removed
    downloaded
    deleted

`downloaded` registra apenas ação + usuário + timestamp.
`previous_value` e `new_value` são NULL quando a ação não tem
estado anterior/novo.

`document` é FK nullable para `Document`. Quando o documento é
excluído, o histórico sobrevive com `document = NULL`. Isso preserva
auditoria sem preservar o arquivo.

============================================================================
REGRA DE EXCLUSÃO
============================================================================

    DELETE É DELETE.

Ao excluir um Document:

    - o arquivo físico é removido
    - o registro em `Document` é removido
    - o registro em `DocumentHistory` com action='deleted' é criado
      ANTES da exclusão, com `document` apontando para o objeto
      prestes a ser apagado
    - após a exclusão, o FK de `DocumentHistory` recebe SET_NULL
      automaticamente pelo Django

Sem soft delete. Sem restore. Sem lixeira.

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
FRONTEIRA CONGELADA (V1)
============================================================================

    accounts      → identidade e autenticação
    workspaces    → tenancy e membros
    console       → governança e capabilities
    clients       → contexto do cliente
    documents     → arquivos (este app)
    references    → curadoria de referências (futuro)
    briefings     → descoberta/contexto (futuro)
    projects      → operação (futuro)
    timeline      → memória factual (futuro)
    intelligence  → interpretação (futuro)

Documents apenas armazena. Não interpreta. Não versiona.
Não organiza em pastas. Não comenta. Não aprova.
"""

default_app_config = 'apps.documents.apps.DocumentsConfig'