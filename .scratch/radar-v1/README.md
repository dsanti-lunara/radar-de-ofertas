# Radar V1 — 67 tickets publicados e revisão pós-recon

Status: 67 tickets publicados e verificados em 2026-10-02 no GitHub, issues #1–#67, com referências reais e blocking nativo; revisão 2026-10-03 mantém `ready-for-agent` conforme gates e encaminha TKT-37 para `ready-for-human`. Consulte [PUBLISHED.md](PUBLISHED.md) para as URLs e `publication-plan.json` para o manifesto retomável. Nenhuma implementação foi iniciada.

## Organização

- Cobertura de RDR-001..RDR-134 preservada em 67 tickets de comportamento verificável, com integração ou investigação completa no escopo de cada um.
- RDR-076/124/125 divididos em três investigações ML/SP/WA; demais IDs têm um ticket responsável. Referências cruzadas não renumeram RDRs.
- A ordem numérica é topológica: blockers aparecem antes. Ela não força serialização de tickets independentes.
- Primeira fronteira: TKT-01; SPIKE-01/TKT-29 e investigações TKT-36/37/38/39 podem iniciar independentemente quando ambiente/acesso humano estiver disponível.
- TKT-23 demonstra Slice 1 Fake; TKT-35 demonstra Slice 2; TKT-46/51 demonstram Slice 3 por marketplace; TKT-54 demonstra Slice 4 WhatsApp sandbox.
- TKT-51 exige uma rota Shopee suportada: TKT-47+48 OU TKT-49+48 OU TKT-49+50 (link manual validado), escolhida com evidência por capability; SPIKE-02 exigido nas rotas API, sem exigir as três rotas cumulativamente.
- Capabilities desconhecidas impedem implementação dependente até resolução do gate; specs/tickets não autorizam side effects reais nem AUTO.
- Sem prefactoring de código: repo ainda documental; TKT-01 estabelece a primeira base executável.

## Breakdown vigente

1. **Inicializar o Radar e consultar saúde local** — **Bloqueado por:** nenhum ticket. **Entrega:** Iniciar Core/API locais com banco migrado e consultar saúde por CLI/API, com toolchains Python/TypeScript verificáveis. [Ticket completo](issues/01-inicializar-o-radar-e-consultar-saude-local.md).

2. **Carregar configuração e proteger segredos** — **Bloqueado por:** TKT-01. **Entrega:** Inicializar o Radar com configuração validada e acesso least-privilege a secrets; emitir logs estruturados sanitizados. [Ticket completo](issues/02-carregar-configuracao-e-proteger-segredos.md).

3. **Capturar oferta manual com proveniência** — **Bloqueado por:** TKT-02. **Entrega:** Receber uma captura manual pelo contrato público, persistir RawCapture/Evidence e consultar o Candidate resultante. [Ticket completo](issues/03-capturar-oferta-manual-com-proveniencia.md).

4. **Consultar histórico próprio de preços** — **Bloqueado por:** TKT-03. **Entrega:** Acrescentar observações monetárias e consultar histórico do MarketplaceProduct com proveniência. [Ticket completo](issues/04-consultar-historico-proprio-de-precos.md).

5. **Classificar categoria e adequação às marcas** — **Bloqueado por:** TKT-03. **Entrega:** Classificar um Candidate e consultar Brand Fit explicável para Radar Beauty e Casa em Ordem. [Ticket completo](issues/05-classificar-categoria-e-adequacao-as-marcas.md).

6. **Avaliar oportunidade de preço** — **Bloqueado por:** TKT-04. **Entrega:** Calcular Price Opportunity consultável usando histórico e condições confirmadas do Candidate. [Ticket completo](issues/06-avaliar-oportunidade-de-preco.md).

7. **Avaliar qualidade do vendedor** — **Bloqueado por:** TKT-03. **Entrega:** Consultar Seller Quality com componentes independentes e origem de cada sinal. [Ticket completo](issues/07-avaliar-qualidade-do-vendedor.md).

8. **Avaliar demanda por categoria** — **Bloqueado por:** TKT-05. **Entrega:** Consultar Demand de um Candidate usando apenas sinais disponíveis e normalização configurada. [Ticket completo](issues/08-avaliar-demanda-por-categoria.md).

