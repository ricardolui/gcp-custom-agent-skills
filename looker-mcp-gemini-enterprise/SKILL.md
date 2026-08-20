---
name: looker-mcp-gemini-enterprise
description: |
  Guias e melhores práticas para conectar e configurar o Looker Platform via Model Context Protocol (MCP) no Gemini Enterprise, permitindo invocar agentes e consultas semânticas nativas.
---

# Looker Platform MCP Integration with Gemini Enterprise

Este guia reúne as melhores práticas e passos necessários para conectar e configurar o **Model Context Protocol (MCP) do Looker Platform** no **Gemini Enterprise**. Esta integração permite que os usuários e agentes do Gemini Enterprise interajam diretamente com a camada semântica do Looker (LookML Explores), realizando perguntas em linguagem natural e construindo agentes no-code inteligentes.

---

## ⚙️ Pré-requisitos de Ambiente & Segurança (.env)

> [!IMPORTANT]
> **Verificação Prévia**: Antes de executar scripts, testes ou integrações CLI:
> 1. Certifique-se de que o arquivo `.env` existe no diretório raiz do projeto (crie a partir do `.env.example` se necessário):
>    ```bash
>    cp .env.example .env
>    ```
> 2. Exporte as variáveis de ambiente antes da execução:
>    ```bash
>    export $(grep -v '^#' .env | xargs)
>    ```
> 3. Utilize sempre as variáveis `${LOOKER_BASE_URL}`, `${GEMINI_ENTERPRISE_HOST_PROJECT}` e `${GEMINI_ENTERPRISE_OAUTH_CLIENT_ID}` em vez de expor valores reais em código.

---


## 1. Visão Geral das Abordagens e Arquitetura

Ao disponibilizar dados do Looker no Gemini Enterprise, duas alternativas principais foram avaliadas:

| Abordagem | Status de Sucesso | Detalhes Técnicos | Status do Recurso |
| :--- | :--- | :--- | :--- |
| **Conversational Analytics API (A2A)** | ❌ **Incompleto (Loop)** | Usa a API de Conversational Analytics e Agent Cards. Apresenta comportamento de loop infinito ("pensando") após a autorização do usuário. | Preview |
| **Model Context Protocol (MCP) Connector** |  **Sucesso** | Conecta o Gemini Enterprise diretamente ao endpoint `/mcp` do Looker via OAuth/PKCE. Permite chat direto e criação de agentes no-code. | Preview |

> [!IMPORTANT]
> A integração utilizando o **conector MCP** contorna com sucesso a limitação de publicação baseada em contas de serviço gerenciadas pelo Looker, garantindo que o contexto de segurança e permissionamento do usuário seja herdado corretamente via OAuth 2.0. Ambos os recursos (Looker MCP e Gemini MCP Connector) estão atualmente em **Preview**.

---

## 2. Pré-requisitos & Configurações no Looker

Antes de realizar a configuração no Gemini Enterprise, a instância do Looker deve ser devidamente preparada.

### A. Conexão com o BigQuery
1. No painel de administração do Looker, garanta que há uma conexão válida para o seu dataset do BigQuery.
2. Na aba **Home** ou de conexões, configure adequadamente o **Storage Project ID** e o **Billing Project ID** apontando para os projetos do BQ que serão faturados/consultados.

### B. Criação do LookML & Modelo
1. Ative o **Development Mode** no Looker.
2. Acesse **Create > LookML** (ou crie um novo projeto/modelo).
3. Selecione a conexão configurada, o dataset do BigQuery e adicione a tabela de testes com seus respectivos campos.
4. **Publique as alterações em produção** para garantir que a camada semântica esteja acessível para a API externa.

### C. Permissionamento e Perfis de Usuário
Configure as regras de acesso em **Admin > Roles**:
1. **Model Set**: Crie um novo Model Set contendo apenas o modelo LookML criado no passo anterior.
2. **Permission Set**: Garanta um conjunto de permissões adequado (ex: permissões básicas de `user` / `explore` / `see_lookml`).
3. **Role**: Crie uma nova Role associando o *Model Set* e o *Permission Set* criados, e atribua-a ao usuário que fará o login no Gemini.
4. **Roles do Usuário (Admin > Users)**: O usuário de teste deve possuir as seguintes roles atribuídas no Looker:
   - `Admin` (se necessário para configuração)
   - `Conversational Analytics User`
   - `Gemini`
   - `User`
   - `Viewer`

