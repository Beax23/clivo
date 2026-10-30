# Worker de Inteligência — Guia de Operação

O worker de análise (`intelligence_worker`) processa os `AnalysisJob`
pendentes. Ele é iniciado **automaticamente** pelo
`IntelligenceConfig.ready()`, em uma thread daemon, sempre que a
aplicação Django sobe.

Não é preciso abrir terminal, nem configurar systemd, nem NSSM, em
nenhum ambiente. As variáveis de ambiente permitem ajustar o
comportamento quando necessário.

---

## Modos do worker

| Modo | Env var | Comportamento |
|---|---|---|
| **auto** (default) | `INTELLIGENCE_WORKER_MODE=auto` | Cada processo da aplicação (gunicorn worker, runserver, waitress) inicia um worker embutido. |
| **single** | `INTELLIGENCE_WORKER_MODE=single` + `INTELLIGENCE_WORKER_LEADER=1` em 1 processo | Apenas o processo marcado como líder inicia o worker. Os demais não. |
| **off** | `INTELLIGENCE_WORKER_MODE=off` ou `INTELLIGENCE_WORKER_DISABLED=1` | Nenhum worker embutido. Espera-se que o worker rode em processo separado. |

---

## Cenário 1 — Desenvolvimento (Windows, Linux, macOS)

**Nada a configurar além de `INTELLIGENCE_WORKER_MODE=single` + `INTELLIGENCE_WORKER_LEADER=1`** (que já está no `.env`). Rode:

```bash
python manage.py runserver