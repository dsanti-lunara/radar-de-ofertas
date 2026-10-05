# Shopee Capability Matrix

[Relatório vigente](BROWSER_RECON_COMPLETION.md), [API oficial](API_DOCUMENTATION_FINDINGS.md). Documentado não significa disponível para a conta ou testado via API.

| Capability | Contrato oficial | Evidência browser | Recomendação/gate |
|---|---|---|---|
| Product discovery/offers | productOfferV2 | Cards/detalhe no portal | API para recorrência; entitlement/live pendentes |
| Detalhe oferta | productOfferV2 shopId/itemId; getItemFeedData | Produto/comissão por canal | Sem inferir SKU/estoque/frete checkout |
| Affiliate/brand offers | shopeeOfferV2 / shopOfferV2 | Tabelas observadas | API para recorrência; portal manual |
| Campanhas/exclusivas | API específica não confirmada | Lista/EMPTY | Manual; regras/adesão não auditadas |
| Short/affiliate link | generateShortLink mutation | Custom/padrão/avançado e destinos confirmados | API prioritária; portal manual; copy host não confirmado |
| Sub IDs | Até cinco subIds | Cinco posições/roundtrip; hífen rejeitado | Preservar posições; limites por campo pendentes |
| Conversion/validated report | conversionReport / validatedReport | Sem dados privados coletados | API planejável; execução autenticada pendente |
| Feed | listItemFeeds / getItemFeedData | Documentação lida | FULL/DELTA, columns JSON String, paginação própria |
| Captura site público | Contrato de captura ainda a completar | Destinos públicos, home/lista relâmpago/filtro beleza/cards e seletores candidatos observados | Candidato BROWSER_ASSISTED separado; estabilidade/fixtures/adapter pendentes; SHOPEE_PUBLIC_FINDINGS.md |

API da conta sem acesso: nenhuma capability API_SUPPORTED comprovada live. Não é NOT_SUPPORTED global.

Detalhe público apresentou Verifique para continuar após DOM inicial; após resolução humana, preço da opção 12L foi confirmado em E-SP-PUB-08; opção preta/checkout/recorrência não validados. Lista/filtros beleza e Casa e Cozinha funcionaram nesta visita, mas não aprovam revalidação automática do detalhe. E-SP-PUB-01..09 em SHOPEE_PUBLIC_FINDINGS.md.

Portal affiliate.shopee.com.br: happy path técnico não supera proteção recorrente. Evitar extensão para operações recorrentes; manual/diagnóstico e API são escopos diferentes. Site público não herda essa conclusão automaticamente; relato de ausência percebida de antibot não garante ausência real. Sem AUTO.
