# Browser Reconnaissance — ML e Shopee

> **Versão inicial de leitura, preservada como histórico.** O [relatório consolidado vigente](BROWSER_RECON_COMPLETION.md) inclui geração de links autorizada, cinco Sub IDs, documentação API detalhada, teste de envio sandbox e decisão do usuário de usar WhatsApp Groups. As pendências e ausência de autorização descritas abaixo pertencem à primeira etapa, não ao estado final.

Data de referência: 2026-10-02, America/Sao_Paulo; sessão iniciada em 2026-10-03 UTC. Ambiente: Windows, Edge, perfil e abas existentes do operador. Skill aplicada: `browser-use:browser-use`; controle host-managed via `cua_repl`. Fontes locais: SDD Master, Browser Bridge, Data Contracts, Publishing/Tracking, Decision Log, QA Matrix, Error Catalog, SPEC-06 e Issue Map.

## Resultado e decisão

**Reconnaissance de leitura realizada; gate de adapter real ainda NÃO aprovado.** Superfícies ML/Shopee, formulários, tracking, navegação, estados vazios e documentação acessível foram investigados. Geração de links, resolução/validação do resultado, autenticação expirada e recuperação do adapter permanecem sem prova. WhatsApp não foi investigado: nenhuma aba ou destino sandbox configurado foi apresentado.

A conta Shopee **não tem acesso à Open API**, embora a documentação oficial Brasil esteja acessível. Não classificar operações documentadas como `API_SUPPORTED` para esta conta. ML possui efeito externo adicional documentado: gerar link/ID adiciona o produto a “Minhas recomendações”. O exemplo de etiqueta do contrato é incompatível com a UI real.

Este pacote serve para melhorar ou propor issues. Não cria/fecha issues, não implementa adapters e não promove capabilities para AUTO. IDs RDR abaixo são IDs locais de `ISSUE_MAP.md`, não números GitHub; o tracker remoto não foi consultado.

## Controle operacional e escopo

- `BROWSER_RECON_MODE` foi o modo de trabalho desta investigação. O repositório inspecionado contém documentação, sem aplicação, scheduler ou configuração operacional versionados; portanto não houve toggle de runtime a alterar nem prova de kill switch de uma instalação externa. Nenhum comando de publicação foi executado nesta sessão.
- Abas reutilizadas: Central ML, produto ML Principia, portal Shopee. Abas auxiliares abertas: documentação oficial Shopee e ajuda oficial ML. Nenhuma sessão foi importada, login automatizado, cookie/token extraído ou endpoint privado reproduzido.
- Foram realizados leitura DOM/AX, navegação por links e preenchimento local de formulários sem submissão. Nenhuma etiqueta foi criada/selecionada como nova etiqueta ativa; nenhum link foi gerado; nenhuma publicação, compra, aplicação para API ou ajuste fiscal/comercial foi feito.
- A autorização específica de links de teste e a disponibilidade de canal WhatsApp sandbox foram solicitadas. Até a emissão deste documento, não havia resposta; os passos dependentes ficaram pendentes.
- Valores privados de cabeçalho, nome da conta, endereço, métricas privadas, etiquetas existentes, parâmetros de tracing e identificadores de verificação foram omitidos dos artefatos. Screenshots completos não foram persistidos por conterem dados de conta. Fixtures são fragmentos DOM mínimos ou projeções semânticas explicitamente identificadas.
- Edge é ambiente de reconnaissance autorizado, **não** substitui homologação de Chrome MV3 no perfil dedicado da VM Linux prevista no SDD.

## Evidências observadas

IDs E-* referenciam observações desta sessão via host, com excertos sanitizados persistidos neste pacote. Não são logs remotos, screenshots ou resultados de testes de adapter.

