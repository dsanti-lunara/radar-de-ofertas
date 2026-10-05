# Aprovação para produção — gates e antecipações

Status: **NO-GO para produção; investigação utilizável para planejamento**. Fontes atuais: [SDD Master](../../00_SDD_MASTER.md), [QA Matrix](../../13_QA_ACCEPTANCE_MATRIX.md), [Decision Log](../../DECISION_LOG.md), [recon consolidado](BROWSER_RECON_COMPLETION.md). Estado do diretório nesta sessão: documentação/contratos e verificadores de evidência; nenhum runtime/adapters de produto encontrado no inventário de arquivos. Não confundir testes do pacote com testes do sistema. Na fase de investigação o tracker remoto não foi auditado; IDs RDR são locais. A revisão documental posterior de 2026-10-03 consultou #1–#67 e reconcilia contratos/specs/issues (UPDATE_HANDOFF.md); isso não aprova os gates de produção abaixo.

## O que pode ser adiantado agora

- [Guia de URLs e percurso de discovery](DISCOVERY_URL_GUIDE.md), com campaign IDs temporários e estados obrigatórios; não é configuração runtime.

- Evidência adicional do site público Shopee: home, lista relâmpago e filtro de beleza acessíveis nesta visita, sem challenge observado. [Resultados e seletores candidatos](SHOPEE_PUBLIC_FINDINGS.md).
- Casa e Cozinha confirmada; detalhe público apresentou Verifique para continuar após renderização inicial. A revalidação browser não está aprovada; planejar CHALLENGE/HumanAction e isolar lista/detalhe, sem contornar proteção.
- Após CAPTCHA humano, detalhe retomou e preço coincidiu com card para 12L; variante preta não confirmada. Não há solução comprovada para acesso sem CAPTCHA; compatibilidade manual/assistida e orçamento de intervenções continuam investigação própria.
- Planejar providers API/contratos/Fake com os [oito métodos oficiais](API_DOCUMENTATION_FINDINGS.md), sem aguardar credenciais.
- Preparar revisão de SDDs/issues para Groups, separar hosts Shopee e resolver tracking ML. A decisão Groups já foi tomada pelo usuário; falta refletir nos contratos. Este documento não altera silenciosamente capabilities normativas.
- Preparar testes negativos e falhas determinísticas em ambientes Fake/fixture; reservar testes live para implementação e destinos controlados.

## Gates de aprovação e evidência exigida

| Gate | O que falta | Evidência para aprovar | Dependência/quem executa |
|---|---|---|---|
| G1 — contratos coerentes | Channels → Groups; identidade/pareamento do grupo; ML etiqueta lowercase/30 e mapeamento; Shopee portal manual/API/site público separado | Docs/contratos/issues coerentes; AC e testes rastreáveis; resolução explícita de conflitos | Revisão documental do projeto; identidade exige solução permitida ou pareamento humano persistente |
| G2 — sistema implementado | Core, API, banco/migrations, bridge, providers, publishing/policies, Control Center e operação conforme SDDs | Unit/contract/integration/E2E e cenários A–L da QA Matrix, sem falhas críticas | Implementação por issues; não substituída por inspeção do browser |
| G3 — integrações externas | Shopee entitlement/AppID/Secret; spike provider IA; Telegram API/sandbox; adapters ML e WhatsApp | Chamadas oficiais autenticadas; respostas sanitizadas; auth/rate/error/timeout; preços/links/tracking/contexto corretos | Operador provisiona acesso/secrets no store, sem colar em chat; implementador executa testes opt-in |
| G4 — browser real | Primário/fallback, ausência/ambiguidade, DOM_CHANGED/AUTH_REQUIRED/CHALLENGE, contexto errado, multiline/preview/hash | FIXTURE → SAFE_LIVE Chrome dedicado VM → SIDE_EFFECT sandbox; zero clique nos negativos | Adapter implementado + ambiente final; Edge exploratório não certifica VM |
| G5 — segurança e recuperação | Nonce/replay/token/hosts, compliance/revalidação, duplicate prevention, unknown remote result, restore | Crash após envio antes de commit não duplica; unknown gera HumanAction sem reenvio; restore bloqueia novos/recuperados até reconciliação; backup/restore, auditoria e scans | Testes de integração/falha com sistema implementado; não provocar outage no notebook de trabalho |
| G6 — VM e release | Boot/autostart/browser/heartbeat/sessões; rede/browser restart/terminação abrupta; migrações/backup/versionamento | Homologação no notebook real e VM; release tests/migration/backup/tag/notes; Requirement → Test → Acceptance → Evidence | Ambiente final e build de release; não configurados nesta task |
| G7 — operação observada | Soak e casos humanos; WhatsApp histórico ASSISTED estável; decisão humana de liberação | 24h SHADOW, depois 72h ou período estendido conforme QA; medir filas/memória/logs/auth/stuck jobs/duplicação; severidades revisadas | Exige tempo real com sistema em execução, sem envio comercial em SHADOW |

## Critérios que não podem ser antecipados com cliques manuais

Preço alterado antes do envio deve bloquear/rescore; preço/URL inventados pela IA devem falhar; destino/hash divergentes e Send ambíguo devem produzir zero clique; crash/restore/resultado desconhecido devem preservar dedupe. Essas propriedades exigem execução do código e persistência, não apenas um envio bem-sucedido no WhatsApp.

Referência Shadow Telegram na QA: pelo menos 50 casos revisados, concordância ordinária >=90%, zero P0, zero P1 nos últimos 30, zero duplicações/links inválidos e 100% disclosure. Números são calibráveis pelo contrato, não dispensáveis por conveniência. WhatsApp exige gate mais rigoroso e histórico ASSISTED estável; limiar exato precisa ser definido na política. Nenhum P0 permite release/AUTO.

Primeira operação real permanece **SHADOW/ASSISTED**, mesmo após aprovação técnica. AUTO é promoção humana posterior, não requisito para concluir tecnicamente a V1.

## Preparação do operador em ordem

1. Solicitar acesso à Shopee Affiliate Open API; depois provisionar segredo no store aprovado. Não enviar segredo por chat.
2. Preparar VM Linux LTS + Chrome dedicado conforme SDD, com login/CAPTCHA feitos manualmente. Registrar ambiente/build quando houver release, sem copiar sessão do Edge para o Core.
3. Manter destino sandbox registrado para cada publisher, separado do comercial; confirmar permissões do bot Telegram e modo ASSISTED para grupo WhatsApp. O envio já autorizado nesta investigação não autoriza novos envios comerciais.
4. Reservar ambiente/horário para testes de falhas e janela de soak quando o sistema estiver implementado. O relógio de soak não começa com este relatório.

## Ordem recomendada para as issues

G1 → contratos/Fake e implementação G2 → integrações G3 e browser G4 → segurança/recuperação G5 → homologação/release G6 → soak/liberação G7. A espera pela API não bloqueia contratos/Fake e domínios independentes. Não publicar/fechar issues automaticamente nem começar implementação global a partir deste checklist.

## Fechamento desta antecipação

Entregues checklist e investigação pública adicional. Sem mudanças normativas, código de produto, migrations, configuração comercial, novos links afiliados ou mensagens. Gates acima permanecem abertos até anexar evidência do sistema implementado.
