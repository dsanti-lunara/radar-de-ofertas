# Shopee Capability Report

Status em 2026-10-02: **DOCUMENTAÇÃO OFICIAL INVESTIGADA — API SEM ACESSO PARA A CONTA; API LIVE PENDENTE**.

Investigação no Edge com sessão existente e documentação oficial Brasil. [Relatório consolidado vigente](recon/2026-10-02/BROWSER_RECON_COMPLETION.md) e [contratos API detalhados](recon/2026-10-02/API_DOCUMENTATION_FINDINGS.md). Links browser gerados e tracking validado com autorização. Não houve chamada API autenticada, solicitação de acesso ou coleta de credenciais. Planejamento por documentação autorizado pelo usuário; documentação acessível não comprova entitlement.

## Regra

Não assumir capabilities a partir de documentação de outro país, package de terceiros ou engenharia reversa.

Confirmar aquilo que a conta Brasil realmente oferece.

## Informações a registrar

### Conta/API

- nome da área: Abrir API → Meu API (`https://affiliate.shopee.com.br/open_api`).
- método de autenticação documentado: Authorization, AppID/Credential, Timestamp, assinatura SHA256 de AppID + Timestamp + Payload + Secret; tolerância de relógio 10 minutos. Inconsistência textual Credential/Credentials deve ser resolvida antes do adapter.
- App ID: portal apresenta `--`; não disponível para esta conta.
- secret: documentação exige Secret; portal apresenta Senha `--`, sem credencial provisionada observável. Nenhum valor registrado.
- environment: portal Brasil; API produtiva/sandbox da conta não confirmados.
- endpoint oficial confirmado documentalmente: POST `https://open-api.affiliate.shopee.com.br/graphql`, application/json, mesmo endpoint para operações; fonte Request and Response. Não houve chamada live.
- GraphQL/REST: GraphQL sobre HTTP documentado.
- token/refresh behavior: assinatura por request documentada; OAuth/access token/refresh não confirmados.
- rate limits: overview informa 8000 chamadas/hora; scope/rate por operação não testados.
- relatórios: overview informa janela recente de 3 meses; paginação até 500 registros, scrollid uma vez/30s e intervalo maior que 30s para consulta sem scrollid. Confirmar aplicabilidade por método.
- documentation source: `/open_api/home`, `/open_api/document?type=overview`, `/open_api/document?type=authentication`, no host oficial Brasil.
- acesso da conta: aviso explícito “No momento você não possui acesso à Plataforma de Open API dos Afiliados Shopee”. Ação Aplicar não executada.
- proteção: tentativa inicial de documento encontrou verificação expirada; posteriormente biblioteca acessível, oito operações lidas. Portal custom_link também apresentou verificação falhou; retomado somente após validação manual do usuário, sem bypass pelo agente.

### Capabilities

| Capability | Supported | Method | Evidence | Notes |
|---|---:|---|---|---|
| Product discovery | Conta API sem acesso; contrato documental confirmado | productOfferV2 | E-API-01 | Query shop/item, filtros/page/limit; browser captura visível assistida candidato, sem crawling |
| Product details | Oferta consultável documentalmente; SKU/estoque/frete API genérico TBD | productOfferV2 shopId/itemId; getItemFeedData | E-SP-03/E-API-01 | Não confundir range preço/feed columns com checkout/variante |
| Affiliate offers | Conta API sem acesso; contrato documental confirmado | shopeeOfferV2 | E-SP-07/E-API-01 | Browser tabela observado |
| Brand offers | Conta API sem acesso; contrato documental confirmado | shopOfferV2 | E-SP-06/E-API-01 | Nome do menu Brand; query atual Shop |
| Campaigns | API específica não confirmada | Portal Campaigns | E-SP-09 | Lista observada, condições não auditadas |
| Short/affiliate link | Browser geração/destino observados; API conta sem acesso | generateShortLink mutation / Link personalizado / modal padrão-avançado | E-SP-15..18/E-API-01 | API originUrl/subIds/shortLink; copy browser não confirmado no clipboard host |
| Sub IDs | Browser cinco posições/roundtrip confirmados; API cinco subIds documentados | subIds [String], utmContent | E-SP-05/16/18/E-API-01 | Charset alfanumérico, hífen rejeitado; maxlength ainda desconhecido |
| Conversion report | Conta API sem acesso; contrato documental confirmado | conversionReport | E-API-01 | Scroll/time/order/item/model/commission/utmContent; sem chamada autenticada |
| Validated report | Conta API sem acesso; contrato documental confirmado | validatedReport | E-API-01 | validationId, scroll e comissões validadas; sem chamada autenticada |
| Product feed | Conta API sem acesso; contrato documental confirmado | listItemFeeds / getItemFeedData | E-API-01 | FULL/DELTA, datafeedId/referenceId, offset/limit até 500, columns JSON String |

