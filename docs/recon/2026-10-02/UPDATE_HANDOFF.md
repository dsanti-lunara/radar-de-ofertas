# Aplicação da revisão pós-recon — specs e issues

Data: **2026-10-03**, America/Sao_Paulo. Status: **APLICADA E VERIFICADA**. Operador autorizou alterar os specs e issues após a avaliação; entrega exclusivamente documental/tracker, sem iniciar implementação.

## Resultado

- SPEC-00/01/05/06/07 e índice atualizados; SPEC-02/03/04 preservam escopo/arquitetura.
- RECON-001..005 formalizam GROUP/capability/vínculo, tracking ML e três rotas Shopee. AUT-101/102 têm refinamento/supersessão explícitos, preservando histórico.
- Shopee API recorrente; portal manual/diagnóstico; captura pública assistida candidata. RDR-100 agora valida link gerado manualmente pelo operador; sem geração recorrente pelo Browser Bridge.
- WhatsApp usa PUBLISH_WHATSAPP_GROUP e destino GROUP. Identidade/reverificação segura permanece gate, sem inferir ID de nome/header/message-id. Serializer/hash/preflight e receipt/unknown result/dedupe seguem GRILL-001..003.
- Correções de integridade: marker/status ausentes são negativos futuros do adapter, não cobertura dos 14 verificadores atuais; E-SP-PUB-08 confirmou preço somente da opção 12L, sem comprovar opção preta/checkout/recorrência.
- 28 issues existentes atualizadas e relidas do GitHub para confirmar corpo, título, estado e label; 67 issues preservadas, nenhuma criada/fechada. Os 134 IDs RDR e AC aplicáveis foram mantidos; nenhum AC de produto foi marcado concluído.

## Issues atualizadas

