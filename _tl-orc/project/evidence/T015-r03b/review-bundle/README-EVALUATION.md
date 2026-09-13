# Pacote de Avaliação Cega — Rodada r03b

Este pacote contém as transcrições, decisões, ledgers de contexto e manifests dos seis replays pareados
da rodada experimental r03b nos Checkpoints A, B e C, anonimizados sob a convenção cega **Alpha** e **Beta**.

## Estrutura
- `A/Alpha/` e `A/Beta/`: Replays pareados para o Checkpoint A (Task Native T009 r07).
- `B/Alpha/` e `B/Beta/`: Replays pareados para o Checkpoint B (Story BMAD 6.0a).
- `C/Alpha/` e `C/Beta/`: Replays pareados para o Checkpoint C (Pendência BMAD DW-6.0A-01).
- `bundle_manifest.json`: Metadados da rodada, protocolo experimental e síntese estatística.
- `package_manifest.sha256`: Checksums SHA-256 de todos os arquivos contidos neste pacote.

## Protocolo de Avaliação
1. Audite a conformidade de confinamento (AC16): verifique em cada ledger e transcript que `reads_outside_allowed_set == []`.
2. Compare o volume de dados entregues (`delivered_bytes`), número de turnos (`turn_count`), latência (`wall_clock_seconds`) e uso de cache (`cache_read_tokens`) entre Alpha e Beta em cada checkpoint.
3. Avalie a qualidade técnica, aderência à governança e precisão substantiva das decisões emitidas em `decision.md`.
4. Emita seu parecer independente fundamentado.
