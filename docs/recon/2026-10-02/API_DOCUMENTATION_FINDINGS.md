# Shopee Affiliate Open API — documentação oficial Brasil

Fontes lidas no Edge em 2026-10-02, host `affiliate.shopee.com.br`. Leitura autorizada como base de planejamento pelo usuário; **nenhuma chamada API autenticada executada**. Entitlement permanece ausente na conta. Exemplos de outros países presentes na documentação não são authority para hosts, identidade ou capacidades da conta Brasil.

## Transporte/autenticação

- Fonte: `/open_api/document?type=request_response`.
- Endpoint explícito: `https://open-api.affiliate.shopee.com.br/graphql`, POST, Content-Type `application/json`, mesmo endpoint para operações.
- Body: `query` String, `operationName` e `variables` opcionais; operationName obrigatório quando há múltiplas operações.
- HTTP 200 pode conter `errors` e `data`. Não considerar HTTP success como business success; rejeitar resultado parcial necessário ao contrato.
- Error: message, path, extensions.code e extensions.message; docs descrevem path String, formato live ainda não testado.
- Fonte auth: `/open_api/document?type=authentication`: assinatura SHA256 de AppID + Timestamp + Payload JSON exato + Secret, hex minúsculo; Authorization `SHA256 Credential=..., Timestamp=..., Signature=...` nos exemplos. Overview textual usa Credentials em um trecho: resolver no teste oficial, não improvisar variante.
- Timestamp diferença máxima 10 minutos. Relógio do node precisa estar sincronizado. Assinar bytes/JSON exatos enviados, não uma reserialização diferente.
- Não foi documentado token de sessão do marketplace ou OAuth refresh nesse fluxo. AppID/Secret provisionados pelo operador, no secret store aprovado, nunca no browser fixture/Git/log/prompt.

## Operações observadas

| Fonte `/open_api/list?type=` | Operação / retorno | Entradas / limites | Campos e implicações |
|---|---|---|---|
| `product_offer` | `productOfferV2` / ProductOfferConnectionV2 | shopId/itemId Int64, productCatId Int32, keyword, sortType, page, limit, isAMSOffer, isKeySeller; listType somente com matchId e não com demais inputs | nodes + pageInfo; shop/item/name/link/image, commissionRate/sellerCommissionRate/shopeeCommissionRate, commission, sales, priceMin/priceMax, categories/rating/discount/shopType/período |
| `shopee_offer` | `shopeeOfferV2` / ShopeeOfferConnectionV2! | keyword, sortType latest=1 ou highest commission=2, page, limit | commissionRate/image/offerLink/originalLink/name; offerType collection=1/category=2, respectivos IDs, período; pageInfo |
| `brand_offer` | **`shopOfferV2`** / ShopOfferConnectionV2 | shopId, keyword, shopType, isKeySeller, sortType, sellerCommCoveRatio, page, limit | commissionRate, shopId/name/type/rating, links/imagem/período, remainingBudget, sellerCommCoveRatio, bannerInfo. “Brand” no menu não é nome da query atual |
| `short_link` | mutation **`generateShortLink`** / ShortLinkResult! | originUrl String!, subIds [String] com cinco posições | shortLink String!; exemplo oficial confirma endpoint GraphQL Brasil. Não copiar/adaptar a sintaxe inválida de aspas do cURL literalmente; serializar JSON/GraphQL corretamente em implementação futura |
| `product_feed_offer` | `listItemFeeds` / ItemFeedListConnection! | feedMode FULL(default) ou DELTA | feeds: datafeedId/name/referenceId/description/totalCount/date/feedMode. FULL inicial; DELTA mudanças desde ontem, associar referenceId ao full |
| `product_feed_offer_detail` | `getItemFeedData` / ItemFeedDataConnection! | datafeedId String!, offset Int, limit Int máximo 500 | rows.columns String (JSON com colunas/valores), updateType NEW/UPDATE/DELETE apenas DELTA; pageInfo offset/limit/totalCount/hasMore. Não assumir que columns já é objeto normalizado |
| `conversion_report` | `conversionReport` / ConversionReportConnection! | purchase/complete time start/end Unix, shop/id/type, conversionId, orderId, productName/id, category levels, orderStatus, buyerType, attributionType, device, limit, fraudStatus, scrollId, campaignPartnerName/type | conversão → orders → items, utmContent = Sub IDs; comissão Shopee capped/seller/total/net, MCN, modelos/promoções/attribution/fraud. Distinguir estimado, capped, gross e net |
| `validation_report` | **`validatedReport`** / ValidatedReportConnection! | validationId Int64 (Billing Information), limit, scrollId | conversão/orders/items e comissões validadas, utmContent, MCN, qty ajustada, refundAmount para caso documentado digital/partial refund; não confundir com conversionReport ou pagamento recebido |

Paginação oferta V2: pageInfo page/limit/hasNextPage. Paginação feed: offset/hasMore. Paginação relatório: scrollId/hasNextPage. Não usar algoritmo único baseado em scroll para todas as capabilities.

