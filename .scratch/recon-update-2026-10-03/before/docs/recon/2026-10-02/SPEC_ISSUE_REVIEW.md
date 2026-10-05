# Avaliação do recon para revisão de specs e issues

Data de referência: 2026-10-02, America/Sao_Paulo; investigação atravessou 2026-10-03 UTC.

**Parecer: o pacote permite revisar planejamento e contratos agora. Não aprova adapters, API da conta, produção ou AUTO.** Esta entrega é uma avaliação/proposta; não altera os SDDs, os specs ou o tracker. A decisão de usar grupos já está registrada no recon; as definições técnicas propostas abaixo ainda precisam ser incorporadas explicitamente aos contratos.

## Fontes e verificações

- Autoridade: SDD Master, Decision Log, CONTEXT, ADR 0001, Data Contracts, Browser Bridge, Publishing, QA Matrix, Browser Reconnaissance e Shopee Capability Report.
- Evidência vigente: [BROWSER_RECON_COMPLETION](BROWSER_RECON_COMPLETION.md), matrizes/mapas ML/SP/WA, [API_DOCUMENTATION_FINDINGS](API_DOCUMENTATION_FINDINGS.md), [SHOPEE_PUBLIC_FINDINGS](SHOPEE_PUBLIC_FINDINGS.md), [DISCOVERY_URL_GUIDE](DISCOVERY_URL_GUIDE.md), fixtures e registry candidatos.
- GitHub consultado: `dsanti-lunara/radar-de-ofertas`, 67 tickets abertos, #1–#67. Corpos atuais conferidos diretamente para #39, #47, #48, #50 e #51; demais propostas usam os artefatos locais publicados de `.scratch/radar-v1` e o inventário remoto de títulos. Antes de editar, reler cada corpo e seus blockers no tracker.
- Verificadores executados novamente: `verify_recon_fixtures.py`, **6 PASS**; `verify_followup_evidence.py`, **8 PASS**. Sem rede/browser nesses testes.
- Nenhum teste de produto, API autenticada, SAFE_LIVE de adapter, envio, migration ou configuração operacional foi executado nesta avaliação.

## Achados que mudam o planejamento

| Tema | Evidência | Consequência |
|---|---|---|
| WhatsApp Groups | Decisão expressa do operador; E-WA-01..06; um envio técnico autorizado | Formalizar GROUP e capability de grupo; retirar Channels do escopo V1 correspondente. Preservar allowlist, marca, sandbox e ASSISTED. |
| Identidade WhatsApp | Não há ID persistente de destino comprovado; nome admite homônimos | Não aceitar nome ou message-id como group-id. Gate de identidade/pareamento e reverificação precisa de contrato e prova antes do envio. |
| Resultado WhatsApp | Bubble/marker e `Enviada`; grupo com um membro, mensagem temporária de sete dias | Não prometer entrega/leitura. Dedupe, receipt e reconciliação persistem independentemente da presença posterior do bubble. |
| Shopee API | Oito operações oficiais documentadas; conta sem entitlement | Planejar contratos/Fake agora; acesso e execução autenticada continuam bloqueios próprios. Ausência de acesso não equivale a NOT_SUPPORTED. |
| Portal Shopee | Proteção recorrente observada, relato de CAPTCHAs manuais | Portal manual/diagnóstico. Não implementar fallback operacional por extensão para contornar indisponibilidade da API. |
| Shopee pública | Listas/filtros observados; detalhe entrou em CHALLENGE; retomada humana confirmou preço apenas da opção 12L | Separar lista, detalhe e variante. Captura assistida é candidata; não garante revalidação automática. Sem dado atual verificável, bloquear publicação. |
| ML tracking | E-ML-05: minúsculas/números, limite 30; contrato exemplifica `RB_TG_OFFER` | Resolver mapeamento do TrackingContext para etiqueta externa, com unicidade e auditoria; não truncar/normalizar silenciosamente. |
| ML geração/resultado | E-ML-08..13: efeito em Minhas recomendações, landing social e resultado anterior persistindo após erro | Geração é side effect; correlacionar tentativa e resultado. Validar o produto destacado e contexto, não apenas host/path ou uma recomendação qualquer. |

## Revisão proposta dos contratos e specs

