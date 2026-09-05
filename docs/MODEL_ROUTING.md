# Evidência para seleção de modelo e effort

Revisão: `official-2026-09-05`. Conferência em 2026-09-05; próxima revisão sugerida em
2026-10-05, ou antes se mudar modelo, preço, harness ou metodologia. Este documento é evidência
consultável, **não uma lista de modelos autorizados**, nem uma tabela tier → modelo.
O Orquestrador entrega ao Classificador somente os cartões pertinentes, com seus IDs e ressalvas.
Não pesquisar estas fontes novamente a cada story nem enviar artigos/gráficos inteiros na chamada.

## Preços e capacidades de transporte

USD por milhão de tokens, API Standard de texto: entrada / leitura de cache / saída.
São referências de preço, não custos medidos de stories, nem a cobrança de assinaturas dos CLIs.

| ID da evidência | Modelo | Entrada / cache / saída | Fonte e validade |
| :--- | :--- | :--- | :--- |
| `price-luna` | GPT-5.6 Luna | 0,20 / 0,02 / 1,20 | [OpenAI Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), conferir novamente na revisão |
| `price-terra` | GPT-5.6 Terra | 2 / 0,20 / 12 | [OpenAI Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), conferir novamente na revisão |
| `price-sol` | GPT-5.6 Sol | 4 / 0,40 / 20 | [OpenAI Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol), promoção garantida pelo menos até 2026-11-21; depois revalidar, não adivinhar preço |
| `price-astra` | GPT-6 Astra | 10 / 1 / 50 | [OpenAI Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), conferir novamente na revisão |
| `price-sonnet` | Claude Sonnet 5 | 2 / 0,20 / 10 | [Anthropic preços](https://platform.claude.com/docs/en/about-claude/pricing), preço permanente; gráficos antigos usam 3/15 |
| `price-opus` | Claude Opus 5 | 5 / 0,50 / 25 | [Anthropic preços](https://platform.claude.com/docs/en/about-claude/pricing), conferir novamente na revisão |
| `price-flash` | Gemini 3.8 Flash | 0,75 / 0,075 / 3,75 | [Google preços](https://ai.google.dev/gemini-api/docs/pricing), até 2026-12-31; 1,50 / 0,15 / 7,50 a partir de 2027-01-01 |

- `transport-openai`: APIs GPT-5.6 oferecem none/low/medium/high/xhigh/max; Astra
  low/medium/high/xhigh/max. Nos modelos acima, entrada >272K muda a tarifa da requisição
  inteira; escrita de cache também custa. Consulte as páginas por modelo. CLI e API não são o
  mesmo transporte: `ultra` do harness não é um effort API simples e não está autorizado só por
  aparecer na interface. Confirme a combinação no harness e o custo de agentes adicionais.
- `transport-claude`: Sonnet 5 e Opus 5 oferecem low/medium/high/xhigh/max; effort afeta
  raciocínio, resposta e ferramentas, mas não é teto rígido de tokens. `xhigh` destina-se a trabalho
  prolongado. [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort).
- `transport-flash`: a API usa `gemini-3.8-flash` com low/medium/high; minimal é inválido.
  [Google modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).
  Variantes Agy com sufixo são IDs do harness, não IDs API. A lista local conferida em 2026-09-05
  oferece `gemini-3.8-flash-low`, `-medium`, `-high`; reconfirme antes de despachar.

## Cartões de evidência

Resultados de fornecedores são sinais iniciais, não avaliação local independente. Cada cartão
preserva o conjunto e suas condições: não combine linhas de publicações distintas numa liga única.
Pontos lidos visualmente sem tabela numérica são aproximações e não entram como valores exatos.

### `astra-coding` — terminal, engenharia e migrações

No lançamento do [Astra](https://openai.com/index/gpt-6-astra/), máximos em qualquer effort:
Terminal-Bench 4.0 Astra/Sol = 57,9/37,3%; DeepSWE v1.1 = 74,1/72,7%; FrontierCode
1.1 Extended = 64,5/60,6%; migrações internas = 63,9/42,7%. Terminal-Bench mostra custo
API estimado por tarefa cerca de 9% menor para Astra. Curvas inspecionadas não são sempre
monotônicas; máximo de score não identifica automaticamente o melhor effort. FrontierCode usa
mensagem de desenvolvimento adicional; os ambientes de avaliação diferem de produção.

### `astra-domain` — sinais específicos, não ranking de revisão

A mesma [publicação](https://openai.com/index/gpt-6-astra/) traz GeneBench Pro Astra/Sol
37,1/32,3%, ExploitBench 100/78,5% e OSWorld com latência **simulada**, aproximadamente
40/75 minutos por tarefa. Cyber foi avaliado sem salvaguardas de produção; não mede precisão de
Checker nem permite contornar recusas. GeneBench só informa trabalho de genômica. Não extrapolar
esses resultados para qualquer debate, revisão ou tempo real de CLI.

### `gpt56-coding` — capacidade dos modelos econômicos

A publicação [GPT-5.6](https://openai.com/pt-BR/index/gpt-5-6/) compara Sol/Terra/Luna:
Terminal-Bench **2.1** = 88,8/87,4/84,7%; DeepSWE v1.1 = 72,7/69,6/67,2%.
São máximos, não resultados de Luna medium. Isso justifica avaliar modelos econômicos também
em código, mas não presumir equivalência em todos os workloads. Não comparar 2.1 com 4.0.
A publicação apresenta preços de lançamento e notas de redução posteriores: usar preços atuais
por modelo. `ultra` coordena agentes, trocando mais tokens por paralelismo; não é economia gratuita.
Nos gráficos inspecionados de custo/latência do Terminal-Bench 2.1, Sol supera vários pontos Luna
em qualidade e tempo. Latência é simulada com velocidade Fast, custo com tarifa regular; não são
medições locais. A janela nominal também não prova recuperação fiel: MRCR v2 8-needle 256K–512K
mostra Sol/Terra/Luna 91,5/89,6/41,3%. Isso reforça manter o briefing de classificação curto,
sem confundir caber na janela com compreender todas as dependências.

### `sonnet-effort` — curvas e metodologia

O [Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) apresenta curvas por effort em
BrowseComp e OSWorld-Verified. No gráfico BrowseComp inspecionado, medium tem aproximadamente
71% e high 79%; custo tem eixo logarítmico e preços antigos 3/15. Não reutilizar o eixo em dólares
como tarifa atual 2/10. A correção de junho usa orçamento de 10M tokens, compactação e chamada
programática de ferramentas. É evidência de pesquisa agêntica, não medição de classificação JSON.

### `opus-effort` — custo por tentativa e saturação

O gráfico [Opus 5 / Frontier-Bench v0.1](https://www.anthropic.com/news/claude-opus-5)
inspecionado usa mini-SWE-agent/GKE e média de cinco tentativas; Opus 4.8 foi fallback em recusas.
A curva de Opus 5 chega ao pico antes do ponto final mais caro: não impor max por ser heavy.
Frontier-Bench não é FrontierCode. O fornecedor relata Fast aproximadamente 2,5× mais rápido
por 2× o preço; isso não é latência comparável entre todos os modelos.

### `flash-deepswe` — economia dependente do workload

No gráfico oficial [Gemini 3.8 Flash / DeepSWE v1.1](https://deepmind.google/models/gemini/flash/),
o eixo de custo por tarefa é **invertido**: direita significa menor custo. Flash aparece próximo
de 74% com custo baixo; a figura não identifica cada ponto por effort. Ela credita a Datacurve.
Não transformar proximidade visual em empate estatístico, inferir qual ponto é medium ou atribuir
a um modelo só seu ponto de menor effort. É um sinal favorável a Flash em engenharia longa,
não prova de melhor revisão de segurança nem de vitória universal sobre Sol/Terra/Luna.

## Aplicação aos papéis — inferências do método

1. Dimensione a **fase atual**, não apenas o tamanho da story. Debate arquitetural com publicação
   atômica, concorrência, permissões e recuperação exige raciocínio de mecanismo mesmo sem diff.
   Revisão exige busca de contraexemplos; execução de mudança mecânica pode exigir bem menos.
2. Primeiro satisfaça risco, ferramentas, contexto, orçamento autorizado, pins e piso de qualidade.
   Depois compare pares modelo/effort no mesmo harness; preserve a ordem de harnesses acordada.
   A cadeia pode custar mais que a alternativa global mais barata: só o usuário muda essa política.
3. Luna é candidato a tarefas delimitadas e classificação; Terra a integrações; Sonnet e Flash
   a raciocínio/engenharia de custo moderado; Sol, Opus e Astra a trabalho com maior necessidade
   de capacidade. São pontos de partida, **não restrições nem mappings por tier**. Um modelo
   maior com effort menor pode superar um menor em max, desde que haja fundamento para a tarefa.
4. Compare custo esperado de entrega aceita, incluindo classificação, revisão, ferramentas,
   falhas e retrabalho. Use observações locais pareadas quando existirem. Sem elas, mantenha
   `official_task_proxy`, `token_price_only` ou `unknown`; não invente probabilidade de sucesso,
   latência, estimativa monetária ou equivalência de qualidade. Dados ausentes não significam zero.
5. Esforço extra precisa de motivo concreto: ambiguidade, hipóteses concorrentes, prova difícil,
   risco de erro ou falha de capacidade observada. Não aumentar por quota, nem reduzir testes,
   independência ou salvaguardas para economizar. Recusa de segurança não é fallback de infraestrutura.

## Medir sem contaminar a seleção

Quando medições já estiverem autorizadas, registre por story/fase: par solicitado e efetivo,
revisões do briefing/catálogo/contrato, tokens de entrada não cacheados/cacheados e saída (incluindo
raciocínio conforme o provedor), chamadas, duração ponta a ponta, espera/infraestrutura,
aceite independente e retrabalho. Separe unidades e contadores para não cobrar tokens duas vezes.
Mantenha falhas na amostra; compare tarefas de risco e ferramentas semelhantes, com tamanho de
amostra e dispersão. Custo total da amostra / entregas aceitas é observável; com zero aceites,
não há custo finito por sucesso a relatar. Não estimar produção por uma única classificação.

Calibração futura exige casos separados dos usados para ajustar o prompt, com defeitos conhecidos
para medir falhas de detecção do Checker. Concordância dos classificadores e confiança declarada
não provam qualidade. Manter o piso de qualidade, portões e revisão independente precede otimizar
tokens. O pacote não coleta telemetria nem executa A/B, cache ou reclassificação em background.