9. **Decidir Candidate com scores e Hard Rules** — **Bloqueado por:** TKT-06, TKT-07, TKT-08. **Entrega:** Avaliar Candidate pela matriz determinística e consultar Evaluation imutável com Deal, Monetization e Confidence. [Ticket completo](issues/09-decidir-candidate-com-scores-e-hard-rules.md).

10. **Comparar fonte de compra sem favorecer comissão** — **Bloqueado por:** TKT-09. **Entrega:** Comparar ofertas confiáveis do mesmo Product e impedir seleção afiliada materialmente pior. [Ticket completo](issues/10-comparar-fonte-de-compra-sem-favorecer-comissao.md).

11. **Produzir claims comerciais verificáveis** — **Bloqueado por:** TKT-04, TKT-09. **Entrega:** Consultar allowed_claims de uma avaliação com a Evidence necessária para cada afirmação. [Ticket completo](issues/11-produzir-claims-comerciais-verificaveis.md).

12. **Impedir duplicação e autorizar repost elegível** — **Bloqueado por:** TKT-09. **Entrega:** Avaliar se uma oferta pode voltar ao fluxo conforme mudança material e histórico de publicação. [Ticket completo](issues/12-impedir-duplicacao-e-autorizar-repost-elegivel.md).

13. **Executar job local com claim e lease** — **Bloqueado por:** TKT-02. **Entrega:** Enfileirar trabalho seguro, reivindicá-lo e consultar resultado persistido sem execução concorrente equivalente. [Ticket completo](issues/13-executar-job-local-com-claim-e-lease.md).

14. **Recuperar retries e encaminhar Dead Jobs** — **Bloqueado por:** TKT-13. **Entrega:** Consultar tentativas, tratar falhas por classe e receber HumanAction quando exige intervenção. [Ticket completo](issues/14-recuperar-retries-e-encaminhar-dead-jobs.md).

15. **Agendar sem executar ticks perdidos em massa** — **Bloqueado por:** TKT-13. **Entrega:** Criar schedules INTERVAL/CRON/ON_DEMAND que geram jobs observáveis sem sobreposição. [Ticket completo](issues/15-agendar-sem-executar-ticks-perdidos-em-massa.md).

16. **Criar Opportunity pelo Workflow Engine** — **Bloqueado por:** TKT-09, TKT-14. **Entrega:** Avançar Candidate avaliado até Opportunity apenas quando aprovado, com transições e ações humanas explícitas. [Ticket completo](issues/16-criar-opportunity-pelo-workflow-engine.md).

17. **Controlar SHADOW, ASSISTED e interrupção externa** — **Bloqueado por:** TKT-16. **Entrega:** Operar políticas de autonomia e comandos pause/drain/kill sem publicação involuntária. [Ticket completo](issues/17-controlar-shadow-assisted-e-interrupcao-externa.md).

18. **Recuperar jobs seguros após crash** — **Bloqueado por:** TKT-14, TKT-15, TKT-17. **Entrega:** Reiniciar o Core, reconciliar jobs locais e retomar somente trabalho seguro sem loops ou leases órfãos. [Ticket completo](issues/18-recuperar-jobs-seguros-apos-crash.md).

19. **Revisar Candidate com IA Fake e Knowledge versionado** — **Bloqueado por:** TKT-11, TKT-16. **Entrega:** Executar Editorial Review Fake com contexto mínimo de marca/canal e consultar decisão estruturada armazenada. [Ticket completo](issues/19-revisar-candidate-com-ia-fake-e-knowledge-versionado.md).

20. **Gerar link Fake com TrackingContext auditável** — **Bloqueado por:** TKT-17. **Entrega:** Criar e consultar AffiliateLink Fake apenas para Opportunity aprovada, com tracking separado e sem PII. [Ticket completo](issues/20-gerar-link-fake-com-trackingcontext-auditavel.md).

21. **Gerar preview validado sem inventar fatos** — **Bloqueado por:** TKT-19, TKT-20. **Entrega:** Gerar ContentGeneration Fake e renderizar preview com preço, link e disclosure determinados pelo backend. [Ticket completo](issues/21-gerar-preview-validado-sem-inventar-fatos.md).

22. **Reutilizar IA somente quando contexto equivale** — **Bloqueado por:** TKT-21. **Entrega:** Reprocessar entrada equivalente sem nova geração e invalidar cache quando fatos ou versões mudam. [Ticket completo](issues/22-reutilizar-ia-somente-quando-contexto-equivale.md).

