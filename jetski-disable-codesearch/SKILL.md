---
name: jetski-disable-codesearch
description: Configura projetos isolados ou repositórios Git locais no Jetski para desativar a ferramenta interna code_search do Google3 (Piper/CitC) e forçar o uso de grep_search, find_by_name e list_dir em 3 camadas (GEMINI.md/Rules, PreToolUse Hook inteligente e Custom Agent com google_mode: false). Ative sempre que o usuário pedir para desabilitar code_search em um projeto, pasta ou workspace isolado.
---

# Jetski Isolated Project — Disable `code_search` Skill (`jetski-disable-codesearch`)

Esta skill automatiza a configuração em **3 camadas** para desativar a ferramenta interna `code_search` do Google3 em projetos Git locais ou workspaces isolados de Google Cloud (fora do Piper/CitC), garantindo que tanto o agente principal quanto subagentes (`teamwork_preview`, `explore`, `implementer`, etc.) utilizem exclusivamente **`grep_search`**, **`find_by_name`** e **`list_dir`**.

---

## 🏗️ Arquitetura de 3 Camadas

Por padrão, o Jetski injeta a diretriz `<google3_infrastructure>` que obriga o modelo a usar `code_search`. Para neutralizar esse comportamento em projetos isolados sem prejudicar o uso do Jetski quando você estiver em um cliente CitC (`/google/src/cloud/...`), esta skill aplica 3 mecanismos complementares:

1. **Camada 1 — Precedência de Prompt & Regra de Workspace (`GEMINI.md` + `_agents/rules/no-codesearch.md`)**:
   - Cria/atualiza o `GEMINI.md` na raiz do projeto isolado e instala `_agents/rules/no-codesearch.md` com `trigger: always_on`.
   - Como instruções de `GEMINI.md` e `_agents/rules/` possuem precedência máxima sobre `<google3_infrastructure>`, o LLM vai direto para `grep_search` e `find_by_name` sem desperdiçar turnos.
2. **Camada 2 — Bloqueio Técnico Físico via `PreToolUse` Hook (`_agents/hooks.json` + `~/.gemini/config/hooks.json`)**:
   - Instala o script standalone `block_codesearch_hook.py` (evitando execução inline `python3 -c` que é bloqueada pelo `agcis-gatekeeper-hook`).
   - O hook inspeciona `workspacePaths` via `stdin`:
     - Se o workspace pertencer à lista de projetos isolados (ou não for `/google/src/`), retorna `{"decision": "deny"}` bloqueando fisicamente `code_search` e instruindo o uso de `grep_search` / `find_by_name`.
     - Se o workspace for um cliente CitC (`/google/src/cloud/...`), retorna `{"decision": "allow"}`.
   - Preserva integralmente hooks globais pré-existentes (como `agcis-gatekeeper-hook`).
3. **Camada 3 — Perfil de Agente Dedicado (`_agents/agents/local-gcp-dev/` com `google_mode: false`)**:
   - Registra o agente declarativo `local-gcp-dev` (`config.yaml` com `google_mode: false` e `agentic_mode: true`) no projeto e em `~/.gemini/config/agents/local-gcp-dev/`.

---

## 🚀 Execução Rápida (1 Comando)

Para aplicar as 3 camadas em qualquer projeto ou diretório isolado (`<TARGET_DIR>`), execute o instalador incluído nesta skill:

```bash
python3 /home/corpagent-eng-gricardo/myself/gcp-custom-agent-skills/jetski-disable-codesearch/scripts/apply_no_codesearch.py \
  --target /caminho/do/seu/projeto \
  --verify
```

### Argumentos Suportados
- `--target <PATH>`: Caminho absoluto ou relativo da pasta/projeto isolado onde o `code_search` deve ser desativado (padrão: diretório atual `.`).
- `--verify`: Executa automaticamente o teste de verificação simulando chamadas `PreToolUse` tanto no projeto isolado (esperado: `"deny"`) quanto em um workspace CitC `/google/src/cloud/...` (esperado: `"allow"`).

---

## 📋 Checklist Manual (Caso aplique sem o script)

Se precisar auditar ou aplicar manualmente os arquivos em um projeto `<PROJECT_DIR>`:

1. **`<PROJECT_DIR>/GEMINI.md`**: Deve declarar proibição explícita de `code_search` e obrigatoriedade de `grep_search` / `find_by_name`, além de instruir repasse dessa regra ao chamar `invoke_subagent`.
2. **`<PROJECT_DIR>/_agents/rules/no-codesearch.md`**: Deve conter frontmatter YAML `trigger: always_on`.
3. **`<PROJECT_DIR>/_agents/hooks.json` e `~/.gemini/config/hooks.json`**:
   - Nunca utilize `python3 -c` no campo `command` (bloqueado pelo gatekeeper). Aponte sempre para o arquivo `python3 <PATH_TO>/block_codesearch_hook.py`.
   - Nunca sobrescreva `~/.gemini/config/hooks.json` sem ler antes e preservar a chave `"agcis-gatekeeper-hook"`.
4. **`<PROJECT_DIR>/_agents/agents/local-gcp-dev/config.yaml`**: Deve configurar `coding_agent.google_mode: false`.
