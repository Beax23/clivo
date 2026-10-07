"""
Módulo de Contas e Autenticação do Clivo.

Este módulo gerencia:
- Identidade do usuário (User)
- Autenticação (Email/Password + Google OAuth via django-allauth)
- Sessões independentes (App + Console)
- Segurança de conta
- Recuperação de senha via email

O módulo NÃO contém:
- Auditoria administrativa (pertence ao Console)
- Controle de membros (pertence ao Workspace/Console)
- Permissões de plataforma (apenas identidade)

Accounts responde apenas: "Quem é essa pessoa e como ela autentica?"
"""