| ID | Página sanitizada | Observação direta / documento oficial |
|---|---|---|
| E-ML-01 | `https://www.mercadolivre.com.br/afiliados/hub` | Central disponível em sessão autenticada; ferramenta `Gerador de links`, ID `AFFILIATES_LINK_BUILDER`; `Administrar etiquetas`, ID `AFFILIATES_ADMIN`. Cards têm preço, comissão, avaliação/vendas e vários `Compartilhar`; produto duplicado visível na lista. |
| E-ML-02 | `/afiliados/linkbuilder` | Título `Gerador de produtos recomendados`; textarea `url-0`, label `Insira 1 ou mais URLs separados por 1 linha`, maxlength DOM 1000000; combobox `Selecione sua etiqueta`; `Gerar` disabled vazio. Nenhuma opção short/full observada no formulário vazio. |
| E-ML-03 | `/afiliados/linkbuilder` | URL de produto `/p/MLB43187757` habilitou `Gerar`. Texto `nao-e-url`, seguido de blur, também habilitou o botão e não exibiu erro local. Não houve submissão. |
| E-ML-04 | `/afiliados/adminlabel` | `Administrador de etiquetas`; lista de etiquetas/radios, etiqueta em uso e busca; dropdown do gerador apresentou opções existentes. Mesma seleção observada ao retornar ao gerador, sem testar alteração/persistência de nova seleção. |
| E-ML-05 | `/afiliados/adminlabel`, modal | `Crie uma etiqueta`; letras e números, sem espaços, maiúsculas ou especiais; `textfield-new-tag`, `data-testid=input-create-label`, maxlength 30. `Teste com espaço!` produziu `Erro`, `aria-invalid=true`; `recon20261002` removeu o erro. Nada salvo. |
| E-ML-06 | `/principia-kit-2-protetor-solar-corporal-ps-03-fps60/p/MLB43187757` | Produto e barra `Afiliados` disponíveis; preço R$91,63, ganhos extras 20%, anúncio MLB5178681714. **Dois** buttons `Compartilhar` no DOM acessível. Barra tem `data-testid=generate_link_button`, ID `P0-1`; botão genérico do produto tem outro ID. Não abrir compartilhamento sem autorizar possível geração. |
| E-ML-07 | `https://www.mercadolivre.com.br/ajuda/30084` | Ajuda oficial `Como recomendar um produto`, alcançada a partir `/ajuda/32979`: “Sempre que você gerar um link ou ID, adicionamos o produto à lista ‘Minhas recomendações’”. Descreve selecionar etiqueta, gerar e pré-visualizar no perfil. Diz que links/IDs não têm vencimento enquanto item disponível; isso não elimina revalidação de oferta. |
| E-SP-01 | `https://affiliate.shopee.com.br/dashboard` | `Painel de controle`, período dos dados, inputs de início/fim e atualização diária às 5:30 PM; seção Top 5 sem produtos na observação. Aviso de informações de pagamento/fiscais incompletas. Valores privados de métricas não persistidos. |
| E-SP-02 | `/offer/product_offer` | Busca `Buscar por todos os produtos na Shopee`; tabs Todos, Comissão da marca, Melhor performance, Casa e Construção, Beleza etc. Cards com preço, vendas, comissão, checkbox e button `Obter link`; ação em massa disabled com zero selecionados, contador `0 / 100`. Não percorrer paginação/crawling. |
| E-SP-03 | `/offer/product_offer/22193956904` | Detalhe `Eudora Siàge Liso Intenso kit`, R$64,99, 21 vendas; `Ver produto` aponta `/product/1487590844/22193956904`. Um button `Obter link`. Tabela separa redes sociais, Lives e Vídeo com comissões diferentes. Rede social: 23% + 3%, estimado R$16,90; não tratar como comissão universal. |
| E-SP-04 | `/offer/custom_link` | Nome atual `Link personalizado`; textarea até 5 links em linhas distintas; cinco labels/inputs `Sub_id 1..5`, IDs `customLink_sub_id1..5`; button submit `Obter link`. Página suporta conversão de home, produto, campanha, loja e categoria. Isso não prova elegibilidade de publicação de produto. |
| E-SP-05 | `/offer/custom_link` | Regra explícita a-z/A-Z/0-9; máximo cinco Sub IDs; inputs sem maxlength DOM observado. `recon-teste` em Sub_id 1 e blur produziu `Número inválido`; `Recon20261002` e blur removeu o erro. Valores removidos depois; nenhuma submissão. |
| E-SP-06 | `/offer/brand_offer` | Oferta da loja carregada: tabela com nome, período, comissão “até”, `Ver detalhes`, `Obter link`; seleção/ação em massa. Valores máximos e períodos não provam comissão efetiva de todo produto. |
| E-SP-07 | `/offer/shopee_offer` | Ofertas Shopee por categoria, períodos e comissão “até”; vários links `Obter link` por row; contador em massa 0/100. |
| E-SP-08 | `/offer/offer_for_me` | Ofertas Exclusivas: busca, ordenação comissão/vendas/preço e estado `Sem Dados`. É estado vazio observado; não inferir capability inexistente nem auth expirada. |
| E-SP-09 | `/campaign/campaign_list` | Campanhas de Afiliados carregadas com nomes, período, `Em Andamento`, `Novo` e `Ver detalhes`. Nenhuma adesão realizada; condições/detalhes de cada campanha não foram auditados. |
| E-SP-10 | `/open_api` | `Meu API`: AppID `--`, Senha `--`, ação `Aplicar`; aviso explícito “No momento você não possui acesso à Plataforma de Open API dos Afiliados Shopee”. Não clicar Aplicar/solicitar acesso. |
| E-SP-11 | `/open_api/home` | Biblioteca oficial lista Shopee Offer, Brand Offer, Product Offer, Product Feed Offer, Feed Detail, Short Link, Conversion Report e Validated Report. Documentação acessível é distinta de entitlement da conta. |
| E-SP-12 | `/open_api/document?type=overview` | GraphQL sobre HTTP; 8000 chamadas/hora; paginação de relatório com até 500 registros, scrollid válido uma vez por 30s; consulta sem scrollid exige intervalo maior que 30s; janela de conversões recente de 3 meses. Aplicabilidade detalhada deve ser confirmada por operação. Links oficiais explorer no host `open-api.affiliate.shopee.com.br`; endpoint de produção não confirmado. |
| E-SP-13 | `/open_api/document?type=authentication` | Header Authorization com AppID/Credential, Timestamp e Signature; SHA256 de AppID + Timestamp + Payload + Secret; tolerância de timestamp 10 minutos; assinatura hexadecimal minúscula. Documentação tem inconsistência textual Credentials/Credential, a resolver antes do adapter. Apenas placeholders/método registrados, sem copiar exemplos de assinaturas ou credenciais reais. Não observado OAuth/refresh. |
| E-SP-14 | tentativa `/open_api/list?type=product_offer` | Navegação resultou em página `Erro de Tempo Esgotado`, `Verificação expirou. Tente novamente.`, button `Voltar`. Interrompida sem CAPTCHA, bypass ou repetição automática. Mapear proteção/verificação para intervenção humana; URL final dessa tela não foi registrada. |