23. **Concluir Slice 1 com publicação Fake idempotente** — **Bloqueado por:** TKT-12, TKT-17, TKT-18, TKT-21. **Entrega:** Completar oferta manual/Fake → scoring real → IA Fake → link Fake → publicação Fake consultável. [Ticket completo](issues/23-concluir-slice-1-com-publicacao-fake-idempotente.md).

24. **Suspender envio de resultado desconhecido** — **Bloqueado por:** TKT-23. **Entrega:** Recuperar crash após aceitação remota sem confirmação local, suspendendo publicação e abrindo revisão humana. [Ticket completo](issues/24-suspender-envio-de-resultado-desconhecido.md).

25. **Consultar saúde pelo Control Center** — **Bloqueado por:** TKT-02. **Entrega:** Abrir Control Center local e consultar saúde real do Core/DB e dependências pela API. [Ticket completo](issues/25-consultar-saude-pelo-control-center.md).

26. **Revisar oportunidades na UI sem autorizar envio** — **Bloqueado por:** TKT-19, TKT-25. **Entrega:** Listar Candidate/Opportunity, consultar Evidence/breakdown e registrar review humana pela UI. [Ticket completo](issues/26-revisar-oportunidades-na-ui-sem-autorizar-envio.md).

27. **Consultar e aprovar publicação na UI** — **Bloqueado por:** TKT-24, TKT-25. **Entrega:** Visualizar preview e timeline de Publication e autorizar publicação em ASSISTED com guardrails ativos. [Ticket completo](issues/27-consultar-e-aprovar-publicacao-na-ui.md).

28. **Operar HumanActions, jobs e configurações na UI** — **Bloqueado por:** TKT-14, TKT-17, TKT-25. **Entrega:** Resolver ações humanas e controlar estado do Radar sem SQL direto. [Ticket completo](issues/28-operar-humanactions-jobs-e-configuracoes-na-ui.md).

29. **Validar acesso oficial à IA (SPIKE-01)** — **Bloqueado por:** nenhum ticket. **Entrega:** Produzir evidência do provider/auth real elegível e de suas capacidades/limites antes do adapter. [Ticket completo](issues/29-validar-acesso-oficial-a-ia-spike-01.md).

30. **Integrar provider IA real aprovado** — **Bloqueado por:** TKT-19, TKT-29. **Entrega:** Executar Editorial Review/generation pelo provider validado, com auth isolada e falhas acionáveis. [Ticket completo](issues/30-integrar-provider-ia-real-aprovado.md).

31. **Validar IA com datasets editorial e adversarial** — **Bloqueado por:** TKT-21. **Entrega:** Executar suite reprodutível que mede propriedades editoriais e resistência a conteúdo adversarial. [Ticket completo](issues/31-validar-ia-com-datasets-editorial-e-adversarial.md).

32. **Publicar Telegram pelo contrato com sandbox bloqueado por padrão** — **Bloqueado por:** TKT-21, TKT-24. **Entrega:** Implementar TelegramPublisher/Bot API com testes seguros e preparo de destinos sandbox explícitos. [Ticket completo](issues/32-publicar-telegram-pelo-contrato-com-sandbox-bloqueado-por-padrao.md).

33. **Editar e expirar publicação Telegram** — **Bloqueado por:** TKT-32. **Entrega:** Revalidar publicação confirmada e atualizar/expirar mensagem preservando revisions. [Ticket completo](issues/33-editar-e-expirar-publicacao-telegram.md).

34. **Notificar o operador em destino privado** — **Bloqueado por:** TKT-28, TKT-32. **Entrega:** Enviar alertas operacionais acionáveis em destino privado explicitamente cadastrado. [Ticket completo](issues/34-notificar-o-operador-em-destino-privado.md).

35. **Validar Slice 2 com IA real e Telegram sandbox** — **Bloqueado por:** TKT-30, TKT-31, TKT-32. **Entrega:** Executar manual/Fake offer com scoring real, IA real e Telegram sandbox autorizado, comprovando preço/link/disclosure e falhas. [Ticket completo](issues/35-validar-slice-2-com-ia-real-e-telegram-sandbox.md).