### D. Registro do Cliente OAuth (OAuth Client Registration)
Habilite o **API Explorer** no Marketplace do Looker e registre um novo aplicativo OAuth:
1. Vá para **API Explorer > Auth > Register OAuth App**.
2. No campo `Run it`, insira a seguinte configuração de parâmetros:
   - **`client_guid`**: `{CLIENT_ID}` (O identificador único gerado/escolhido para o Gemini Enterprise).
3. No corpo da requisição (**Body**), configure o redirecionamento oficial do Gemini Enterprise:
   ```json
   {
     "redirect_uri": "https://vertexaisearch.cloud.google.com/oauth-redirect",
     "display_name": "{CLIENT_DISPLAY_NAME}",
     "description": "{CLIENT_DESCRIPTION}",
     "enabled": true,
     "group_id": ""
   }
   ```

### E. Ativação do Looker MCP
1. Navegue até **Admin > MCP** na interface do Looker.
2. **Habilite todas as ferramentas (tools)** disponíveis no painel para que sejam expostas ao conector MCP.

---

## 3. Configuração do MCP Connector no Gemini Enterprise

No console do Gemini Enterprise, configure o novo Data Store do tipo MCP utilizando as credenciais e URIs registradas no Looker:

### Parâmetros de Configuração do Data Store

| Campo no Gemini Enterprise | Valor / Configuração | Observações |
| :--- | :--- | :--- |
| **MCP Server URL** | `https://{LOOKER_INSTANCE_URI}/mcp` | Endpoint do servidor MCP no Looker |
| **Authorization URL** | `https://{LOOKER_INSTANCE_URI}/auth` | Endpoint de autorização OAuth do Looker |
| **Authorization URL Parameters** | `&response_type=code&code_challenge_method=S256` | Parâmetros adicionais exigidos pelo PKCE |
| **Token URL** | `https://{LOOKER_INSTANCE_URI}/api/token` | Endpoint para troca de tokens de acesso |
| **Client ID** | `{CLIENT_ID}` | O Client ID cadastrado no registro OAuth do Looker |
| **Client Secret** | `none` (ou deixar vazio/conforme requerido) | O Looker OAuth público usa fluxo PKCE sem client secret |
| **Scopes** | `cors_api` | Escopo exigido para acesso à API |
| **PKCE verification enabled** | `true` | **Obrigatório** para fluxos de client público no Looker |

### Ativação de Ações (Actions)
Uma vez criado o Data Store com sucesso:
1. Vá até a seção de **Actions** (Ações) do agente/aplicativo no Gemini Enterprise.
2. Selecione e **habilite todas as ações disponíveis** expostas pelo Looker MCP Server.

---

## 4. Validação, Uso e Casos de Sucesso

Após a conclusão da configuração, os usuários finais autorizados (que possuem a permissão de `Agent User` e login ativo no Looker) podem interagir com os dados em duas modalidades principais:

### A. Interação via Chat Direto
- No painel de Chat do Gemini Enterprise, selecione o conector do Looker.
- Faça perguntas analíticas diretamente em linguagem natural.
- *Exemplo:* "Qual foi o faturamento total da categoria X no mês passado?"
- O Gemini traduzirá a pergunta em requisições para a ferramenta MCP correspondente, consultando o Explore do Looker de forma segura e transparente.

### B. Agentes No-Code Inteligentes
- Crie um agente customizado do tipo **No-Code** no Gemini Enterprise.
- Associe o Data Store do Looker MCP recém-criado a esse agente.
- O agente se tornará um especialista analítico focado em responder com base em suas regras de negócio LookML pré-definidas.

---

## 5. Resolução de Problemas (Troubleshooting)

> [!WARNING]
> **Loop Infinito de "Pensando" com API Conversational Analytics (A2A)**
> Se tentar usar a abordagem de agente A2A via Conversational Analytics API (que exporta o *agent card* via endpoint `.../v1/card`), o agente poderá autenticar com sucesso, mas entrará em um loop de processamento infinito sem retornar respostas. **Recomenda-se descontinuar essa abordagem e adotar o Looker MCP Connector padrão.**

### Outros Problemas Comuns:
- **Erro de Autenticação / OAuth Redirect:** Verifique se a URI de redirecionamento no registro de OAuth do Looker está exatamente definida como `https://vertexaisearch.cloud.google.com/oauth-redirect`.
- **Campos Ausentes nas Respostas:** Garanta que o LookML Model foi publicado para produção. Alterações apenas em "Development Mode" não são visíveis para o MCP Server de produção.
- **Ferramentas não listadas:** Verifique em **Admin > MCP** se as permissões e ferramentas estão ativadas globalmente na instância do Looker.