1. **SDDs 00/04/07/09, Decision Log, CONTEXT, Error Catalog, QA e roteiro de recon:** refletir Groups. Proposta de nome: `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua plataforma, `PublishingDestination.destination_type=GROUP` descreve destino. Definir identidade/pareamento, validade e invalidação do vínculo, preflight e receipt. Não preencher `external_id` com um valor inferido de storage, nome ou message-id. Se a identidade segura não for demonstrável, bloquear somente envio WA e registrar CAPABILITY_CONFLICT.
2. **Data Contracts e Publishing:** manter TrackingContext interno separado de etiqueta ML/Sub IDs externos. Etiqueta ML alfanumérica minúscula até 30, com mapeamento auditável sem colisão e configuração humana de etiquetas. Shopee preserva até cinco posições; limites de comprimento ainda não comprovados. Guardar retorno literal do provider; IA não altera links.
3. **Browser Bridge e Shopee Capability Report:** distinguir API oficial, portal manual/diagnóstico e site público assistido candidato. Não generalizar READY para um host inteiro. Definir suspensão em CHALLENGE, retomada com contexto revalidado e circuit breaker; thresholds não devem ser inventados pelo implementador.
4. **SPEC-00:** atualizar estado dos spikes e Slice 4 para grupo sandbox. Recon funcional finalizado não significa spike/aceite integral concluído; documentação API permite trabalho offline independentemente do entitlement.
5. **SPEC-06:** principal revisão. Adicionar contratos e AC específicos de ML, Shopee por superfície e WA Groups. Separar aceites offline, SAFE_LIVE Chrome/VM, API autenticada e SIDE_EFFECT sandbox. Os oito métodos documentados não tornam relatórios/feeds/analytics automaticamente obrigatórios na V1; incorporar apenas o necessário aos fluxos já aprovados.
6. **SPEC-05:** identidade de destino, serializer/hash determinísticos, receipt limitado à evidência disponível, dedupe persistente, unknown result e restore. Preparar/injetar mensagem continua separado de autorização para enviar.
7. **SPEC-01 e SPEC-07:** impacto restrito ao contrato de destino e às suas fronteiras de aceitação/retention/VM. Não reabrir foundation nem ampliar analytics. SPEC-02/03/04 não precisam de mudança arquitetural; atualizar referências somente quando afetadas.

`docs/specs/README.md` está desatualizado quanto à decomposição: tickets já foram publicados, embora os specs não apareçam como issues próprias no inventário consultado. Atualizar rastreabilidade para #1–#67; não criar specs ou tickets duplicados automaticamente. Os corpos consultados também conservam “publicação ainda pendente”, apesar de existirem no tracker.

## Mapa de issues e critérios propostos

Números abaixo são GitHub/TKT; RDR permanece o identificador canônico original.

| Tickets | RDR / escopo | Alteração proposta |
|---|---|---|
| #36, #38, #39 | RDR-076/124/125, separados ML/SP/WA | Consumir o pacote existente; renomear #39 para Groups; registrar evidência e gaps por etapa. Não refazer recon completo nem declarar auth/recovery/Chrome comprovados. Conferir AC antes de fechar. |
| #37 | RDR-077 | Documentação concluída, acesso/live pendentes. Separar entregável documental de validação da conta; ação humana de entitlement. Recomendar `needs-info` para a fronteira que exige acesso. |
| #40–#42 | RDR-078..086 | Preservar Foundation MV3/Bridge; explicitar CHALLENGE, ausência/ambiguidade, versão de contrato, nonce, hosts e persistência/recovery. |
| #20, #44–#46 | RDR-070 e RDR-090..094 | Tracking externo ML, efeitos da geração, short/full/social landing, contexto catálogo/anúncio, erro com resultado stale e ausência de barra. |
| #47 | RDR-095/096 | Contratos/Fake V2 e normalização podem ser planejados sem segredo; runtime/live requer #37. Não classificar falta de entitlement como impossibilidade global. |
| #48 | RDR-097/101 | `generateShortLink(originUrl, subIds)` é mutation; retorno literal, posições, contexto/redirect e estado ambíguo. Retirar promessa automática de fallback browser. |
| #49 | RDR-098/099 | Captura pública assistida: campanha vigente, listas/filtros e detalhe/variante com gates separados. Portal fica diagnóstico/manual. Fixtures públicas completas e negativos ainda faltam. |
| #50 | RDR-100 | Reespecificar como suporte/validação de link obtido manualmente, se essa rota for escolhida, ou retirar do caminho operacional. Não manter o objetivo atual de geração recorrente por extensão no portal. Preservar RDR-100 e histórico. |
| #51 | RDR-102 | Atualizar combinação de rotas e blockers: o OR atual `47+48 OU 49+50` pressupõe fallback browser que o estudo desaconselha. Captura pública + link API é combinação possível; rota manual depende de contrato próprio. Nenhuma é aprovada sem revalidação e aceite. |
| #52 | RDR-103..107/109 | GROUP, identidade/pareamento, homônimos, multiline, preview/hash, seletor ausente/duplicado e zero envio. |
| #53–#55 | RDR-108/110/111 | ASSISTED em grupo cadastrado; aprovação da publicação, preflight imediato, zero clique nos negativos, receipt/unknown result, sandbox e homologação real distintos. |
| #24, #58, #62–#67 | Unknown result, retenção e homologação | Acrescentar desaparecimento de mensagem temporária, crash/reload/reconnect/MV3/restore, dedupe persistente e gates Chrome/VM/soak. Manter GRILL-002/003. |

Para cada atualização, revisar objetivo, in/out of scope, contratos, AC, testes e dependências conjuntamente; um apêndice isolado não resolve objetivos contraditórios. Sincronizar corpo remoto, arquivo local, README/PUBLISHED, manifesto de publicação e blockers nativos quando houver mudança de dependência. Preservar IDs e AC ainda aplicáveis.

Em particular, #48 hoje depende de #47. Para admitir captura pública/manual + geração API, verificar se #47 é realmente requisito da geração de link ou apenas da rota de discovery; explicitar a dependência de Opportunity/contexto e do gate API de link. Não retirar #37 do caminho live para liberar contratos offline: separar fronteiras e seus gates, preservando o bloqueio da execução autenticada.

## Testes necessários nos próximos tickets

- **ML:** etiqueta inválida/overflow/colisão; gerador e barra no produto correto; social landing com produto destacado errado; erro da tentativa atual junto a resultado stale; link literal; recuperação sem repetir side effect cegamente.
- **Shopee API:** HTTP 200 com errors/data parcial; precisão Int64 no TypeScript; Decimal para preço/comissão; priceMin/Max não tratado como SKU escolhido; assinatura dos bytes exatos; família 10020 classificada pelo reason, 10030/backoff e 10035/entitlement. Paginação por método; timeout da mutation sem nova geração automática indiscriminada.
- **Shopee pública:** loading diferente de EMPTY; mudança de campanha; card/detalhe/variante divergentes; CHALLENGE após render inicial; resolução humana exige revalidação; dado antigo/cache não autoriza publicação.
- **WA:** grupos homônimos e troca de contexto após preview; serializer canônico para blocos/linhas; hash divergente; Send ausente/duplicado; marker/status ausentes; crash após envio antes de commit; reconnect/reload; desaparecimento de bubble; dedupe e restore sem reenvio automático.

Testes Fake/fixture e negativos vêm primeiro. SAFE_LIVE e SIDE_EFFECT não são autorizados por esta avaliação. Não há nova autorização para gerar links ou enviar mensagens.

## Ajustes de integridade do pacote de evidência

O pacote distingue corretamente observação, relato humano e gate futuro, mas requer três ajustes antes de servir como checklist de conclusão:

1. Sincronizar resumos que ainda dizem “ofertas relâmpago não investigadas” ou “preço não confirmado” com E-SP-PUB-01..09. Histórico continua preservado: a opção 12L teve preço confirmado após resolução humana; a opção preta continua inconclusiva, assim como checkout e estabilidade recorrente.
2. VALIDATION e o consolidado descrevem simulações negativas de marker/status ausentes. `verify_followup_evidence.py` verifica a projeção positiva de marker/status; não contém casos mutados desses campos nem implementa classificação unknown/retry. Corrigir a alegação de cobertura ou adicionar verificações de artefato adequadas; manter o teste de produção exigido nos tickets. Os 14 PASS não provam essa propriedade.
3. O registry ainda é candidato e os fallbacks não foram exercitados. Fixtures incluem fragmentos e projeções semânticas, não páginas completas. Não promovê-los a seletores certificados ou fixture HTTP real da API.

## Ordem recomendada e blockers

1. Corrigir coerência documental Groups/tracking/rotas Shopee e alegações de cobertura; registrar decisões técnicas sem alterar a stack.
2. Revisar SPEC-00/01/05/06/07 e os tickets existentes com rastreabilidade por evidência. Definir rota manual, se desejada, antes de atualizar #50/#51 e o grafo de dependências.
3. Avançar apenas a fronteira offline autorizada de contratos/Fake/fixtures e fundamentos do Bridge; provisioning da API é tarefa humana independente. Nenhuma implementação começa por esta avaliação.
4. Aceitar adapters com negativos e recovery; depois SAFE_LIVE Chrome dedicado/VM, API autenticada quando disponível e SIDE_EFFECT sandbox especificamente autorizado.
5. Homologar persistência/segurança/reboot/soak. Produção continua NO-GO e AUTO não é promovido.

Blockers objetivos: entitlement/segredo Shopee e ambiguidade documental de auth a resolver no spike oficial; contrato de tracking ML; identidade/reverificação do grupo; rota Shopee e limites ainda não observados; fixtures/adapter/recovery; Chrome/VM e tempo real de soak. Eles bloqueiam suas partes, não o planejamento independente ou a fundação já especificada.

## Entrega desta avaliação

Único arquivo novo: este relatório. Sem edição de specs, SDDs, issues, labels, dependências, código, migrations ou configuração runtime. Alterações paralelas preexistentes foram preservadas. A consulta ao tracker e os 14 testes offline foram executados; testes live e aceites de produto ficaram fora do escopo. As mudanças de contrato acima são propostas explícitas, não contratos já publicados.