36. **Consolidar recon ML e validar fixtures** — **Bloqueado por:** nenhum ticket. **Entrega:** Consolidar o recon ML finalizado em 2026-10-02, adotar mapas/fixtures candidatos, testar artefatos e registrar gaps de implementação/homologação sem repetir investigação completa ou gerar novos links. [Ticket completo](issues/36-investigar-ml-e-validar-fixtures-de-navegador.md).

37. **Validar Shopee Affiliate API da conta (SPIKE-02)** — **Bloqueado por:** nenhum ticket. **Entrega:** Determinar capabilities realmente disponíveis na conta Brasil e atualizar relatório sem implementar adapter. [Ticket completo](issues/37-validar-shopee-affiliate-api-da-conta-spike-02.md).

38. **Consolidar recon Shopee e validar fixtures** — **Bloqueado por:** nenhum ticket. **Entrega:** Consolidar o recon Shopee API/portal/site público finalizado; separar superfícies e adotar fixtures/evidências existentes, registrando gaps sem automatizar o portal afiliado ou presumir API da conta disponível. [Ticket completo](issues/38-investigar-shopee-e-validar-fixtures-de-navegador.md).

39. **Consolidar recon WhatsApp Groups e validar fixtures** — **Bloqueado por:** nenhum ticket. **Entrega:** Consolidar o recon WhatsApp Groups finalizado, adotar projeções sanitizadas do grupo sandbox e registrar identidade/serializer/fallback/recovery pendentes. O envio técnico histórico autorizado não autoriza novo envio. [Ticket completo](issues/39-investigar-whatsapp-channels-e-validar-fixtures.md).

40. **Parear Browser Bridge e consultar heartbeat** — **Bloqueado por:** TKT-02. **Entrega:** Instalar extensão MV3 mínima, parear com Core e ver conectividade no popup/API local sem executar comandos de marketplace. [Ticket completo](issues/40-parear-browser-bridge-e-consultar-heartbeat.md).

41. **Executar job Browser seguro e persistente** — **Bloqueado por:** TKT-13, TKT-40. **Entrega:** Entregar comandos allowlisted ao Bridge com persistência e anti-replay, verificável em página controlada. [Ticket completo](issues/41-executar-job-browser-seguro-e-persistente.md).

42. **Detectar página e emitir diagnóstico sanitizado** — **Bloqueado por:** TKT-41. **Entrega:** Executar page detection de framework em fixtures controladas e emitir diagnóstico de estado/DOM sem segredos. [Ticket completo](issues/42-detectar-pagina-e-emitir-diagnostico-sanitizado.md).

43. **Descobrir ML por API oficial e normalizar Candidate** — **Bloqueado por:** TKT-03, TKT-16. **Entrega:** Trazer uma oferta ML por capability oficial documentada e consultá-la como Candidate com fonte preservada. [Ticket completo](issues/43-descobrir-ml-por-api-oficial-e-normalizar-candidate.md).

44. **Capturar ML pelo navegador com contexto correto** — **Bloqueado por:** TKT-36, TKT-42. **Entrega:** Reconhecer páginas ML reais validadas, detectar sessão e capturar produto sem clique em contexto errado. [Ticket completo](issues/44-capturar-ml-pelo-navegador-com-contexto-correto.md).

45. **Gerar link afiliado ML pelo fluxo validado** — **Bloqueado por:** TKT-20, TKT-44. **Entrega:** Gerar AffiliateLink ML auditável pelo Gerador de Links, com fallback Barra somente se validado. [Ticket completo](issues/45-gerar-link-afiliado-ml-pelo-fluxo-validado.md).

46. **Validar Slice 3 ML até Telegram sandbox** — **Bloqueado por:** TKT-35, TKT-43, TKT-45. **Entrega:** Executar oferta ML real → avaliação → link validado → IA real → sandbox, sem envio comercial. [Ticket completo](issues/46-validar-slice-3-ml-ate-telegram-sandbox.md).

47. **Descobrir Shopee por API validada** — **Bloqueado por:** TKT-03, TKT-16, TKT-37. **Entrega:** Implementar contratos/Fake e normalização Shopee pela documentação oficial Brasil; validar captura API real somente após entitlement/SPIKE-02 e aceites específicos. Sem acesso, expor capability indisponível sem declarar NOT_SUPPORTED global. [Ticket completo](issues/47-descobrir-shopee-por-api-validada.md).

