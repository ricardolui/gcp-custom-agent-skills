#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
clean_gemini_enterprise.py

Script para listar e limpar agentes conversacionais e autorizações órfãs no:
1. Gemini Enterprise (Discovery Engine API: discoveryengine.googleapis.com)
2. BigQuery Conversational Analytics (Gemini Data Analytics API: geminidataanalytics.googleapis.com)

Suporta confirmação interativa, modo dry-run e seleção customizada de projetos/regiões.
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple
import requests

try:
    import google.auth
    from google.auth.transport.requests import Request
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


def get_access_token(account: Optional[str] = None) -> str:
    """Obtém token de acesso via gcloud CLI ou Google Auth ADC."""
    cmd = "CLOUDSDK_METRICS_ENVIRONMENT=datacloud.jetski gcloud auth print-access-token"
    if account:
        cmd += f" --account={account}"
    
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    token = res.stdout.strip().split("\n")[-1]
    if token and not token.startswith("ERROR") and len(token) > 20:
        return token
    
    if GOOGLE_AUTH_AVAILABLE:
        creds, _ = google.auth.default()
        creds.refresh(Request())
        return creds.token
        
    raise RuntimeError("Não foi possível obter o token de autenticação GCP.")


def list_discovery_engine_resources(
    project_id: str,
    token: str,
    location: str = "global"
) -> Tuple[List[Dict], List[Dict]]:
    """
    Lista engines, agentes customizados e autorizações no Discovery Engine.
    Preserva agentes de sistema (ex: deep_research ou com managedAgentDefinition).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": project_id
    }
    
    agents_to_clean = []
    auths_to_clean = []
    
    # 1. Listar Engines
    engines_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines"
    r_eng = requests.get(engines_url, headers=headers)
    if r_eng.ok:
        engines = r_eng.json().get("engines", [])
        for eng in engines:
            eng_name = eng.get("name")
            eng_id = eng_name.split("/")[-1]
            display = eng.get("displayName")
            
            # Listar Agentes da Engine
            agents_url = f"https://discoveryengine.googleapis.com/v1alpha/{eng_name}/assistants/default_assistant/agents"
            r_ag = requests.get(agents_url, headers=headers)
            if r_ag.ok:
                agents = r_ag.json().get("agents", [])
                for ag in agents:
                    ag_name = ag.get("name")
                    ag_id = ag_name.split("/")[-1]
                    ag_display = ag.get("displayName", ag_id)
                    # Não deletar agentes gerenciados de sistema
                    if ag_id == "deep_research" or ag.get("managedAgentDefinition"):
                        continue
                    agents_to_clean.append({
                        "name": ag_name,
                        "id": ag_id,
                        "displayName": ag_display,
                        "engineId": eng_id,
                        "project": project_id
                    })
    
    # 2. Listar Autorizações órfãs
    auth_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/authorizations"
    r_auth = requests.get(auth_url, headers=headers)
    if r_auth.ok:
        auths = r_auth.json().get("authorizations", [])
        for au in auths:
            au_name = au.get("name")
            au_id = au_name.split("/")[-1]
            auths_to_clean.append({
                "name": au_name,
                "id": au_id,
                "project": project_id
            })
            
    return agents_to_clean, auths_to_clean


def list_gemini_data_agents(
    project_id: str,
    token: str,
    locations: List[str]
) -> List[Dict]:
    """Lista todos os Data Agents do BigQuery Conversational Analytics."""
    headers = {"Authorization": f"Bearer {token}"}
    data_agents = []
    
    for loc in locations:
        url = f"https://geminidataanalytics.googleapis.com/v1beta/projects/{project_id}/locations/{loc}/dataAgents?pageSize=100"
        r = requests.get(url, headers=headers)
        if r.ok:
            agents = r.json().get("dataAgents", [])
            for da in agents:
                da_name = da.get("name")
                da_id = da_name.split("/")[-1]
                da_display = da.get("displayName", da_id)
                data_agents.append({
                    "name": da_name,
                    "id": da_id,
                    "displayName": da_display,
                    "location": loc,
                    "project": project_id
                })
    return data_agents


def delete_resource(url: str, token: str, quota_project: Optional[str] = None) -> bool:
    """Executa a exclusão de um recurso via DELETE HTTP."""
    headers = {"Authorization": f"Bearer {token}"}
    if quota_project:
        headers["X-Goog-User-Project"] = quota_project
        
    res = requests.delete(url, headers=headers)
    return res.status_code in [200, 204, 404]


def main():
    parser = argparse.ArgumentParser(
        description="Limpa agentes conversacionais no Gemini Enterprise e BigQuery Conversational Analytics."
    )
    parser.add_argument(
        "--projects",
        nargs="+",
        default=["dataml-latam-argolis", "argolis-zeneto"],
        help="Lista de projetos GCP para inspeção e limpeza."
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Conta gcloud específica para autenticação (ex: admin@gricardo.altostrat.com)."
    )
    parser.add_argument(
        "--locations",
        nargs="+",
        default=["global", "us", "us-central1", "southamerica-east1", "europe-west1"],
        help="Regiões do Gemini Data Analytics a verificar."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas lista os recursos sem deletar."
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Pula o prompt interativo de confirmação."
    )

    args = parser.parse_args()

    print("\n=======================================================")
    print("🧹 GEMINI ENTERPRISE & CONVERSATIONAL ANALYTICS CLEANUP")
    print("=======================================================")
    print(f"Projetos alvo: {args.projects}")
    print(f"Modo Dry-Run: {'SIM' if args.dry_run else 'NÃO'}")

    try:
        token = get_access_token(args.account)
    except Exception as e:
        print(f"\n❌ Erro de Autenticação: {e}")
        sys.exit(1)

    all_de_agents = []
    all_de_auths = []
    all_gda_agents = []

    print("\n🔍 Escaneando recursos nos projetos...")
    for proj in args.projects:
        # Discovery Engine
        de_agents, de_auths = list_discovery_engine_resources(proj, token)
        all_de_agents.extend(de_agents)
        all_de_auths.extend(de_auths)
        
        # Gemini Data Analytics
        gda_agents = list_gemini_data_agents(proj, token, args.locations)
        all_gda_agents.extend(gda_agents)

    # Exibição do Resumo
    print("\n-------------------------------------------------------")
    print(f"📦 Discovery Engine Custom Agents ({len(all_de_agents)} encontrados):")
    for a in all_de_agents:
        print(f"   • [{a['project']}] {a['id']} -> \"{a['displayName']}\"")

    print(f"\n🔑 Discovery Engine Authorizations ({len(all_de_auths)} encontradas):")
    for au in all_de_auths:
        print(f"   • [{au['project']}] {au['id']}")

    print(f"\n📊 BigQuery Data Analytics Agents ({len(all_gda_agents)} encontrados):")
    for da in all_gda_agents:
        print(f"   • [{da['project']} / {da['location']}] {da['id']} -> \"{da['displayName']}\"")
    print("-------------------------------------------------------")

    total_items = len(all_de_agents) + len(all_de_auths) + len(all_gda_agents)
    if total_items == 0:
        print("\n✨ Nenhum recurso pendente para exclusão. Ambiente já está 100% limpo!")
        return

    if args.dry_run:
        print(f"\n⚠️ Modo Dry-Run finalizado. Total de {total_items} recursos identificados.")
        return

    # Confirmação do Usuário
    if not args.yes:
        print(f"\n⚠️ ATENÇÃO: {total_items} recursos serão permanentemente excluídos dos projetos: {args.projects}")
        confirm = input("Deseja confirmar e prosseguir com a exclusão? [s/N]: ").strip().lower()
        if confirm not in ["s", "sim", "y", "yes"]:
            print("Operação cancelada pelo usuário.")
            return

    print("\n🚀 Executando exclusão de recursos...")

    # 1. Deletar Agentes Discovery Engine
    for ag in all_de_agents:
        print(f"  [DELETING] Discovery Engine Agent: {ag['id']} ({ag['displayName']})...")
        url = f"https://discoveryengine.googleapis.com/v1alpha/{ag['name']}"
        success = delete_resource(url, token, quota_project=ag["project"])
        print(f"    -> {'Sucesso' if success else 'Falha'}")

    # 2. Deletar Autorizações Discovery Engine
    for au in all_de_auths:
        print(f"  [DELETING] Authorization: {au['id']}...")
        url = f"https://discoveryengine.googleapis.com/v1alpha/{au['name']}"
        success = delete_resource(url, token, quota_project=au["project"])
        print(f"    -> {'Sucesso' if success else 'Falha'}")

    # 3. Deletar BigQuery Data Agents
    for da in all_gda_agents:
        print(f"  [DELETING] BigQuery DataAgent: {da['id']} ({da['displayName']})...")
        url = f"https://geminidataanalytics.googleapis.com/v1beta/{da['name']}"
        success = delete_resource(url, token)
        print(f"    -> {'Sucesso' if success else 'Falha'}")

    print("\n✅ Operação de limpeza finalizada com sucesso!")


if __name__ == "__main__":
    main()
