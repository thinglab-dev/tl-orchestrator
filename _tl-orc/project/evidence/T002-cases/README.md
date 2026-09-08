# Casos de Medição em Smoke Sintético (T002)

Este diretório armazena os artefatos da medição empírica prevista no critério de aceitação **AC03** da Task Native T002.

## Consolidação dos Resultados

- `RESULTS.md`: Registro consolidado das 6 chamadas executadas pelo Orquestrador em 2026-09-08 (linhas 1–31), com identificadores de sessão, carimbos UTC, conferência mecânica em duas camadas (estrutura e catálogo/pins/IDs), inventário de defeitos da primeira resposta, comandos completos para reprodução da conferência, limites declarados da medição e ressalva sobre a procedência normativa dos IDs locais.

## Objetivo e Estrutura dos Arquivos

A medição confronta a taxa de respostas estruturalmente e semanticamente válidas na primeira chamada do Classificador (`gpt-5.6-luna`, `effort: medium`) entre dois estilos de briefing, utilizando a mesma intenção sintética e o mesmo catálogo controlado:

1. **Briefings em Prosa (estilo v0.6.0 do Claude Code):**
   - `briefing-prosa-1.md`: 1ª chamada com descrição dos campos em prosa, sem esqueleto JSON literal (3.545 caracteres, 3.598 bytes).
   - `briefing-prosa-2.md`: 2ª chamada em sessão nova com o mesmo estilo em prosa (3.545 caracteres, 3.598 bytes).
   - `briefing-prosa-3.md`: 3ª chamada em sessão nova com o mesmo estilo em prosa (3.545 caracteres, 3.598 bytes).

2. **Briefings Mínimos (com Esqueleto Literal derivado de `_tl-orc/project/evidence/T002-briefing-skeleton.py`):**
   - `briefing-minimo-1.md`: 1ª chamada com briefing mínimo estruturado, esqueleto JSON literal e regras fixas (10.131 caracteres, 10.245 bytes; 6.586 caracteres a mais).
   - `briefing-minimo-2.md`: 2ª chamada em sessão nova com o mesmo briefing mínimo estruturado (10.131 caracteres, 10.245 bytes).
   - `briefing-minimo-3.md`: 3ª chamada em sessão nova com o mesmo briefing mínimo estruturado (10.131 caracteres, 10.245 bytes).

3. **Respostas Canônicas do Classificador:**
   - `resposta-prosa-1.json`, `resposta-prosa-3.json`: saída JSON da primeira resposta, na qual o modelo encerrou prematuramente o objeto JSON raiz antes de `confidence` e emitiu fragmento adicional `,"confidence":"high"}` fora da raiz (gerando erro `Extra data` no validador, e não truncamento).
   - `resposta-prosa-2.json`: saída JSON parseável, porém estruturalmente inválida (omissão de `schema_version`, `context_revision`, `catalog_revision`, inclusão de `version` extra e enums de `tier` inválidos).
   - `resposta-minimo-1.json`: saída JSON íntegra e 100% válida, com dimensionamento dos três papéis em `tier: "normal"`.
   - `resposta-minimo-2.json`, `resposta-minimo-3.json`: saídas JSON íntegras e 100% válidas, com dimensionamento dos três papéis em `tier: "simple"`.

4. **Conferência Mecânica em Duas Camadas:**
   - `check-prosa-1.txt`, `check-prosa-2.txt`, `check-prosa-3.txt`: registros de conferência separando a **saída literal dos comandos** da interpretação analítica do Orquestrador.
   - `check-minimo-1.txt`, `check-minimo-2.txt`, `check-minimo-3.txt`: registros de conferência em duas camadas das respostas mínimas, separando saída literal e interpretação.
   - `tools/`: ferramentas utilizadas na conferência mecânica:
     - `tools/check_struct.py`: validador mecânico estrito contra `schemas/classification-result.schema.json` sem dependências externas;
     - `tools/mech_check.py`: verificador de catálogo, cadeias, pins e evidências a partir de `_tl-orc/PROJECT.md` e expectativas pré-definidas;
     - `tools/expected-medicao.json`: arquivo de expectativas utilizado por `mech_check.py`.

## Protocolo de Execução e Distinção Operacional

- **Modelo e Esforço:** Codex `gpt-5.6-luna` com `effort: medium` fixo.
- **Sessões:** Cada uma das 6 chamadas executada em sessão independente e isolada (`fresh session` via `codex exec`), em sandbox read-only, sem histórico prévio.
- **Sem Correção:** Nenhuma rodada interativa de correção ou `resume` admitida; a métrica avalia estritamente a **primeira resposta**.
- **Reprodução da Conferência vs. Nova Medição:**
  - *Reprodução da conferência:* Para revalidar mecanicamente as respostas preservadas sem custos de rede ou API, execute os comandos de conferência a partir da raiz do repositório:
    ```bash
    python3 _tl-orc/project/evidence/T002-cases/tools/check_struct.py schemas/classification-result.schema.json _tl-orc/project/evidence/T002-cases/resposta-<...>.json
    python3 _tl-orc/project/evidence/T002-cases/tools/mech_check.py _tl-orc/project/evidence/T002-cases/resposta-<...>.json _tl-orc/project/evidence/T002-cases/tools/expected-medicao.json
    ```
  - *Nova medição:* Exige novas chamadas pagas à CLI do Codex com criação de novas sessões e envio dos briefings via stdin (`RESULTS.md:17-19`), gerando novas respostas que deverão ser submetidas às mesmas camadas de verificação.
- **Limite sobre a Procedência dos IDs Locais:** Os quatro IDs `local-*` foram fornecidos no briefing com referências genéricas aos relatórios de origem e não constam na primeira coluna de tabelas estruturadas nesses arquivos (`prompts/orchestrator-perfis.md:242-245`). A conferência mecânica atesta exclusivamente o pertencimento dos IDs ao conjunto fornecido no briefing, sem comprovar a procedência normativa integral desses registros. Esse limite aplica-se igualmente a ambas as condições experimentais.