48. **Gerar link Shopee por API e Sub IDs** — **Bloqueado por:** TKT-20, TKT-37. **Entrega:** Gerar AffiliateLink Shopee por API oficial a partir de Opportunity aprovada e contexto/tracking verificáveis, independentemente da rota que capturou o produto. Contratos/Fake primeiro; API autenticada depende de SPIKE-02. [Ticket completo](issues/48-gerar-link-shopee-por-api-e-sub-ids.md).

49. **Capturar Shopee de forma assistida** — **Bloqueado por:** TKT-03, TKT-38, TKT-42. **Entrega:** Capturar Shopee publicamente de forma assistida, por listas/filtros/campanha vigente e detalhe/variante, preservando RawCapture/Evidence/Candidate e CHALLENGE/HumanAction. Portal afiliado permanece manual/diagnóstico. [Ticket completo](issues/49-capturar-shopee-de-forma-assistida.md).

50. **Validar link Shopee gerado manualmente** — **Bloqueado por:** TKT-20, TKT-49. **Entrega:** Validar e persistir retorno literal de link Shopee gerado manualmente pelo operador no portal, após Opportunity aprovada, com contexto/tracking/evidência verificáveis. O Radar não automatiza a geração no portal nem usa essa rota para contornar bloqueios. [Ticket completo](issues/50-gerar-link-shopee-pelo-fallback-assistido.md).

51. **Validar Slice 3 Shopee até Telegram sandbox** — **Bloqueado por:** TKT-35; uma rota alternativa 47+48, 49+48 ou 49+50. **Entrega:** Comprovar uma rota Shopee validada até Telegram sandbox: captura API+link API, captura pública assistida+link API ou captura assistida+link manual validado, sempre com revalidação atual e guards. [Ticket completo](issues/51-validar-slice-3-shopee-ate-telegram-sandbox.md).

52. **Preparar mensagem WhatsApp no grupo cadastrado** — **Bloqueado por:** TKT-21, TKT-39, TKT-42. **Entrega:** Abrir grupo WhatsApp cadastrado com vínculo/identidade verificados e preparar preview canônico sem enviar, validando marca, destino e message hash; vínculo não provado bloqueia a fronteira de envio. [Ticket completo](issues/52-preparar-mensagem-whatsapp-no-canal-certo.md).

53. **Enviar WhatsApp em ASSISTED com revisão explícita** — **Bloqueado por:** TKT-24, TKT-27, TKT-52. **Entrega:** Autorizar publicação específica e enviar por Bridge somente após verificar contexto imediato. [Ticket completo](issues/53-enviar-whatsapp-em-assisted-com-revisao-explicita.md).

54. **Validar Slice 4 WhatsApp sandbox** — **Bloqueado por:** TKT-35, TKT-53. **Entrega:** Comprovar envio único em grupo sandbox cadastrado com preço/link/disclosure corretos e revisão ASSISTED. [Ticket completo](issues/54-validar-slice-4-whatsapp-sandbox.md).

55. **Homologar destinos reais e grupos WhatsApp em ASSISTED** — **Bloqueado por:** TKT-54. **Entrega:** Validar readiness e, somente com autorização específica, operação controlada nos canais reais das marcas. [Ticket completo](issues/55-homologar-canais-reais-em-assisted.md).

56. **Criar backup consistente verificável** — **Bloqueado por:** TKT-04, TKT-23. **Entrega:** Produzir pacote verificável de SQLite/config/knowledge e consultar status/health do backup. [Ticket completo](issues/56-criar-backup-consistente-verificavel.md).

57. **Restaurar sem repetir publicações pós-backup** — **Bloqueado por:** TKT-24, TKT-56. **Entrega:** Restaurar explicitamente banco/config/knowledge e retomar trabalho seguro com envios bloqueados até reconciliação. [Ticket completo](issues/57-restaurar-sem-repetir-publicacoes-pos-backup.md).

58. **Aplicar retenção e proteção contra disco crítico** — **Bloqueado por:** TKT-02, TKT-56. **Entrega:** Limpar diagnostics/logs expirados com segurança e pausar discovery quando espaço permanecer crítico. [Ticket completo](issues/58-aplicar-retencao-e-protecao-contra-disco-critico.md).

59. **Diagnosticar instalação com radarctl doctor** — **Bloqueado por:** TKT-28, TKT-40, TKT-56, TKT-58. **Entrega:** Consultar diagnóstico read-only de DB/config/knowledge/disk/backup e integrações pelo CLI. [Ticket completo](issues/59-diagnosticar-instalacao-com-radarctl-doctor.md).

