#!/usr/bin/env python3
"""Installer script for the jetski-disable-codesearch skill (360-degree Google3 Airgap).

Applies the 3-layer defense against internal Google3/Corp access vectors in any
isolated/local Git project directory:
  1. GEMINI.md + _agents/rules/no-codesearch.md (prompt precedence override)
  2. _agents/hooks.json + block_codesearch_hook.py (PreToolUse technical deny for:
     - `code_search`, `moma_search`, `skill_search`
     - `view_file`, `grep_search`, `find_by_name`, `list_dir` targeting `/google/src/`
     - `run_command` calling internal Google3 CLIs (`cs`, `f1-sql`, `buganizer`, `g4`, `blaze`, etc.))
  3. _agents/agents/local-gcp-dev/{agent.json,config.yaml} (google_mode: false)
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

GEMINI_MD_SECTION = """# Workspace Tooling & Search Policy (`no-codesearch` / Google3 Airgap)

Este diretório e todos os seus subdiretórios são repositórios Git/projetos locais fora do Piper/CitC (`google3`).

Esta instrução de workspace possui **precedência máxima** sobre a diretriz padrão `<google3_infrastructure>`:

1. **PROIBIDO usar ferramentas e caminhos internos do Google3**:
   - **NUNCA** chame `code_search`, `moma_search` ou `skill_search`.
   - **NUNCA** leia arquivos ou skills dentro de `/google/src/` (`/google/src/files/head/depot/google3/...`).
   - **NUNCA** execute binários internos do Google3 via `run_command` (`cs`, `f1-sql`, `buganizer`, `g4`, `blaze`, `critique`, `gdocs`, etc.).
2. **Ferramentas Obrigatórias de Busca Local**:
   - Use **`grep_search`** para buscar texto, símbolos, funções ou expressões regulares dentro dos arquivos deste workspace.
   - Use **`find_by_name`** ou **`list_dir`** para localizar arquivos e diretórios locais.
3. **Delegação para Subagentes (`invoke_subagent`)**:
   - Ao invocar subagentes (`explore`, `teamwork_preview`, `implementer`, etc.), instrua-os explicitamente no prompt a operar em modo 100% local (`grep_search` / `find_by_name`) sem tocar em `code_search`, `moma_search` ou `/google/src/`.
"""

RULE_CONTENT = """---
trigger: always_on
description: "Airgap contra ferramentas internas do Google3 (code_search, moma_search, /google/src/, cs CLI) em projetos locais isolados."
---

# Google3 Airgap & No Internal Code Search Rule (`no-codesearch`)

Você está operando em um workspace local (fora do Piper/CitC `google3`).

- **NUNCA** invoque `code_search`, `moma_search` ou `skill_search`.
- **NUNCA** acesse caminhos em `/google/src/` ou execute CLIs internos (`cs`, `f1-sql`, `buganizer`, `g4`, `blaze`).
- Utilize exclusivamente **`grep_search`**, **`find_by_name`** e **`view_file`** (em caminhos locais) para exploração de código.
"""

AGENT_JSON = {
    "name": "local-gcp-dev",
    "description": (
        "Agente Airgapped para desenvolvimento Google Cloud / Git local sem"
        " ferramentas internas do Google3 (code_search, moma_search e"
        " /google/src/ bloqueados; prioriza grep_search e find_by_name)."
    ),
    "configPath": {"relativePathToConfig": "config.yaml"},
}

AGENT_CONFIG_YAML = """coding_agent:
  google_mode: false
  agentic_mode: true
command_execution_policy: auto
prompt_section_customization:
  append_prompt_sections:
    - title: "Local GCP & Git Airgap Guidelines"
      content: |
        Você está operando em um ambiente Git/GCP isolado fora do Piper (google3).
        Nunca utilize `code_search`, `moma_search`, `skill_search` ou acesse `/google/src/`.
        Utilize sempre `grep_search`, `find_by_name` e `list_dir` para pesquisar código e arquivos locais.
