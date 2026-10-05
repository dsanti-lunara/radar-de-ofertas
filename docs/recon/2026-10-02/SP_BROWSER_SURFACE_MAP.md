# Shopee Browser Surface Map

Documento vigente: [avaliação consolidada](BROWSER_RECON_COMPLETION.md). Portal e site público são superfícies distintas.

Complemento E-SP-PUB-06/07: Casa e Cozinha categoryId=20 observada; detalhe público da lixeira transitou do DOM de produto para heading Verifique para continuar. CHALLENGE também existe no host público. [Evidências](SHOPEE_PUBLIC_FINDINGS.md), [URLs](DISCOVERY_URL_GUIDE.md).

| Host/superfície | Path | Estado/evidência |
|---|---|---|
| affiliate.shopee.com.br — Dashboard | /dashboard | READY, Top 5 vazio; E-SP-01 |
| Oferta Shopee | /offer/shopee_offer | READY, tabela/categorias; E-SP-07 |
| Oferta produto/detalhe | /offer/product_offer e /offer/product_offer/22193956904 | READY, cards/shop/item/comissão por canal; E-SP-02/03 |
| Modal de oferta | Detalhe → Obter link | Padrão/Avançado, loading/resultado, cinco Sub IDs; E-SP-17/18 |
| Link personalizado | /offer/custom_link | READY/resultado, validação local, challenge, retomada manual, no-result; E-SP-04/05/15/20/21 |
| Loja | /offer/brand_offer | READY, período/comissão; E-SP-06 |
| Exclusivas/campanhas | /offer/offer_for_me e /campaign/campaign_list | EMPTY / lista READY; E-SP-08/09 |
| Conta API | /open_api | Portal READY; API indisponível para conta; E-SP-10 |
| Biblioteca/documentos API | /open_api/home e documentos | Inicialmente verificação expirada; retomada, oito métodos/transporte lidos; E-SP-14/E-API-01/02 |
| shopee.com.br — produto público | /product/1487590844/22193956904 e /opaanlp/1487590844/22193956904 | Redirect/título/tracking confirmados; E-SP-16/18 |
| Site público — ofertas relâmpago | /flash_sale, promotionId, categoryId=11 | Home/lista/filtro de beleza/cards observados sem challenge nesta visita; E-SP-PUB-01..05 em SHOPEE_PUBLIC_FINDINGS.md; estabilidade pendente |

Portal: navegação SPA pode manter shell; loading e resultado disabled são transitórios. customLink_sub_id1..5 e getLinkModal_sub_id1..5 pertencem a contextos diferentes. Resultado short deve vir do textarea DOM, com cardinalidade/contexto; clipboard não confirmado.

Proteção forte/recorrente no portal: verificação expirada/falhou observadas; operador relata cerca de três CAPTCHAs manuais. Evitar extensão operacional no portal, priorizar API oficial. Site público permanece candidato a captura assistida investigada separadamente, sem inferir ausência de proteção. Parar em challenge; nunca automatizar CAPTCHA ou retry de contorno.
