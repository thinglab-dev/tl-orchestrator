# Spec 6.0a (Recorte Documental Adaptado)

## §2. Dependências e gates

**Dependencies:**
- Nenhuma

**Gates de evidência:** os das dependências e dos ACs.

Esta spec não autoriza efeitos em clientes nem ensaios financeiros sem G5. As dependências do engine são as de epics.md; gates humanos têm stories âncora, quando aplicável.

G1/G2/G4/G6 são evidências escopadas por capability. A story produtora mede a prova como saída;
as consumidoras exigem a parte já demonstrada. G3, exceção de persistência e emenda de PII não
são flags entendidas pelo engine: dependem de ratificação nas stories de decisão. Nunca marcar
gate humano done por teste verde. Conformance de dois binários é saída de 6.14, sem exigir esse
resultado futuro para escrever o contrato ou seus primeiros codecs.

## §3. Critérios de aceite

1. **AC01.** Configuração explícita distingue subsistemas habilitados; Bling só é obrigatório quando seu observer/executor estiver habilitado. Configuração atual Bling mantém comportamento.
2. **AC02.** Registrar lifecycle de subsistemas do control plane com startup/stop/drain e falha de configuração antes de efeitos; handlers são ligados pelas stories 6.0b–d.
3. **AC03.** Teste entra por NewFromConfig com origem MK-Auth e sem Bling; não cria conexão fake nem desativa isolamento.
4. **AC04.** Nenhum servidor é iniciado implicitamente em endereço default de produção; validar endereços e material público/privado por função.

## §5. Verificação

Cenários: S18, S19. Mapear cada AC a entrada/ação/esperado/observado no dev report.
**Sonda contrafactual:** Remover a precondição crítica do AC01 ou adulterar seu insumo deve tornar vermelho o teste do consumidor; restaurar e observar verde.
Confirmar mutação no caminho real, observar vermelho e restaurar verde. Fixtures devem ser
sintéticas. Não usar mock para comprovar engine, grant, endpoint PSP ou documento visual real.
Testes Go ficam sob internal e são descobertos por go test ./.... Live usa build tag explícita
e prova de seleção; não introduzir t.Skip no gate determinístico da Lynvia. C2.0b é dona do Makefile/gate determinístico do conector hoje ausente; C4.4 integra o piloto financeiro. Roteiros isolados em test/
não bastam. G5 precede todo efeito de laboratório; nenhuma operação externa foi feita nesta revisão.

## §6. Limites e registro R2

Uma story implementa somente seu módulo; fonte canônica em protocol/ é exceção documental/IDL
com dono Lynvia, sem import entre módulos. Addon continua opcional e Go independente de PHP.
As perguntas pendentes têm dono/experimento no documento transversal e nas decisões propostas.
Não executar DDL MariaDB próprio antes de C2.0/C2.0a nem persistir PII real antes da emenda ratificada.

Esta R2 incorpora os achados aplicáveis listados na resposta à revisão. O estado acima é planejamento;
nenhum AC financeiro foi declarado implementado. O fechamento do mecanismo exige suas peças no
mechanisms.yaml, incluindo consumidores; o histórico do módulo também foi coberto sem mudar seus status.