## Cobertura do roteiro

`OBSERVADO` significa inspeção real da superfície. `PARCIAL` não passa o gate de implementação. `PENDENTE` não significa `NOT_SUPPORTED`.

| Etapa | Estado | Evidência / falta |
|---|---|---|
| ML-01 Central | OBSERVADO | E-ML-01 e navegação para gerador |
| ML-02 vazio | OBSERVADO | E-ML-02; loading/short/full não confirmados |
| ML-03 preenchimento | PARCIAL | E-ML-03; sem resposta de servidor para URL inválida/tipos alternativos |
| ML-04 resultado | PENDENTE | Sem gerar, sem copy/resultado/link final |
| ML-05 etiquetas | PARCIAL | E-ML-04/05; charset/30 confirmados; quota, criação, persistência e associação real ao link pendentes |
| ML-06 barra | PARCIAL | E-ML-06; ausência da barra, modal e resultado não exercitados |
| SP-01 dashboard | OBSERVADO | E-SP-01 |
| SP-02 produto | OBSERVADO | E-SP-02/03; catálogo não é checkout nem prova de estoque atual |
| SP-03 Obter link | PARCIAL | Botões/contextos identificados, sem execução de geração/modal |
| SP-04 conversão | OBSERVADO | E-SP-04; nome atual diferente do roteiro |
| SP-05 resultado | PENDENTE | Nenhum affiliate_url/copy/redirect verificado |
| SP-06 Sub IDs | PARCIAL | E-SP-05; posições/charset confirmados, limites por campo e roundtrip pendentes |
| SP-07 loja | OBSERVADO | E-SP-06; sem obter link/detalhes de loja |
| SP-08 campanha/exclusivas | PARCIAL | E-SP-08/09; lista e vazio, sem adesão/condições detalhadas |
| SP-09 Abrir API | OBSERVADO | E-SP-10: acesso ausente |
| SP-10 API da conta | PARCIAL/BLOQUEADO | E-SP-11..14: documentos oficiais, sem credenciais/entitlement/teste autenticado |
| WA-01..04 | PENDENTE | Sem aba WhatsApp, destino configurado, canal sandbox ou autorização de envio |

