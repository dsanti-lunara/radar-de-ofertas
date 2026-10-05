# Specs de entrega V1

Specs e fronteiras aprovados em 2026-10-02, reconciliados com o recon em 2026-10-03 por autorização do operador. SDDs, Decision Log, CONTEXT e ADRs continuam autoridade.

- [SPEC-00: entrega geral](00-delivery.md)
- [SPEC-01: fundação e domínio](01-foundation-domain.md)
- [SPEC-02: seleção de oportunidades](02-opportunity-selection.md)
- [SPEC-03: workflow e autorização](03-workflow-authorization.md)
- [SPEC-04: IA e conteúdo](04-ai-content.md)
- [SPEC-05: publicação e recuperação](05-publication-recovery.md)
- [SPEC-06: browser e marketplaces](06-browser-marketplaces.md)
- [SPEC-07: operação e homologação](07-operations-acceptance.md)

## Tracker e rastreabilidade

Decomposição publicada: 67 tickets em [dsanti-lunara/radar-de-ofertas](https://github.com/dsanti-lunara/radar-de-ofertas/issues), #1–#67. IDs RDR-001..134 continuam canônicos; números GitHub/TKT são diferentes dos RDR. Links, corpos locais e manifesto em `.scratch/radar-v1/PUBLISHED.md`, `issues/` e `publication-plan.json`.

Specs permanecem arquivos locais de referência dos tickets. Esta revisão atualiza tickets existentes; não cria oito issues de specs duplicadas. A proposta anterior de autorização/recuperação está incorporada em SPEC-03/05.

## Revisão pós-recon

GROUP/identidade/preflight, tracking ML e três rotas Shopee foram incorporados nas SPEC-00/01/05/06/07. SPEC-02/03/04 preservam arquitetura e escopo. Investigação finalizada e 14 checks offline não aprovam API da conta, adapters, Chrome/VM ou produção. Entitlement Shopee exige operador; envios permanecem ASSISTED/sandbox com autorização específica e AUTO não é ativado.

Evidências em `docs/recon/2026-10-02/`; avaliação em `SPEC_ISSUE_REVIEW.md` e registro da aplicação em `UPDATE_HANDOFF.md` nesse diretório. Nenhuma implementação ou side effect comercial é autorizado pela publicação desta revisão.