[#20](https://github.com/dsanti-lunara/radar-de-ofertas/issues/20), [#24](https://github.com/dsanti-lunara/radar-de-ofertas/issues/24), [#36](https://github.com/dsanti-lunara/radar-de-ofertas/issues/36), [#37](https://github.com/dsanti-lunara/radar-de-ofertas/issues/37), [#38](https://github.com/dsanti-lunara/radar-de-ofertas/issues/38), [#39](https://github.com/dsanti-lunara/radar-de-ofertas/issues/39), [#40](https://github.com/dsanti-lunara/radar-de-ofertas/issues/40), [#41](https://github.com/dsanti-lunara/radar-de-ofertas/issues/41), [#42](https://github.com/dsanti-lunara/radar-de-ofertas/issues/42), [#44](https://github.com/dsanti-lunara/radar-de-ofertas/issues/44), [#45](https://github.com/dsanti-lunara/radar-de-ofertas/issues/45), [#46](https://github.com/dsanti-lunara/radar-de-ofertas/issues/46), [#47](https://github.com/dsanti-lunara/radar-de-ofertas/issues/47), [#48](https://github.com/dsanti-lunara/radar-de-ofertas/issues/48), [#49](https://github.com/dsanti-lunara/radar-de-ofertas/issues/49), [#50](https://github.com/dsanti-lunara/radar-de-ofertas/issues/50), [#51](https://github.com/dsanti-lunara/radar-de-ofertas/issues/51), [#52](https://github.com/dsanti-lunara/radar-de-ofertas/issues/52), [#53](https://github.com/dsanti-lunara/radar-de-ofertas/issues/53), [#54](https://github.com/dsanti-lunara/radar-de-ofertas/issues/54), [#55](https://github.com/dsanti-lunara/radar-de-ofertas/issues/55), [#58](https://github.com/dsanti-lunara/radar-de-ofertas/issues/58), [#62](https://github.com/dsanti-lunara/radar-de-ofertas/issues/62), [#63](https://github.com/dsanti-lunara/radar-de-ofertas/issues/63), [#64](https://github.com/dsanti-lunara/radar-de-ofertas/issues/64), [#65](https://github.com/dsanti-lunara/radar-de-ofertas/issues/65), [#66](https://github.com/dsanti-lunara/radar-de-ofertas/issues/66), [#67](https://github.com/dsanti-lunara/radar-de-ofertas/issues/67)

Títulos revisados de #36/#38/#39 descrevem consolidação do estudo já existente; #50 valida link manual; #52 prepara grupo cadastrado; #55 homologa destinos/grupos reais com autorização específica.

O label padrão `ready-for-human` não existia no repositório e foi criado conforme `docs/agents/triage-labels.md`. #37 recebeu esse label (removido ready-for-agent): entitlement e provisionamento seguro dependem do operador. Os demais tickets mantêm ready-for-agent para escopo especificado, sujeito a blockers/gates.

## Dependências verificadas no GitHub

| Ticket | Blockers nativos finais | Motivo |
|---|---|---|
| #48 | #20, #37 | Geração API exige contexto/Opportunity e gate API; discovery #47 não é obrigatório para produto capturado por outra rota. |
| #50 | #20, #49 | Link manual validado exige Opportunity/contexto assistido; não requer entitlement da API. |
| #51 | #35 | Além do blocker comum, exige uma rota alternativa comprovada: #47+#48 OU #49+#48 OU #49+#50. Não cadastrar alternativas como blockers cumulativos. |

Corpos, README/PUBLISHED e `publication-plan.json` foram sincronizados. A publicação foi retomável; snapshots antes/depois e hashes dos corpos estão em `.scratch/recon-update-2026-10-03/`. O manifesto registra `published-and-verified`.

## Verificações e limites

| Verificação | Resultado |
|---|---|
| `python docs/recon/2026-10-02/verify_recon_fixtures.py` | 6 PASS |
| `python docs/recon/2026-10-02/verify_followup_evidence.py` | 8 PASS |
| `.scratch/recon-update-2026-10-03/verify.py` | Estrutura das 28 issues, cobertura RDR-001..134/67 tickets, grafo sem ciclos e três rotas: PASS |
| Releitura GitHub | 28 corpos/títulos/labels OPEN iguais aos arquivos locais; 3 conjuntos de blockers nativos conferidos |
| `git diff --check` | Sem erros de whitespace; avisos de conversão LF/CRLF do Git |

Não executados: testes de produto/adapters, API autenticada, SAFE_LIVE Chrome/VM, SIDE_EFFECT, envio, recuperação real e soak. Motivo: tarefa de atualização documental; sistema/aceites não implementados ou liberados, acesso Shopee pendente. Verificadores/fixtures originais não foram alterados nem reinterpretados como aceite de produto.

Mudanças de contrato são documentais: capability GROUP; vínculo/receipt/preflight; separação tracking interno/externo; source de link manual; API/portal/público e erros/classificação fail closed. Schema_version final, schemas executáveis, migrations e runtime config pertencem à implementação; nenhum banco/config foi alterado nesta entrega. Stack permanece congelada.

## Blockers e riscos restantes

Entitlement/credenciais e auth/schema/limites reais Shopee; configuração/associação de etiqueta ML; identidade/reverificação de grupo; comprimento Sub IDs; fixtures completas/fallback/adapter; recovery persistente; Chrome/VM e soak. Em todas as rotas, dados atuais indisponíveis bloqueiam revalidação/publicação. Produção continua **NO-GO**, operação inicial SHADOW/ASSISTED e **AUTO não ativado**.

As alterações paralelas preexistentes foram preservadas; não houve staging, commit, reset ou limpeza. Este handoff é o registro da revisão documental, não conclusão técnica das issues.

## Arquivos atualizados

### Specs

- `docs/specs/00-delivery.md`
- `docs/specs/01-foundation-domain.md`
- `docs/specs/05-publication-recovery.md`
- `docs/specs/06-browser-marketplaces.md`
- `docs/specs/07-operations-acceptance.md`
- `docs/specs/README.md`

### Contratos, decisões e operação

- `CONTEXT.md`
- `docs/00_SDD_MASTER.md`
- `docs/04_DATA_CONTRACTS.md`
- `docs/07_BROWSER_BRIDGE.md`
- `docs/09_PUBLISHING.md`
- `docs/10_PERSISTENCE_AND_RECOVERY.md`
- `docs/12_SECURITY_AND_COMPLIANCE.md`
- `docs/13_QA_ACCEPTANCE_MATRIX.md`
- `docs/14_DELIVERY_PLAN.md`
- `docs/BROWSER_RECONNAISSANCE.md`
- `docs/DECISION_LOG.md`
- `docs/ERROR_CATALOG.md`
- `docs/ISSUE_MAP.md`
- `docs/SHOPEE_CAPABILITY_REPORT.md`

### Evidência e revisão

- `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`
- `docs/recon/2026-10-02/GAP_REPORT.md`
- `docs/recon/2026-10-02/PRODUCTION_READINESS.md`
- `docs/recon/2026-10-02/SPEC_ISSUE_REVIEW.md`
- `docs/recon/2026-10-02/SP_CAPABILITY_MATRIX.md`
- `docs/recon/2026-10-02/UPDATE_HANDOFF.md`
- `docs/recon/2026-10-02/VALIDATION.md`
- `docs/recon/2026-10-02/WA_CAPABILITY_MATRIX.md`

### Espelhos de tickets e rastreabilidade

- `.scratch/radar-v1/PUBLISHED.md`
- `.scratch/radar-v1/README.md`
- `.scratch/radar-v1/issues/20-gerar-link-fake-com-trackingcontext-auditavel.md`
- `.scratch/radar-v1/issues/24-suspender-envio-de-resultado-desconhecido.md`
- `.scratch/radar-v1/issues/36-investigar-ml-e-validar-fixtures-de-navegador.md`
- `.scratch/radar-v1/issues/37-validar-shopee-affiliate-api-da-conta-spike-02.md`
- `.scratch/radar-v1/issues/38-investigar-shopee-e-validar-fixtures-de-navegador.md`
- `.scratch/radar-v1/issues/39-investigar-whatsapp-channels-e-validar-fixtures.md`
- `.scratch/radar-v1/issues/40-parear-browser-bridge-e-consultar-heartbeat.md`
- `.scratch/radar-v1/issues/41-executar-job-browser-seguro-e-persistente.md`
- `.scratch/radar-v1/issues/42-detectar-pagina-e-emitir-diagnostico-sanitizado.md`
- `.scratch/radar-v1/issues/44-capturar-ml-pelo-navegador-com-contexto-correto.md`
- `.scratch/radar-v1/issues/45-gerar-link-afiliado-ml-pelo-fluxo-validado.md`
- `.scratch/radar-v1/issues/46-validar-slice-3-ml-ate-telegram-sandbox.md`
- `.scratch/radar-v1/issues/47-descobrir-shopee-por-api-validada.md`
- `.scratch/radar-v1/issues/48-gerar-link-shopee-por-api-e-sub-ids.md`
- `.scratch/radar-v1/issues/49-capturar-shopee-de-forma-assistida.md`
- `.scratch/radar-v1/issues/50-gerar-link-shopee-pelo-fallback-assistido.md`
- `.scratch/radar-v1/issues/51-validar-slice-3-shopee-ate-telegram-sandbox.md`
- `.scratch/radar-v1/issues/52-preparar-mensagem-whatsapp-no-canal-certo.md`
- `.scratch/radar-v1/issues/53-enviar-whatsapp-em-assisted-com-revisao-explicita.md`
- `.scratch/radar-v1/issues/54-validar-slice-4-whatsapp-sandbox.md`
- `.scratch/radar-v1/issues/55-homologar-canais-reais-em-assisted.md`
- `.scratch/radar-v1/issues/58-aplicar-retencao-e-protecao-contra-disco-critico.md`
- `.scratch/radar-v1/issues/62-validar-perda-de-rede-e-recuperacao-isolada.md`
- `.scratch/radar-v1/issues/63-homologar-reboot-e-restart-na-vm-alvo.md`
- `.scratch/radar-v1/issues/64-fechar-matriz-de-seguranca-e-compliance.md`
- `.scratch/radar-v1/issues/65-executar-piloto-shadow-de-24-horas.md`
- `.scratch/radar-v1/issues/66-executar-soak-estendido-e-avaliar-estabilidade.md`
- `.scratch/radar-v1/issues/67-auditar-readiness-da-v1-e-entregar-operacao-controlada.md`
- `.scratch/radar-v1/publication-plan.json`