60. **Instalar Execution Node com auto-start seguro** — **Bloqueado por:** TKT-25, TKT-40, TKT-59. **Entrega:** Instalar Radar na VM Linux alvo e iniciar Core/API/Chrome dedicados com health verificável. [Ticket completo](issues/60-instalar-execution-node-com-auto-start-seguro.md).

61. **Atualizar e reverter release com salvaguardas** — **Bloqueado por:** TKT-57, TKT-60. **Entrega:** Deployar versão e recuperar falha de upgrade usando drain/backup/validation sem enviar com DB incompatível. [Ticket completo](issues/61-atualizar-e-reverter-release-com-salvaguardas.md).

62. **Validar perda de rede e recuperação isolada** — **Bloqueado por:** TKT-30, TKT-32, TKT-41, TKT-53. **Entrega:** Simular outage/retorno de AI, Telegram e Browser sem perder estado ou reenviar mensagens incertas. [Ticket completo](issues/62-validar-perda-de-rede-e-recuperacao-isolada.md).

63. **Homologar reboot e restart na VM alvo** — **Bloqueado por:** TKT-18, TKT-57, TKT-61, TKT-62. **Entrega:** Reiniciar VM/browser e simular terminação abrupta preservando recovery e autorização. [Ticket completo](issues/63-homologar-reboot-e-restart-na-vm-alvo.md).

64. **Fechar matriz de segurança e compliance** — **Bloqueado por:** TKT-10, TKT-22, TKT-24, TKT-28, TKT-45, TKT-48, TKT-50, TKT-53, TKT-57. **Entrega:** Executar acceptance de segurança nas fronteiras reais do sistema e provar fail-closed. [Ticket completo](issues/64-fechar-matriz-de-seguranca-e-compliance.md).

65. **Executar piloto SHADOW de 24 horas** — **Bloqueado por:** TKT-31, TKT-46, TKT-51, TKT-54, TKT-58, TKT-63, TKT-64. **Entrega:** Operar 24h SHADOW com dados reais e decisões humanas, registrando recursos e estabilidade sem envio comercial. [Ticket completo](issues/65-executar-piloto-shadow-de-24-horas.md).

66. **Executar soak estendido e avaliar estabilidade** — **Bloqueado por:** TKT-65. **Entrega:** Estender ensaio conforme QA e consolidar falhas/recuperações antes de readiness. [Ticket completo](issues/66-executar-soak-estendido-e-avaliar-estabilidade.md).

67. **Auditar readiness da V1 e entregar operação controlada** — **Bloqueado por:** TKT-33, TKT-34, TKT-55, TKT-66. **Entrega:** Consolidar todos os gates técnicos, operacionais e compliance para concluir V1 sem autorizar AUTO. [Ticket completo](issues/67-auditar-readiness-da-v1-e-entregar-operacao-controlada.md).

## Cobertura canônica