## State map, autenticação e recuperação

| Estado | Evidência real | Comportamento requerido para issue |
|---|---|---|
| READY | ML gerador/admin/produto e Shopee portal | Exigir host/path/contexto + elementos únicos + estado estável; sessão marketplace permanece no navegador |
| LOADING | Conteúdo principal inicialmente vazio em transições, depois carregado | Polling DOM limitado; não interpretar vazio inicial como UNSUPPORTED/AUTH_REQUIRED; timeout separado de mudança estrutural |
| EMPTY | Shopee exclusivas `Sem Dados`, Top 5 vazio | Resultado vazio válido, sem retry/crawl para “preencher” |
| LOCAL_VALIDATION_ERROR | ML etiqueta inválida; Shopee Sub ID com hífen | Falha acionável; não submeter nem normalizar silenciosamente o identificador |
| AUTH_REQUIRED | Não exercitado | Fixture de sessão ausente; HumanAction, zero loop de login/retry; não provocar logout da conta para testar |
| CHALLENGE / verificação expirada | E-SP-14 | Interromper capability; intervenção humana. Não classificar indiscriminadamente como expiração de login ou simples erro transient |
| UNSUPPORTED | API explicitamente indisponível para conta | Bloquear API, manter captura assistida; falta de dados não é UNSUPPORTED |
| DOM_CHANGED / AMBIGUOUS | ML dois buttons Compartilhar; muitos Obter link na Shopee | Missing/zero/multiple matches falham fechados antes do clique. Ambiguidade observada, falha do adapter ainda não implementada |
| SUCCESS / REMOTE_ERROR / UNKNOWN_RESULT | Não exercitados nos geradores | Verificar resultado/contexto e auditar; timeout após clique não autoriza novo efeito sem reconciliação |

Navegação do portal Shopee troca caminho e conteúdo mantendo shell/menu (compatível com SPA). Não houve inspeção de framework/eventos internos. ML ferramentas mudam path; algumas âncoras são controles sem href. URL e título isolados não bastam para detector. Um timeout do host ao clicar `Link personalizado` não mudou a página; navegação direta ao href já observado resolveu. Um timeout posterior ao retornar ao gerador ML foi seguido de DOM carregado; não prova seletor permanentemente ausente. Tempos dos tools incluem transporte/host e variaram muito: **não** são latência do marketplace nem SLO de adapter.

Não foram interrompidas rede, sessões ou browser, nem testados reboot, crash/MV3 ou recuperação persistente. State maps desses casos são requisitos pendentes, não resultados aprovados.

## Selector registry candidate

Registro estruturado: [SELECTOR_REGISTRY_CANDIDATE.json](SELECTOR_REGISTRY_CANDIDATE.json). Cada entrada tem primário, dois fallbacks, motivo, ambiguidade, estados e evidência/fixture. Todos são **candidatos**, com estabilidade ainda não comprovada em versões/sessões múltiplas.

Principais decisões:

- ML `Gerar`: role/button + nome exato + escopo da página. Não usar ID React `_R_...` como primário.
- ML URL: role/textbox e label observados; fallback `#url-0`, depois textarea relativo ao formulário confirmado. Resolver correspondência label/elemento em fixture completa antes de aprovar.
- ML criar etiqueta: label `Crie uma etiqueta`, fallback testid `input-create-label` e ID `textfield-new-tag`.
- ML barra: testid `generate_link_button`; nome Compartilhar isolado é ambíguo (2). ID `P0-1` tem risco de ser gerado e não é autoridade principal.
- Shopee lista: selecionar card/row pelo identificador de produto/oferta e então Obter link. Nunca primeiro botão global, `.first()`, índice AX persistido, coordenada ou nth-child como estratégia de adapter.
- Shopee detalhe: role/button `Obter link` único, verificação prévia de `Ver produto` com shop_id/item_id esperado.
- Shopee custom_link: Sub_id por label/ID; textarea não tem label semântico claro no snapshot. Primário por placeholder exato observado; fallback precisa de unicidade dentro do main/form.
- IDs `rc-tabs-0-*`, classes Ant/Andes e `_R_...` não provaram estabilidade. Roles/textos podem variar por idioma; fixture PT-BR e diagnóstico de locale necessários.

