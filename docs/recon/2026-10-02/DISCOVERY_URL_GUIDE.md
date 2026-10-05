# URLs de entrada para discovery e investigação

URLs públicas ou caminhos de ferramentas observados nesta sessão. Não contêm links afiliados opacos, segredos, perfil privado ou identificador de grupo. Um URL permitir acesso direto não certifica seletor, sessão, produto, preço ou capacidade. Verificar host/path/contexto e estado READY a cada visita; parar em AUTH_REQUIRED/CHALLENGE, sem retry de contorno.

## Shopee — site público, discovery assistido candidato

| Finalidade | URL | Uso futuro |
|---|---|---|
| Home / promoção vigente | https://shopee.com.br/ | Ponto inicial; localizar região Ofertas Relâmpago e seguir href vigente |
| Ofertas relâmpago | https://shopee.com.br/flash_sale | Entrada pública observada no footer; lista acessada com promotionId nesta sessão; revalidar conteúdo atual |
| Campanha da sessão | https://shopee.com.br/flash_sale?promotionId=508768026837425 | Histórico público; ID temporário, não fixar no scheduler |
| Beleza na campanha da sessão | https://shopee.com.br/flash_sale?categoryId=11&promotionId=508768026837425 | Filtro e estado ativo observados; descobrir promoção vigente e revalidar taxonomia |
| Casa e Cozinha na campanha da sessão | https://shopee.com.br/flash_sale?categoryId=20&promotionId=508768026837425 | Seleção do operador, estado ativo e cards confirmados; promoção temporária |
| Produto Eudora usado no teste | https://shopee.com.br/product/1487590844/22193956904 | Destino público observado; identidade shop/item; não garante oferta/preço atuais |
| Lixeira do card relâmpago | https://shopee.com.br/Lixeira-Automática-Knock-12L-–-Sem-Toque-Sensor-Infravermelho-e-Tampa-para-Cozinha-Banheiro-Escritório-e-Quarto-i.1807752749.58263807139 | Challenge resolvido manualmente; preço 63,70 com 12L selecionada coincidiu com card; troca 12LPreto não confirmada, sem validação de checkout |
| Kit Salon Line do filtro beleza | https://shopee.com.br/Kit-S.O.S-Hidratação-Azeite-de-Oliva-Shampoo-e-Condicionador-Litrão-Salon-Line-i.616222685.14463127889 | Href observado no card; detalhe/variante/condições pendentes |

Percurso guiado recomendado: home → região flash → campanha vigente → categoria de interesse → cards visíveis → detalhe do produto → identidade/variante/condições → oferta/comissão pela API oficial quando liberada. Captura candidata deve guardar source_url, observed_at, IDs de produto e campanha, categoria e evidência de preço. Não tratar desconto anunciado como histórico independente ou score. Link comum de produto não substitui link afiliado retornado pelo provider.

Sem challenge observado em home/lista/filtros nesta visita; detalhe público ativou Verifique para continuar. Não é garantia de estabilidade ou ausência de proteção. [Evidências públicas](SHOPEE_PUBLIC_FINDINGS.md).

## Shopee — portal afiliado, consulta/configuração manual

Evitar extensão como operação recorrente neste host devido à proteção forte/recorrente. URLs preservadas para consulta humana, diagnóstico e fontes; não são fallback automático de discovery/link.

| Finalidade | URL |
|---|---|
| Dashboard | https://affiliate.shopee.com.br/dashboard |
| Ofertas produto | https://affiliate.shopee.com.br/offer/product_offer |
| Detalhe observado | https://affiliate.shopee.com.br/offer/product_offer/22193956904 |
| Ofertas Shopee | https://affiliate.shopee.com.br/offer/shopee_offer |
| Ofertas loja | https://affiliate.shopee.com.br/offer/brand_offer |
| Exclusivas | https://affiliate.shopee.com.br/offer/offer_for_me |
| Campanhas | https://affiliate.shopee.com.br/campaign/campaign_list |
| Link personalizado | https://affiliate.shopee.com.br/offer/custom_link |
| Estado de acesso API | https://affiliate.shopee.com.br/open_api |

## Shopee — documentação/API oficial Brasil

| Fonte | URL |
|---|---|
| Biblioteca | https://affiliate.shopee.com.br/open_api/home |
| Overview | https://affiliate.shopee.com.br/open_api/document?type=overview |
| Autenticação | https://affiliate.shopee.com.br/open_api/document?type=authentication |
| Request/Response | https://affiliate.shopee.com.br/open_api/document?type=request_response |
| productOfferV2 | https://affiliate.shopee.com.br/open_api/list?type=product_offer |
| shopeeOfferV2 | https://affiliate.shopee.com.br/open_api/list?type=shopee_offer |
| shopOfferV2 | https://affiliate.shopee.com.br/open_api/list?type=brand_offer |
| generateShortLink | https://affiliate.shopee.com.br/open_api/list?type=short_link |
| listItemFeeds | https://affiliate.shopee.com.br/open_api/list?type=product_feed_offer |
| getItemFeedData | https://affiliate.shopee.com.br/open_api/list?type=product_feed_offer_detail |
| conversionReport | https://affiliate.shopee.com.br/open_api/list?type=conversion_report |
| validatedReport | https://affiliate.shopee.com.br/open_api/list?type=validation_report |
| Endpoint documentado — POST GraphQL | https://open-api.affiliate.shopee.com.br/graphql |

Endpoint não é página de discovery; não usar GET no browser para validar API. Entitlement/secret/teste autenticado pendentes. [Contratos e limites](API_DOCUMENTATION_FINDINGS.md).

## Mercado Livre

| Finalidade | URL | Uso futuro |
|---|---|---|
| Central afiliados | https://www.mercadolivre.com.br/afiliados/hub | Entrada autenticada, cards e ferramentas |
| Gerador | https://www.mercadolivre.com.br/afiliados/linkbuilder | Side effect: geração adiciona Minhas recomendações; oportunidade/autorizações/guards necessários |
| Etiquetas | https://www.mercadolivre.com.br/afiliados/adminlabel | Configuração manual; não criar/alterar automaticamente |
| Produto observado | https://www.mercadolivre.com.br/principia-kit-2-protetor-solar-corporal-ps-03-fps60/p/MLB43187757?pdp_filters=item_id%3AMLB5178681714 | Catálogo/anúncio da sessão; revalidar vendedor/variante/preço |
| Ajuda da geração | https://www.mercadolivre.com.br/ajuda/30084 | Fonte do efeito de geração |

Links full de afiliado em /social/<affiliate> e shorts meli.la são resultados de provider; não registrar valor opaco no guia, não sintetizar e não editar via IA.

## WhatsApp

Entrada: https://web.whatsapp.com/. Não há URL/ID persistente de grupo validado nesta investigação. Abrir a home não comprova destino. Destino registrado + identidade/pareamento humano persistente + preflight/hash continuam necessários; nome do grupo isolado não é suficiente. Nenhum novo envio autorizado por este guia.

## Manutenção

Este guia é mapa de navegação para planejamento, não allowlist executável nem configuração runtime. Validar URLs e seletores em SAFE_LIVE do adapter no Chrome/VM; permitir apenas hosts/capabilities do contrato. Extrair links atuais da região correta e rejeitar destinos inesperados. Não persistir tracking privado, sessão, QR ou URL de grupos com convite/acesso.