## Decisão por capability

```text
API_SUPPORTED
BROWSER_ASSISTED
MANUAL
NOT_SUPPORTED
```

## Security

Não colocar secret, access token ou refresh token neste documento.

## Decisões e impacto nas issues

Complemento: [home/lista relâmpago/filtro de beleza públicos](recon/2026-10-02/SHOPEE_PUBLIC_FINDINGS.md) agora observados sem challenge nesta visita, com seletores candidatos. Isso supersede a pendência de investigação inicial abaixo; estabilidade/fixtures completas/aceite de adapter continuam pendentes. [Gates de produção](recon/2026-10-02/PRODUCTION_READINESS.md).

Atualização E-SP-PUB-06/07: Casa e Cozinha categoryId=20 confirmada; **detalhe público também ativou Verifique para continuar** após renderização inicial. Não assumir ausência de antibot no site normal; captura da lista e revalidação do detalhe precisam de estados/limites separados e parada humana. [URLs e percurso guiado](recon/2026-10-02/DISCOVERY_URL_GUIDE.md).

E-SP-PUB-08/09: resolução humana permitiu retomada/preço da opção 12L; mudança para opção preta não confirmada por timeout. Não há forma validada de eliminar CAPTCHA nem prova de causalidade da extensão. API oficial prioritária para operações documentadas; cache/TTL/dedupe não dispensam revalidação pré-envio e bloqueio quando dado atual é indisponível.

- Nenhuma capability `API_SUPPORTED` para a conta nesta sessão. Ausência de acesso não prova `NOT_SUPPORTED` global.
- Portal `affiliate.shopee.com.br`: happy path de links observado, mas proteção recorrente impede recomendá-lo como fluxo operacional por extensão. Operador relatou cerca de três resoluções manuais de CAPTCHA (`USER_REPORTED`); agente observou verificação expirada/falhou. Preferir API oficial nas operações recorrentes; portal manual para consulta/configuração. Sem bypass/retry automático.
- Site público Shopee: operador relata uso aparentemente viável em produtos/ofertas relâmpago, sem antibot percebido. Relato não prova ausência de proteção. Destinos públicos, ofertas relâmpago/listas/filtros e detalhe foram investigados em E-SP-PUB-01..09; estabilidade recorrente e variante preta não foram comprovadas. Captura visível `BROWSER_ASSISTED` permanece candidata a investigação separada por host, com parada em challenge e sem crawling. Não promover AUTO.
- RDR-077: registrar bloqueio de acesso e HumanAction do operador; completar schemas oficiais depois da verificação humana.
- RDR-095/096/097: planejamento/contratos pela documentação autorizados; execução API real condicionada a acesso e testes oficiais; providers Fake podem avançar sem credenciais.
- RDR-098/099: separar detecção/estados por host; portal manual/diagnóstico e possível captura pública assistida são escopos distintos. Investigar ofertas relâmpago do site público antes de aceitar seletores reais.
- RDR-100/101: priorizar generateShortLink oficial; preservar Link personalizado/modal como evidência e suporte manual, sem extensão operacional no portal. IDs customLink/getLinkModal distintos, cinco Sub IDs e roundtrip observado; limites por campo ainda pendentes.
- RDR-102: resultado/contexto/redirect observados nesta reconnaissance; SAFE_LIVE de adapter/recuperação continuam gates distintos. Inputs inválidos no custom_link não produziram resultado/erro visível. IDs são locais do Issue Map; nenhuma issue criada/editada nesta avaliação.

## Output

Ao final do spike:
1. atualizar tabela;
2. registrar gaps;
3. registrar rate/usage constraints;
4. listar quais issues RDR-095..RDR-102 precisam ser criadas, removidas ou divididas;
5. não implementar adapter nesta mesma task, a menos que a issue explicitamente autorize.