## Fixtures e testes

[FIXTURES_SANITIZED.json](FIXTURES_SANITIZED.json) preserva fragmentos HTML mínimos observados (ML URL, gerar vazio, barra, etiqueta inválida; Shopee Sub ID/detalhe) e projeções semânticas de estados. Projeções não devem ser apresentadas como outerHTML original ou screenshot. Valores privados e tracking de conta omitidos; produto e shop IDs mantidos são públicos e necessários para contexto.

[verify_recon_fixtures.py](verify_recon_fixtures.py) valida offline os fragmentos persistidos: atributos/limites, estado disabled/aria-invalid, contexto público e cardinalidade com variantes de seletor ausente/duplicado. Serve para integridade do pacote, **não** implementa detector e não certifica adapter, fallback real, renderização, SPA ou idempotência. Suite de implementação FIXTURE → SAFE_LIVE → SIDE_EFFECT ainda deverá ser construída.

SAFE_LIVE desta investigação foi somente observação e preenchimento local autorizados. Não equivale ao SAFE_LIVE de adapter depois de fixtures aprovadas. SIDE_EFFECT não executado: geração de links sem autorização específica recebida; WhatsApp sem sandbox/destino. Não enviar/publicar para fechar um checklist.

## CAPABILITY_CONFLICT — tracking ML

Decision: contrato conceitual em `docs/04_DATA_CONTRACTS.md` usa `tracking_label: "RB_TG_OFFER"` para `GENERATE_ML_AFFILIATE_LINK`.

Evidence: E-ML-05; UI exige letras minúsculas/números, sem espaços/maiúsculas/especiais, maxlength 30; entrada inválida apresentou aria-invalid e erro.

Why it fails: o exemplo tem maiúsculas e underscores e não atende às regras atuais de criação da etiqueta.

Affected contracts: TrackingContext → payload Browser Job → etiqueta ML → AffiliateLink/auditoria, RDR-092/093 e testes QA de tracking.

Options: (1) mapeamento determinístico de tracking interno para etiqueta ML válida, provisionada e selecionada explicitamente; (2) rejeitar payload que não referencie etiqueta válida existente, mantendo provisionamento humano; (3) revisar vocabulário/exemplo do contrato mediante decisão aprovada.

Recommended option: separar identificador interno de etiqueta externa e começar com provisionamento humano/allowlist; avaliar comprimento, colisões e brand/channel antes de aprovar transformação. Não trocar valores silenciosamente ou criar etiqueta automaticamente nesta investigação.

Tests/experiments performed: inspeção do modal; valor inválido e válido preenchidos/blur, sem salvar. Teste do exemplo exato e associação ao link ainda pendentes.

## Gaps para melhorar/criar issues

