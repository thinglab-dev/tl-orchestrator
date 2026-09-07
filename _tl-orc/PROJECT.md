format_version: 1
work_method: native

## Fontes autoritativas

| Tipo | Localização | Uso | Última conferência |
| :--- | :--- | :--- | :--- |
| Instruções do repositório fonte | `AGENTS.md`, `CONTRIBUTING.md` | política de contribuição e fechamento | 2026-09-07 |
| Contratos do método | `SKILL.md`, `prompts/`, `docs/`, `schemas/` | o próprio pacote, editado neste repositório | 2026-09-07 |

## Portões

| Portão | Diretório | Origem/condição |
| :--- | :--- | :--- |
| `python3 scripts/validate_repository.py` | raiz | CI do repositório |

## Modelo de trabalho

Este é o repositório fonte do método; não há instalação em `_tl-orc/package`. A área `global` em
`_tl-orc/project/` registra trabalho Native sobre o próprio método (achados, análises e correções),
conforme `docs/WORK_MODEL.md`. `_tl-orc/` aqui não é conteúdo de consumidor.

## Evidências

`_tl-orc/project/evidence/`.
