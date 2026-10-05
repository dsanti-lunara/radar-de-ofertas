# Specs de entrega V1

Divisão e fronteiras de testes confirmadas pelo usuário em 2026-10-02. Os SDDs, Decision Log, CONTEXT e ADRs continuam autoridade.

- [SPEC-00: entrega geral](00-delivery.md)
- [SPEC-01: fundação e domínio](01-foundation-domain.md)
- [SPEC-02: seleção de oportunidades](02-opportunity-selection.md)
- [SPEC-03: workflow e autorização](03-workflow-authorization.md)
- [SPEC-04: IA e conteúdo](04-ai-content.md)
- [SPEC-05: publicação e recuperação](05-publication-recovery.md)
- [SPEC-06: browser e marketplaces](06-browser-marketplaces.md)
- [SPEC-07: operação e homologação](07-operations-acceptance.md)

## Publicação

Tracker: `dsanti-lunara/radar-de-ofertas`. Label previsto: `ready-for-agent`. Nenhuma destas specs foi publicada nesta sessão: a consulta pelo conector funcionou, mas a criação foi bloqueada porque exige aprovação e a política da sessão é `never`; o CLI havia falhado por conexão de proxy.

Publicar uma issue por spec, com o conteúdo integral do arquivo e título `[SPEC-NN] <nome>`, após verificar novamente duplicações no tracker. Registrar aqui os links retornados. A proposta anterior de autorização/recuperação está incorporada em SPEC-03/SPEC-05 e não deve gerar publicação duplicada.

Esta etapa prepara specs. A decomposição em issues executáveis preserva RDR-001..RDR-134 e seus critérios, com gates/dependências explícitos; implementação, spikes e side effects não foram executados nem autorizados por esta publicação.