| Prioridade / IDs locais | Proposta de ajuste ou investigação | Entrega e acceptance criteria necessários |
|---|---|---|
| P0 gate — RDR-076 | Dividir fechamento do reconnaissance por marketplace e nível de evidência | Este pacote fecha leitura; itens resultado/auth/fallback/recuperação/SAFE_LIVE adapter permanecem abertos. Não concluir spike inteiro com sucesso parcial |
| P0 — RDR-077 | Registrar acesso Shopee ausente e separar documentação de entitlement | HumanAction para operador solicitar acesso por fluxo oficial; sem criação de credenciais pelo agente; documentação operacional completa + teste oficial autenticado antes de liberar dependências |
| P0 — RDR-095/096/097 | Condicionar adapters/discovery/link API ao acesso real | Manter bloqueados; contrato Fake pode avançar independentemente. Não remover API-first nem substituí-la por crawler/browser em massa |
| P0 — RDR-092/093 | Resolver conflito de etiqueta e efeito Minhas recomendações | Decisão explícita para tracking externo; validação charset/30/unicidade; geração somente depois de oportunidade aprovada; auditar produto/etiqueta/resultado e efeito adicional; autorização de teste controlado |
| P0 — RDR-090/091/098 | Detector de superfície/sessão/challenge com evidência negativa | Fixtures READY, loading, vazio, auth, verificação expirada, DOM ausente/ambíguo; CHALLENGE sem login/retry; isolar integração afetada; revalidação de contexto ao retomar |
| P1 — RDR-099 | Captura Shopee assistida preservando canal e granularidade | Card vs detalhe; shop_id/item_id público; preço/vendas/source/time; comissão por canal/base/extra sem universalizar “até”; zero score calculado por IA; revalidar produto antes de publicar |
| P1 — RDR-100/101 | Conversor atual Link personalizado e Sub IDs | Até 5 URLs/5 Sub IDs; charset alfanumérico; limites de comprimento ainda a investigar; mapa das posições; zero PII; rejeitar overflow/caracteres inválidos; comprovar roundtrip após geração autorizada |
| P1 — RDR-094/102 | Completar live de links em caso controlado | Obter autorização que mencione efeito ML em recomendações; revisar tracking teste; sucesso/erro/resultado/copy/full-short/redirect/contexto; repetição/idempotência e recuperação sem duplicar efeito |
| P1 — nova investigação vinculada RDR-077 | Completar biblioteca API depois de verificação humana | Schemas/campos, filtros/paginação por método, endpoint oficial, erros, auth singular/plural, rate scopes, feeds e relatórios validados. Não chamar explorer com sessão/cookie do portal |
| P1 — RDR-103..110 / SPIKE-04 | Recon WhatsApp independente | Aba WhatsApp e registro de canal sandbox necessários; excluir conversas privadas/QR; compositor/destino/hash/ambiguidade/sucesso; SIDE_EFFECT só com autorização explícita da issue |
| P2 — nova QA de evidências | Reexecutar candidatos no Chrome/VM e capturar regiões completas sanitizadas | Versionar registry, fixtures completas dos modais/resultados e scanner; validar primário/fallback sob mutação real, locale, SPA, suspensão MV3; nunca promover AUTO |

Não há prova de inviabilidade da arquitetura API-first; há bloqueio de conta. Não emitir redesenho global. Nome `Link personalizado` vs `Link de Conversão` e título ML atualizado são diferenças de superfície a incorporar ao detector, sem inventar capabilities.

## Ordem de dependências sugerida

1. Resolver contrato tracking ML, autorização do efeito adicional e entitlement Shopee.
2. Completar coleta de fixtures/resultados/estados negativos por capability; WhatsApp em spike separado.
3. Construir/testar detector, contexto e registry fail closed com providers Fake/fixtures.
4. Executar SAFE_LIVE opt-in no Chrome da VM.
5. Executar SIDE_EFFECT controlado autorizado, auditar e reconciliar resultados; só então aceitar adapter real.

## Handoff

Entregas: relatório consolidado; maps/matrices ML, Shopee e WhatsApp pendente; registry candidato; fixtures mínimas; verificador offline; atualização do Shopee Capability Report.

Testes: observações SAFE_LIVE de leitura/formulário descritas em E-*; verificação offline documentada em `VALIDATION.md`. Não executados: geração/validação de links, API autenticada, WhatsApp, testes de adapter, live Chrome/VM, persistência MV3/reboot/rede/soak — pelas lacunas e gates descritos.

Contratos: nenhum contrato normativo alterado; conflito e opções registrados para decisão. Migrations/config changes: nenhuma. Riscos: entitlement Shopee, bibliotecas API interrompidas pela verificação, identificação de variante/vendedor, efeito de recomendação ML, limites Sub ID desconhecidos, seletores observados apenas em uma sessão e ausência de resultado remoto. As alterações paralelas existentes no repositório foram preservadas.

Ao encerrar a leitura, abas de origem restauradas à Central ML e Oferta Shopee; produto ML preservado. As duas abas auxiliares abertas nesta investigação foram fechadas. Campos de teste limpos; nenhuma configuração ou etiqueta nova persistida.
