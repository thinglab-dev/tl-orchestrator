---
name: tl-impeccable-design
description: Use quando o Maker for criar, alterar ou refatorar interfaces (web, dashboards ou componentes de UI), ou quando o Checker for auditar a conformidade de design, ergonomia e acessibilidade de um diff. Elimina vícios e clichês de IA ("AI slop"), impondo hierarquia visual, contraste acessível, tipografia calibrada, estados completos e estética profissional.
metadata:
  target_roles:
    - maker
    - checker
  triggers:
    - "arquivos em web/, static/, templates/, css, html, js, tsx, jsx"
    - "tags de frontend, ui, redesign, dashboard, layout"
---

# TL-Impeccable Design: Frontend & UI de Alta Fidelidade

Esta skill é a autoridade de design para os agentes do TL-Orchestrator ao criar, alterar ou auditar interfaces (web, dashboards analíticos, componentes e páginas).

Ela existe para combater o **"AI Slop"**: a tendência crônica de modelos gerarem interfaces genéricas com gradientes azul/roxo clichês, cards aninhados sem função, fontes de sistema descalibradas e contraste insuficiente.

---

## 1. Princípios Fundamentais de Engenharia de Design

1. **Densidade e Intenção:** Dashboards de trading e inteligência de mercado exigem alta densidade de dados e legibilidade imediata. Elementos puramente decorativos sem valor funcional devem ser eliminados.
2. **Diretriz > Hábito:** A identidade e os tokens visuais definidos pelo projeto prevalecem sobre os vícios do modelo.
3. **Completude de Estados (Os 5 Estados Obrigatórios):** Todo elemento interativo DEVE implementar:
   * **Default:** Aparência estável de repouso.
   * **Hover:** Feedback visual sutil ao foco do cursor.
   * **Active / Focus-visible:** Anel de foco (`:focus-visible`) nítido com contraste mínimo 3:1 para navegação acessível por teclado.
   * **Disabled:** Cursor `not-allowed`, opacidade atenuada e sem eventos de clique.
   * **Loading / Error / Empty:** Skeletons de carregamento, alertas de erro com recuperação e telas vazias contextuais.

---

## 2. Tabela de Anti-Patterns Absolutos (Vícios Proibidos)

| Vício Proibido | O que NUNCA fazer | O que fazer em vez disso |
| :--- | :--- | :--- |
| **Cards Aninhados** | `div.card` dentro de outro `div.card` | Achatar a hierarquia usando linhas sutis (`border-subtle`), espaçamento modular ou pesos tipográficos. |
| **Kickers / Eyebrows** | Etiquetas minúsculas em caixa alta acima de títulos (`// OVERVIEW //`) | Deixar o título falar por si mesmo com peso e tamanho adequados. |
| **Texto em Gradiente** | `background-clip: text` com arco-íris de cores | Ênfase vem de contraste, escala ou peso tipográfico. |
| **Sombras Duras / Sem Blur** | `box-shadow: 4px 4px 0 ...` fora de estilo neobrutalista | Sombras com dispersão suave calculada ou borda sutil de 1px. |
| **Tracking Excessivo** | `letter-spacing < -0.04em` (letras coladas) | Manter entre `-0.02em` e `-0.03em` para títulos grandes; `0` para corpo. |
| **Preto/Branco Puro** | `#000000` ou `#ffffff` estourados em superfícies | Usar grafite profundo matizado (`#0d1117`, `#12161f`) para dark mode e off-white para light mode. |
| **Outline Removido às Cegas** | `outline: none` ou `outline: 0` sem `:focus-visible` | Preservar sempre um anel de foco visível em `:focus-visible`. |
| **Scrollbars e Seleção Padrão** | Deixar barra de rolagem e seleção de texto no padrão do SO | Estilizar `::selection` e `::-webkit-scrollbar` na paleta do projeto. |

---

## 3. Padrões Canônicos e Tokens Obrigatórios

### A. Tabela de Contraste Mínimo (WCAG AA Estrito)
* **Texto de corpo e placeholders:** $\ge 4.5:1$ de razão de contraste contra o fundo.
* **Títulos grandes ($\ge 18\text{pt}$ ou bold $\ge 14\text{pt}$):** $\ge 3:1$.
* **Números tabulares:** Sempre declarar `font-variant-numeric: tabular-nums` para evitar que colunas de dados numéricos dancem na tela.

### B. Sistema de Espaçamento Modular
```css
/* Escala de Espaçamento (Base 4px) */
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-6: 24px;
--space-8: 32px;
--space-12: 48px;
```
* **Regra de Gestalt:** O espaçamento acima de um título DEVE ser visivelmente maior que o espaçamento entre o título e o conteúdo logo abaixo.

---

## 4. Auditoria Determinística Offline

O auditor determinístico da skill valida arquivos HTML e CSS contra esses vícios:

```bash
python .agents/skills/tl-impeccable-design/scripts/audit_ui.py <caminhos...>
```

* **Exit Code 0:** Sucesso; todos os arquivos passaram sem nenhum anti-pattern detectado.
* **Exit Code 1:** Falha; anti-patterns ou erros operacionais detectados (falha fechada). Caminhos inexistentes ou diretórios sem arquivos elegíveis bloqueiam a esteira imediatamente.

---

## 5. Checklist de Verificação para o Checker

- [ ] `audit_ui.py` executado sobre os arquivos tocados e retornou exit code `0`.
- [ ] Nenhum card aninhado em elementos de visualização ou tabelas.
- [ ] Todo controle interativo possui `:focus-visible` navegável por teclado.
- [ ] Tabelas e métricas numéricas usam `tabular-nums` e alinhamento à direita.
- [ ] Textos longos possuem tratamento contra estouro visual (`overflow: hidden`, `text-overflow: ellipsis`).