## Semântica relevante para implementação futura

### ProductOfferV2

Query por shopId/itemId está documentada; pode sustentar reconsulta da **oferta**. Não equivale a detalhe de SKU completo, estoque, frete/localização ou checkout. priceMin/Max representa range; não gerar mensagem de kit/variante pelo menor preço sem evidência da variante correta. commissionRate é **maximum commission rate**, String decimal: `0.0123` equivale a 1.23%; preço/commission são strings monetárias em moeda local. IA não calcula nem converte scores.

sortType: relevância=1 só em keyword; vendas=2; price desc=3; asc=4; comissão=5. listType/ matchId mutuamente exclusivos dos demais filtros conforme texto oficial; valores highest commission=1 e collection=6 marcados To Be Removed. Campos `price`, app/web/new/existing commission rates também marcados To Be Removed. Preferir campos V2 atuais, sem eliminar checks só para compatibilizar versão antiga.

Int64 em shop/item/conversion não deve perder precisão no transporte TypeScript/JSON. Definir contrato decimal/string ou estratégia segura ao gerar tipos, antes de implementação.

### ShopOfferV2

remainingBudget enums documentados: 0 Unlimited; 3 acima de 50%; 2 abaixo de 50%; 1 abaixo de 30%. São buckets de risco, não valores monetários; não confundir 0 com orçamento esgotado. Oferta pode terminar antes do período se orçamento acabar.

sellerCommCoveRatio tem inconsistência no exemplo da documentação entre `0.123` e referência 1.23%; não usar exemplo como algoritmo. Fixar unidade pelo contrato/fixture oficial após acesso, mantendo evidência do texto.

### Relatórios

conversionReport: order statuses UNPAID/PENDING/COMPLETED/CANCELLED; buyer NEW/EXISTING; device APP/WEB; fraud UNVERIFIED/VERIFIED/FRAUD; campos checkoutId/conversionStatus/algumas comissões marcados To Be Removed. Não tratar pedidos pendentes/estimativas como receita validada.

validatedReport exige validationId encontrado em Billing Information. Esta investigação não coletou dados financeiros privados da conta. Tipo mcnContractId difere nos documentos: Int64 em conversion, String em validated; normalização precisa preservar origem e evitar cast silencioso.

ModelId é identidade de variante; promotionId de bundle/add-on. Attribution/channel/utmContent são evidência para métricas, não instruções para IA. Guardar snapshot/version/source/observed_at, distinguir conversão, validação e pagamento.

## Rate/paginação/recovery

Overview oficial: 8000 calls/hora; confirmar scope por app/conta e resposta real após acesso. Não operar no teto sem orçamento conservador compartilhado; não conflitar discovery/revalidação/link/relatórios.

Relatórios: até 500 registros/página; scrollid válido uma vez e por 30 segundos; consulta sem scrollid exige intervalo maior que 30s. Janela de consulta de conversões: três meses recentes. Retomada de cursor vencido exige novo checkpoint/coleta deduplicada, não reutilizar cursor cego nem gerar chamadas em loop.

Feeds documentam DELTA “desde ontem”; downtime maior requer política de ressincronização FULL. Performance/carga inicial e limite operacional devem ser planejados por issue; não executar crawling/carga massiva nesta task.

generateShortLink é mutation; docs não mostraram chave idempotente nem garantia de mesmo resultado em repetição. Core precisa registrar intenção/attempt/resultado e evitar resubmissão automática após resultado desconhecido. Retorno de provider nunca permite IA gerar/editar affiliate_url.

## Erros documentados

| Code | Semântica | Orientação para issue |
|---|---|---|
| 10000 | System error | Retry bounded após classificar, sem repetir mutation desconhecida cegamente |
| 10010 | Request parsing, tipo/syntax/API inexistente | Falha de contrato, não retry infinito |
| 10020 | Signature/timestamp/credential/auth type/disabled app, conforme mensagem | Uma só família numérica tem várias causas; preservar reason sanitizado, fail closed/ação humana quando necessário |
| 10030 | Rate limit | Budget/backoff; não retry imediato |
| 10031..10034 | Access deny, invalid affiliate id, frozen, black list | Bloqueio/ação humana, não contornar |
| 10035 | Sem acesso à plataforma API | Entitlement gate; [formulário oficial de contato](https://help.shopee.com.br/portal/webform/bbce78695c364ba18c9cbceb74ec9091), não submetido pelo agente |
| 11000/11001/11002 | Business / params / bind account | Classificar causa; não aceitar sucesso parcial nem ignorar schema |

## Gates

Planejamento de API com esses contratos autorizado. Testes Fake/contract podem ser planejados sem secrets. API_SUPPORTED operacional, execução real e aprovação final exigem conta liberada, secret store, chamada oficial autenticada, schemas/limites/errors reais sanitizados e cobertura de recuperação/idempotência. Sem API live neste pacote.
