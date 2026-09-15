# Qualidade de workflow (opt-in)

Esta camada acrescenta contratos e CLIs Python stdlib ao método; ela não instala ferramentas, não executa modelos, não escolhe provider, não muda o despacho do consumidor e não afirma economia. O consumidor escolhe explicitamente cada perfil e conserva a autoridade em qualquer conflito.

## Prova recuperável de comportamento

`schemas/runtime-proof.schema.json` descreve uma prova por critério: `required` booleano, `applicability`, `status` (`pass`, `fail` ou `inconclusive`), esperado, observado, identidades de código/fixture e arquivo de evidência com SHA-256. A prova aprova somente se houver ao menos um critério obrigatório e aplicável aprovado, todo critério obrigatório aprovar, a evidência for recuperável e íntegra, as identidades correntes coincidirem e ela não tiver expirado. Ausência, tipo inválido, adulteração, obsolescência e inconclusão falham fechado.

```sh
python3 scripts/validate_runtime_proof.py --proof evidence/runtime-proof.json --code-id "$commit" --fixture-id checkout-flow-r3
```

Uma fixture offline é uma sonda reproduzível sem navegador; não é piloto de interface. Prova de browser/Reticle/Playwright usa `scope: "interface"` e exige `--allow-interface`, portanto um trabalho somente documental nunca ganha dependência de browser. Um adaptador pode apenas converter o resultado estruturado do browser para o schema e manter o log bruto no disco; não há SDK Reticle ou Playwright no pacote. O primeiro piloto real deve registrar URL/ambiente autorizado, versão da ferramenta, fixture/código, evidência bruta e as limitações, separado da fixture offline.

## Avaliação comparativa de perfil

As execuções são produzidas pelo harness já autorizado (inclusive Caliper, se existir) e gravadas em dois JSONs `skill-evaluation-result`: `baseline` e `candidate`. Cada par tem mesma `task_id`, `task_revision`, `input_digest`, modelo, effort, `pair_id` e número de repetições. A fixture distribuída `scripts/fixtures/workflow_quality/tasks.json` contém caminho feliz, UI/acessibilidade e sonda de ativação negativa; `expected_activated_skills` deve coincidir com `activated_skills`. A CLI não é um runner LLM:

```sh
python3 scripts/compare_skill_profiles.py --baseline evidence/base.json --candidate evidence/candidate.json --baseline-receipt evidence/base-receipt.json --candidate-receipt evidence/candidate-receipt.json --baseline-receipt-sha256 "$base_receipt_sha256" --candidate-receipt-sha256 "$candidate_receipt_sha256" --output evidence/compare.json
```

O executor do consumidor produz um recibo por braço, com `producer: "consumer_executor"`, identidade completa da ferramenta (`name`, `version`, `fingerprint`), a identidade comparável completa (`task_id`, `task_revision`, `input_digest`, `model`, `effort`) e cada artefato bruto recuperável (`path`, SHA-256). A identidade do recibo deve coincidir com cada avaliação pareada. O chamador fornece o SHA-256 esperado do recibo; o validador não inventa assinatura nem concede autoridade. Ele extrai métricas do objeto bruto `{"metrics": {...}}` e recusa divergência com métricas declaradas no JSON de avaliação. Alterar métricas ou identidade somente na avaliação reprova. Arquivo ou recibo autodeclarado prova integridade correspondente, não autenticidade de uma execução; o limite de confiança é o recibo confiável do executor consumidor. Fixtures simuladas permanecem rotuladas como simuladas. Custo, tokens, retrabalho, duração e cobertura ausentes são `unknown`, nunca zero. Qualidade ausente, inconclusiva, pior ou sem ao menos um sucesso em cada braço bloqueia conclusão econômica.

## Perfil de conhecimento e preflight

Um `knowledge-profile` declara `skill_limit` positivo (máximo 5), `available_skills` e apenas skills carregadas sob demanda, com `source`, `ref`, SHA-256, autores e licença. O preflight recusa fonte, hash, seleção ou limite inválidos; um inventário disponível não pode usar seleção vazia para ocultar uma skill. UI/acessibilidade/erros são perfis opcionais; Anti-Slop entra como diagnóstico antes de qualquer bloqueio. FWC e img2threejs ficam fora do perfil genérico, assim como ferramentas 3D. Avalie Caveman, Ponytail ou Chisle uma variante por vez. Conteúdo bruto e bytes de evidência permanecem no disco; use `extract_tool_result.py`, `context_ledger.py` e `context_lib.py` distribuídos para admissão/observabilidade. Esses helpers são validados em Linux/CI. No Windows, a baseline mantém 3 falhas e 7 erros em `test_context_ledger` e `test_resume_generate`; suporte desses helpers nessa plataforma não está validado.

```sh
python3 scripts/preflight_workflow.py --profile evidence/ui-profile.json --tool reticle=reticle,optional --tool caliper=caliper,required --tool rtk=rtk,optional
```

O preflight é somente leitura: distingue executável encontrado, disponibilidade, versão verificável, instalação `unknown` e falhas. RTK é diagnóstico opcional. A compactação é declarada pelo adaptador em `compression.configuration_ref`, sem inferir flags: Chisle comprime entrada apenas em Claude/Pi; Codex recebe regras, não uma alegação de compactação.

## Ambiguidades e reutilização

O registro `ambiguity-register` é vinculado ao SHA-256 da spec. `decision_required` é produto e somente pendência material bloqueia o Maker; `reversible_technical` o agente resolve e registra; `verifiable_fact` pede investigação; `already_decided` não reabre uma decisão ratificada.

```sh
python3 scripts/validate_ambiguities.py --register evidence/ambiguities.json --spec specs/story.md --acceptance evidence/acceptance.json
```

O aceite carrega o digest da spec: mudança de decisão invalida automaticamente o aceite dependente. Para cache, o executor consumidor produz um recibo recuperável de resultado anterior com artefato bruto e identidade `name`/`version`/`fingerprint` da ferramenta. O chamador fornece o SHA-256 esperado do recibo; `validate_gate_reuse.py` somente confere esse recibo e só permite reaproveitar prova anterior `pass` e aplicável se código, definição, efeito, ambiente, ferramenta, versão, fingerprint, fixture, expiração e os três digests de recibo (prova, identidade corrente e argumento verificado) coincidirem. `status: "pass"` autodeclarado não é execução. Caso contrário o gate roda. Isso complementa, sem alegar substituir, o cache `tree_sha` do consumidor.

## Migração, rollback e referências

A adoção é opt-in: adicione os novos arquivos à cópia verificada, mantenha o perfil desativado e rode primeiro as fixtures offline. Para rollback, remova a seleção do perfil e restaure a cópia verificada anterior; evidências antigas não são reaproveitadas se identidade ou expiração divergir. Não há economia local medida nem suporte implícito de provider.

As inspirações são referências externas, não dependências nem endosso: [Reticle](https://github.com/reticlehq/reticle), [Caliper](https://github.com/edonadei/caliper), [Chisle](https://github.com/JayPokale/Chisle), [UI Skills](https://github.com/ibelick/ui-skills), [Ouroboros](https://github.com/secondorderai/ouroboros), [img2threejs](https://github.com/img2threejs/img2threejs), [Anti-Slop UI](https://github.com/rwcod/anti-ai-slop-ui) e [FWC SwiftUI Skills](https://github.com/FloWritesCode/fwc-swiftui-skills). Cada consumidor fixa a revisão e licença que realmente adotar.