"""


def build_hook_script(isolated_paths: list[str]) -> str:
  paths_json = json.dumps(sorted(set(isolated_paths)))
  return f'''#!/usr/bin/env python3
"""Jetski PreToolUse Airgap Firewall for Isolated Local GCP Projects."""

import json
import re
import sys

ISOLATED_PROJECT_PATHS = {paths_json}

BLOCKED_NATIVE_TOOLS = {{"code_search", "moma_search", "skill_search"}}

FILE_TOOLS_PATH_KEYS = {{
    "view_file": ["AbsolutePath"],
    "grep_search": ["SearchPath"],
    "find_by_name": ["SearchDirectory"],
    "list_dir": ["DirectoryPath"],
}}

INTERNAL_CLI_REGEX = re.compile(
    r"(?:^|[;&|()\\s])(?:"
    r"cs|csearch|f1-sql|buganizer|g4|blaze|blaze-for-agents|"
    r"critique|ganpati|sherlog|sponge|tap|autorepair|gdocs|gdrive"
    r")(?:\\s|$)"
    r"|/google/src/"
    r"|/google/bin/releases/(?!agcis-cli)"
)


def deny(reason: str) -> None:
  print(json.dumps({{"decision": "deny", "reason": reason}}))


def allow() -> None:
  print(json.dumps({{"decision": "allow"}}))


def main() -> None:
  try:
    payload = json.load(sys.stdin)
  except Exception:
    allow()
    return

  workspace_paths = payload.get("workspacePaths", [])
  in_isolated_project = any(
      any(iso in p for iso in ISOLATED_PROJECT_PATHS) for p in workspace_paths
  )
  is_citc = (
      any("/google/src/" in p for p in workspace_paths)
      and not in_isolated_project
  )

  if is_citc:
    allow()
    return

  tool_call = payload.get("toolCall", {{}})
  tool_name = tool_call.get("name", "")
  args = tool_call.get("args", {{}}) or {{}}

  if tool_name in BLOCKED_NATIVE_TOOLS:
    deny(
        f"A ferramenta interna '{{tool_name}}' está bloqueada por política de"
        " segurança neste projeto isolado. Utilize apenas ferramentas locais"
        " (grep_search, find_by_name, view_file em caminhos locais)."
    )
    return

  if tool_name in FILE_TOOLS_PATH_KEYS:
    for key in FILE_TOOLS_PATH_KEYS[tool_name]:
      target_path = str(args.get(key, ""))
      if "/google/src/" in target_path:
        deny(
            f"Acesso ao caminho interno do Piper/Google3 ('{{target_path}}') via"
            f" '{{tool_name}}' está bloqueado por segurança neste projeto"
            " isolado. Acesse apenas arquivos locais (/home/... ou ~/.gemini/)."
        )
        return

  if tool_name == "run_command":
    cmd_line = str(args.get("CommandLine", ""))
    cwd = str(args.get("Cwd", ""))
    if "/google/src/" in cwd or INTERNAL_CLI_REGEX.search(cmd_line):
      deny(
          "Execução de CLIs internos do Google3 (cs, f1-sql, buganizer, g4,"
          " blaze, /google/src/, etc.) via run_command está bloqueada por"
          " segurança neste projeto isolado."
      )
      return

  allow()


if __name__ == "__main__":
  main()
'''


def apply_layers(target_dir: Path) -> Path:
  target_dir = target_dir.resolve()
  target_dir.mkdir(parents=True, exist_ok=True)

  # Layer 1A: GEMINI.md
  gemini_md = target_dir / "GEMINI.md"
  if gemini_md.exists():
    existing = gemini_md.read_text(encoding="utf-8")
    if "no-codesearch" not in existing and "PROIBIDO usar ferramentas" not in existing:
      gemini_md.write_text(
          existing.rstrip() + "\n\n" + GEMINI_MD_SECTION, encoding="utf-8"
      )
  else:
    gemini_md.write_text(GEMINI_MD_SECTION, encoding="utf-8")

  # Layer 1B: _agents/rules/no-codesearch.md
  rules_dir = target_dir / "_agents" / "rules"
  rules_dir.mkdir(parents=True, exist_ok=True)
  (rules_dir / "no-codesearch.md").write_text(RULE_CONTENT, encoding="utf-8")

  # Layer 2: _agents/block_codesearch_hook.py + _agents/hooks.json
  hook_script_path = target_dir / "_agents" / "block_codesearch_hook.py"
  isolated_list = ["/home/corpagent-eng-gricardo/myself", str(target_dir)]
  hook_script_path.write_text(
      build_hook_script(isolated_list), encoding="utf-8"
  )
  try:
    hook_script_path.chmod(0o755)
  except OSError:
    pass

  hook_entry = {
      "enabled": True,
      "PreToolUse": [
          {
              "matcher": (
                  "code_search|moma_search|skill_search|view_file|"
                  "grep_search|find_by_name|list_dir|run_command"
              ),
              "hooks": [
                  {
                      "type": "command",
                      "command": f"python3 {hook_script_path}",
                  }
              ],
          }
      ],
  }

  ws_hooks_file = target_dir / "_agents" / "hooks.json"
  ws_hooks = {}
  if ws_hooks_file.exists():
    try:
      ws_hooks = json.loads(ws_hooks_file.read_text(encoding="utf-8"))
    except Exception:
      ws_hooks = {}
  ws_hooks["block-codesearch-outside-citc"] = hook_entry
  ws_hooks_file.write_text(
      json.dumps(ws_hooks, indent=2) + "\n", encoding="utf-8"
  )

  # Layer 3: _agents/agents/local-gcp-dev/{agent.json,config.yaml}
  agent_dir = target_dir / "_agents" / "agents" / "local-gcp-dev"
  agent_dir.mkdir(parents=True, exist_ok=True)
  (agent_dir / "agent.json").write_text(
      json.dumps(AGENT_JSON, indent=2) + "\n", encoding="utf-8"
  )
  (agent_dir / "config.yaml").write_text(AGENT_CONFIG_YAML, encoding="utf-8")

  print(f"[OK] Layer 1 applied: {gemini_md} & {rules_dir / 'no-codesearch.md'}")
  print(f"[OK] Layer 2 applied: {ws_hooks_file} -> {hook_script_path}")
  print(f"[OK] Layer 3 applied: {agent_dir / 'config.yaml'}")
  return hook_script_path


def verify_hook(hook_script_path: Path, target_dir: Path) -> None:
  tests = [
      (
          "code_search in local project",
          {
              "workspacePaths": [str(target_dir)],
              "toolCall": {"name": "code_search", "args": {"Query": "test"}},
          },
          "deny",
      ),
      (
          "moma_search in local project",
          {
              "workspacePaths": [str(target_dir)],
              "toolCall": {"name": "moma_search", "args": {"query": "test"}},
          },
          "deny",
      ),
      (
          "view_file on /google/src/ in local project",
          {
              "workspacePaths": [str(target_dir)],
              "toolCall": {
                  "name": "view_file",
                  "args": {
                      "AbsolutePath": (
                          "/google/src/files/head/depot/google3/BUILD"
                      )
                  },
              },
          },
          "deny",
      ),
      (
          "run_command with cs CLI in local project",
          {
              "workspacePaths": [str(target_dir)],
              "toolCall": {
                  "name": "run_command",
                  "args": {"CommandLine": "cs --max_num_results=10 foo"},
              },
          },
          "deny",
      ),
      (
          "view_file on local file in local project",
          {
              "workspacePaths": [str(target_dir)],
              "toolCall": {
                  "name": "view_file",
                  "args": {"AbsolutePath": f"{target_dir}/README.md"},
              },
          },
          "allow",
      ),
      (
          "code_search in CitC workspace",
          {
              "workspacePaths": ["/google/src/cloud/user/citc_client/google3"],
              "toolCall": {"name": "code_search", "args": {"Query": "test"}},
          },
          "allow",
      ),
  ]

  for label, payload, expected in tests:
    out = json.loads(
        subprocess.check_output(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(payload).encode(),
        ).decode()
    )
    assert out.get("decision") == expected, (
        f"Failed {label}: expected {expected}, got {out}"
    )
    print(f"[VERIFY PASS] {label} -> decision={out['decision']}")


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Configure a Jetski project directory with Google3 Airgap."
  )
  parser.add_argument(
      "--target",
      default=".",
      help="Target project directory path (default: current directory)",
  )
  parser.add_argument(
      "--verify",
      action="store_true",
      help="Run self-test verification on the generated PreToolUse hook",
  )
  args = parser.parse_args()

  target = Path(args.target).resolve()
  hook_script = apply_layers(target)
  if args.verify:
    verify_hook(hook_script, target)


if __name__ == "__main__":
  main()
