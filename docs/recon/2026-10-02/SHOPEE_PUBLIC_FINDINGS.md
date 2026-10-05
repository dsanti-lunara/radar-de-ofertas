# Shopee pública — investigação adicional de ofertas relâmpago

Sessão iniciada em 2026-10-02 America/Sao_Paulo, atravessando 2026-10-03 UTC. Browser Edge existente, aba auxiliar criada no host público; leitura DOM e navegação por superfícies observadas. Sem endpoint privado, storage/cookies/tokens, compra, carrinho, link afiliado ou publicação. Header/perfil/carrinho e sugestões da sessão não persistidos.

| Evidência | Superfície/ação | Resultado |
|---|---|---|
| E-SP-PUB-01 | shopee.com.br/ | Home carregou; região Ofertas Relâmpago, contador, cards e Ver Tudo. Sem challenge visível nesta observação |
| E-SP-PUB-02 | /flash_sale?promotionId=<public-promotion-id> | Lista carregou com categorias e cards. Clique Ver Tudo teve timeout do host; leitura confirmou permanência na home; navegação direta ao href observado chegou à lista. Outra leitura teve timeout; leitura posterior confirmou conteúdo. Não atribuir esses timeouts a antibot sem evidência |
| E-SP-PUB-03 | Categoria Beleza e Cuidado Pessoal | Clique no texto exato; inicialmente região sem cards, posteriormente cards de beleza presentes. Anchor ativo navbar-with-more-menu__item--active; href /flash_sale?categoryId=11&promotionId=<public-promotion-id>. Não tratar ausência transitória de cards como EMPTY |
| E-SP-PUB-04 | Card público | Lixeira Knock 12L: shop 1807752749/item 58263807139 no href -i.shop.item; referência anunciada 300,00, preço exibido 63,70, desconto anunciado 79%, 12 itens vendidos |
| E-SP-PUB-05 | Card de beleza | Salon Line kit shampoo/condicionador: shop 616222685/item 14463127889; referência anunciada 73,50, preço exibido 47,99, desconto anunciado 35%, 66 itens vendidos |
| E-SP-PUB-06 | Operador selecionou Casa e Cozinha | Categoria ativa categoryId=20, mesma promoção; cards carregados (lixeira, luminária, kit caixas de joias etc.), sem challenge visível nessa observação. Kit 20-40-60 não autoriza mensagem usando uma quantidade arbitrária pelo preço do card |
| E-SP-PUB-07 | Detalhe da lixeira em aba auxiliar | Inicialmente título/produto, opções 12L/12LPreto (segunda disabled) e seção Estoque 79 visíveis; preço não confirmado. Em leitura posterior h1 mudou para **Verifique para continuar**, heading com cardinalidade 1. Parada da parte afetada; nenhum CAPTCHA automatizado ou retry. Não tratar DOM parcialmente carregado como READY definitivo nem estoque como prova de disponibilidade atual |
| E-SP-PUB-08 | Operador resolveu CAPTCHA manualmente | Detalhe retomou: título esperado, preço exibido R$63,70 e referência R$300,00, opção 12L selecionada, 12LPreto disponível. Valores card/detalhe coincidem para o estado selecionado; não valida checkout, frete/cupom, comissão ou todas variantes |
| E-SP-PUB-09 | Tentativa de seleção 12LPreto | Locator encontrou um botão visível/enabled, mas ação teve timeout. Leitura posterior ainda mostrou 12L selecionada, 12LPreto não selecionada e mesmos preços; sem novo challenge. Não afirmar troca de variante; clique não repetido. Estabilidade da ação e preço da opção preta permanecem inconclusivos |

Preços são snapshots de UI, não recomendações atuais nem validação de checkout. Referência riscada não é histórico independente de preço; porcentagem anunciada não é Deal Score. Vendas e “Popular”/“Só mais” têm semânticas diferentes; não converter Popular em volume ou “só mais” em estoque SKU garantido. Card não fornece todas as condições de variante, frete, Pix/cupom ou elegibilidade afiliada. API pode confirmar oferta/comissão; não inferir capability flash_sale a partir de productOfferV2.

## Seletores candidatos

| Elemento | Primário | Fallback/risco |
|---|---|---|
| Home flash | role region, name Ofertas Relâmpago | Região relativa com link href /flash_sale; falhar em ausência/duplicação |
| Ver Tudo | link aria-label clique, entrar em ofertas relâmpago botão Ver Tudo, scoped | href observado dentro da região; não Ver Tudo global; timeout precisa observar antes de repetir |
| Categoria | Texto exato Beleza e Cuidado Pessoal dentro navbar | Anchor href categoryId no contexto de promoção; CSS é candidato, não estável certificado |
| Categoria ativa | Anchor com navbar-with-more-menu__item--active | Correlacionar categoria/URL/resultado; não aceitar só presença do texto |
| Card | Anchor com href -i.shop.item, scoped na lista | aria-label contém nome/preço/desconto/vendas mas também literal null; não usar string inteira como seletor persistente |
| Preço | Região/card com texto monetário e semântica atual/referência | Dois strong observados, referência e atual; não usar primeiro/último strong global ou nth-child como contrato |

Não houve desafio visível em home/lista/filtros nesta visita, **mas o detalhe público ativou Verifique para continuar**. Site público também exige estado CHALLENGE/HumanAction e não oferece garantia de revalidação recorrente automática. Separar capacidade da lista e do detalhe, sem generalizar READY para o host inteiro. Captura pública assistida é candidata: faltam fixture DOM completa, negativos/fallback, produto/variante/condições, expiração da promoção, cross-session/Chrome VM e testes do adapter. Não fazer crawling massivo nem usar browser para contornar bloqueio de API. Aba do detalhe preservada para resolução manual, sem bloqueio dos trabalhos documentais independentes.

[Gates de produção](PRODUCTION_READINESS.md). Esta leitura adicional adianta a investigação, não aprova produção.

## Redução de interrupções sem contornar proteção

Não foi encontrada nem validada forma de garantir acesso sem CAPTCHA. Não há prova de que a extensão seja a causa: comparar navegação manual e assistida no mesmo ambiente autorizado é investigação de compatibilidade, não promessa de eliminação do challenge.

Planejar uso de API oficial para operações recorrentes documentadas, orçamento conservador, cache com timestamps/TTL e dedupe de consultas, reutilização de abas e captura assistida de itens visíveis. Cache nunca substitui a revalidação exigida antes de envio. Se não houver dado atual verificável por fonte permitida, bloquear publicação/gerar HumanAction. Rate limit oficial não autoriza browser crawl. Não usar stealth, proxy/rotação de identidade, falsificação de fingerprint, solver ou endpoints privados. Não alternar métodos para contornar bloqueio.

Regra de estado: DOM inicial incompleto → aguardar sinais de prontidão; CHALLENGE → suspender somente parte afetada e solicitar ação humana; retomada → revalidar host/produto/variante/dados, sem continuar cegamente tentativa de side effect. Adotar circuit breaker e limitar intervenções antes de considerar capacidade operacional adequada. Threshold deve ser definido nas issues, não inventado nesta reconnaissance.