- RDR-001 → TKT-01
- RDR-002 → TKT-01
- RDR-003 → TKT-01
- RDR-004 → TKT-02
- RDR-005 → TKT-02
- RDR-006 → TKT-01
- RDR-007 → TKT-01
- RDR-008 → TKT-02
- RDR-009 → TKT-01
- RDR-010 → TKT-01
- RDR-011 → TKT-03
- RDR-012 → TKT-03
- RDR-013 → TKT-04
- RDR-014 → TKT-03
- RDR-015 → TKT-03
- RDR-016 → TKT-09
- RDR-017 → TKT-16
- RDR-018 → TKT-20
- RDR-019 → TKT-21
- RDR-020 → TKT-23
- RDR-021 → TKT-03
- RDR-022 → TKT-05
- RDR-023 → TKT-06
- RDR-024 → TKT-07
- RDR-025 → TKT-08
- RDR-026 → TKT-05
- RDR-027 → TKT-09
- RDR-028 → TKT-09
- RDR-029 → TKT-09
- RDR-030 → TKT-09
- RDR-031 → TKT-10
- RDR-032 → TKT-11
- RDR-033 → TKT-12
- RDR-034 → TKT-13
- RDR-035 → TKT-13
- RDR-036 → TKT-13
- RDR-037 → TKT-14
- RDR-038 → TKT-14
- RDR-039 → TKT-15
- RDR-040 → TKT-14
- RDR-041 → TKT-16
- RDR-042 → TKT-18
- RDR-043 → TKT-17
- RDR-044 → TKT-17
- RDR-045 → TKT-19
- RDR-046 → TKT-19
- RDR-047 → TKT-19
- RDR-048 → TKT-29
- RDR-049 → TKT-30
- RDR-050 → TKT-19
- RDR-051 → TKT-21
- RDR-052 → TKT-21
- RDR-053 → TKT-21
- RDR-054 → TKT-21
- RDR-055 → TKT-22
- RDR-056 → TKT-25
- RDR-057 → TKT-25
- RDR-058 → TKT-26
- RDR-059 → TKT-26
- RDR-060 → TKT-26
- RDR-061 → TKT-27
- RDR-062 → TKT-27
- RDR-063 → TKT-28
- RDR-064 → TKT-28
- RDR-065 → TKT-28
- RDR-066 → TKT-28
- RDR-067 → TKT-28
- RDR-068 → TKT-32
- RDR-069 → TKT-21
- RDR-070 → TKT-20
- RDR-071 → TKT-32
- RDR-072 → TKT-23
- RDR-073 → TKT-33
- RDR-074 → TKT-34
- RDR-075 → TKT-35
- RDR-076 → TKT-36, TKT-38, TKT-39
- RDR-077 → TKT-37
- RDR-078 → TKT-40
- RDR-079 → TKT-40
- RDR-080 → TKT-40
- RDR-081 → TKT-41
- RDR-082 → TKT-41
- RDR-083 → TKT-42
- RDR-084 → TKT-41
- RDR-085 → TKT-42
- RDR-086 → TKT-40
- RDR-087 → TKT-43
- RDR-088 → TKT-43
- RDR-089 → TKT-43
- RDR-090 → TKT-44
- RDR-091 → TKT-44
- RDR-092 → TKT-45
- RDR-093 → TKT-44
- RDR-094 → TKT-46
- RDR-095 → TKT-47
- RDR-096 → TKT-47
- RDR-097 → TKT-48
- RDR-098 → TKT-49
- RDR-099 → TKT-49
- RDR-100 → TKT-50
- RDR-101 → TKT-48
- RDR-102 → TKT-51
- RDR-103 → TKT-52
- RDR-104 → TKT-52
- RDR-105 → TKT-52
- RDR-106 → TKT-52
- RDR-107 → TKT-52
- RDR-108 → TKT-53
- RDR-109 → TKT-52
- RDR-110 → TKT-54
- RDR-111 → TKT-55
- RDR-112 → TKT-56
- RDR-113 → TKT-57
- RDR-114 → TKT-58
- RDR-115 → TKT-58
- RDR-116 → TKT-59
- RDR-117 → TKT-60
- RDR-118 → TKT-60
- RDR-119 → TKT-60
- RDR-120 → TKT-61
- RDR-121 → TKT-61
- RDR-122 → TKT-31
- RDR-123 → TKT-31
- RDR-124 → TKT-36, TKT-38, TKT-39
- RDR-125 → TKT-36, TKT-38, TKT-39
- RDR-126 → TKT-64
- RDR-127 → TKT-18
- RDR-128 → TKT-24
- RDR-129 → TKT-62
- RDR-130 → TKT-57
- RDR-131 → TKT-63
- RDR-132 → TKT-65
- RDR-133 → TKT-66
- RDR-134 → TKT-67

## Publicação após aprovação

Tracker: dsanti-lunara/radar-de-ofertas; um issue por ticket, blockers primeiro; label ready-for-agent conforme skill. Usar relações nativas de blocking onde disponíveis; manter Blocked by com referências reais para transparência e para a dependência alternativa Shopee. Não criar/alterar/fechar parent issues inexistentes.

Verificar novamente duplicações e autorização do transporte. A sessão anterior teve criação via conector bloqueada por approval policy never; não tratar rascunho ou comando preparado como publicação concluída. Registrar number/url de cada issue criada num manifesto, incluindo cobertura e blockers, e retomar idempotentemente se a publicação parar.

## Aprovação e conclusão

Granularidade e blocking edges aprovados em 2026-10-02; retomada da publicação autorizada explicitamente. Publicação concluída com verificação de título, body e label por issue. A publicação não inicia implementação nem autoriza side effects reais ou AUTO.
