"""Apply the authorized documentary reconciliation; never operates a browser."""
from pathlib import Path
import hashlib
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
TASK = Path(__file__).resolve().parent
PLAN = ROOT / ".scratch/radar-v1/publication-plan.json"
REMOTE = json.loads((TASK / "remote-before.json").read_text(encoding="utf-8-sig"))
REMOTE = {x["number"]: x for x in REMOTE}
CHANGED = []


def read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig")


def save(path, content):
    target = ROOT / path
    previous = target.read_bytes() if target.exists() else None
    newline = "\r\n" if previous and b"\r\n" in previous else "\n"
    data = content.replace("\r\n", "\n").replace("\n", newline).encode("utf-8")
    if data == previous:
        return
    backup = TASK / "before" / path
    if previous is not None and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(previous)
    target.write_bytes(data)
    CHANGED.append(path)


def replace(path, old, new):
    value = read(path)
    assert old in value, (path, old[:90])
    save(path, value.replace(old, new))


def add(path, heading, content):
    value = read(path)
    assert heading in value, (path, heading)
    save(path, value.replace(heading, heading + "\n\n" + content.strip(), 1))


def section(body, heading, content):
    pattern = rf"(^{re.escape(heading)}\n)(.*?)(?=^## |\Z)"
    result, count = re.subn(pattern, lambda m: m[1] + "\n" + content.strip() + "\n\n", body, flags=re.M | re.S)
    assert count == 1, heading
    return result


def extend(body, heading, content):
    assert body.count(heading) == 1, heading
    return body.replace(heading, heading + "\n\n" + content.strip(), 1)


GROUP = """WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003)."""

ML = """TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos."""

SP = """Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação."""

EVIDENCE = """Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental."""

# Normative reconciliation, preserving existing parallel edits.
for path in ["docs/00_SDD_MASTER.md", "docs/14_DELIVERY_PLAN.md"]:
    replace(path, "WhatsApp Channels", "WhatsApp Groups cadastrados")
replace("docs/14_DELIVERY_PLAN.md", "WhatsApp Test Channel", "WhatsApp Grupo Sandbox")
add("docs/00_SDD_MASTER.md", "## Spikes obrigatórios", "Recon funcional de 2026-10-02 finalizado e consumido na revisão de 2026-10-03. Isso não fecha automaticamente spikes/aceites. API Shopee da conta, fixtures completas, adapters, SAFE_LIVE Chrome/VM e recovery continuam gates próprios. Ver `docs/recon/2026-10-02/PRODUCTION_READINESS.md`.")
add("docs/DECISION_LOG.md", "# Decision Log", """## Revisão autorizada em 2026-10-03 — resultados do browser recon

- **RECON-001**: WhatsApp V1 usa GROUP cadastrado e PUBLISH_WHATSAPP_GROUP, em ASSISTED, mantendo allowlist/marca/sandbox. Identidade e reverificação do vínculo são gates; nome/message-id não são identidade de grupo. Envio não é habilitado sem prova segura.
- **RECON-002**: Shopee separa API recorrente, portal manual/diagnóstico e captura pública assistida candidata. Retirar geração recorrente de links por extensão do portal. Link obtido manualmente pode ser validado pelo Core conforme RDR-100; não automatizar o portal ou contornar proteção.
- **RECON-003**: Etiqueta ML externa usa minúsculas/números até 30, com mapeamento explícito, unicidade e auditoria; TrackingContext interno não sofre normalização silenciosa. Geração é side effect também em Minhas recomendações.
- **RECON-004**: Documentação API Brasil permite contratos/Fake offline; entitlement e API autenticada são gates separados. Resultado desconhecido de mutation/envio não recebe retry cego. Recon finalizado não promove API_SUPPORTED, adapter ou AUTO.
- **RECON-005**: Slice Shopee aceita uma rota comprovada: captura API + link API; captura pública assistida + link API; ou captura assistida + link manual validado. Revalidação atual, guards, disclosure e autorização continuam obrigatórios em todas.

Fonte: `recon/2026-10-02/BROWSER_RECON_COMPLETION.md` e `SPEC_ISSUE_REVIEW.md`; operador autorizou atualização dos specs e issues, sem implementação ou novos side effects.""")
add("CONTEXT.md", "## Language", """**Grupo WhatsApp cadastrado**:
Destino GROUP associado à marca e ao ambiente por vínculo verificado; nome de exibição isolado não comprova identidade.

**Vínculo de destino**:
Registro versionado de pareamento/evidência e reverificação do grupo. Não habilita envio enquanto identidade segura estiver pendente.

**Etiqueta externa ML**:
Valor alfanumérico minúsculo até 30 caracteres, mapeado explicitamente ao TrackingContext interno e configurado pelo operador.

**Link Shopee manual validado**:
Retorno literal gerado pelo operador no portal, após Opportunity aprovada, aceito pelo Core somente com contexto/tracking/evidência válidos; não é fallback automático do Browser Bridge.""")
replace("docs/04_DATA_CONTRACTS.md", '"tracking_label": "RB_TG_OFFER"', '"tracking_label": "rbtgoffer"')
add("docs/04_DATA_CONTRACTS.md", "## Browser Bridge, get job", "O exemplo de etiqueta abaixo é sintático; não comprova que exista na conta. A revisão documental mantém `schema_version=1.0` para contratos ainda não implementados; schemas executáveis/versionamento final pertencem aos tickets, sem compatibilidade silenciosa de CHANNEL para GROUP.")
add("docs/04_DATA_CONTRACTS.md", "## Enums principais", """`Channel` identifica a plataforma; o destino WA V1 tem `destination_type=GROUP` e capability `PUBLISH_WHATSAPP_GROUP`. Não usar PUBLISH_WHATSAPP_CHANNEL como alias. Registro de destino/vínculo e receipt seguem o contrato abaixo; campos adicionais/migrations serão formalizados antes da implementação.""")
add("docs/04_DATA_CONTRACTS.md", "## Idempotency", GROUP + "\n\n" + ML + "\n\n" + SP)
replace("docs/07_BROWSER_BRIDGE.md", "- PUBLISH_WHATSAPP_CHANNEL", "- PUBLISH_WHATSAPP_GROUP")
replace("docs/07_BROWSER_BRIDGE.md", "- GENERATE_SHOPEE_AFFILIATE_LINK\n", "")
replace("docs/07_BROWSER_BRIDGE.md", "Browser pode ser usado de forma assistida/fallback nas superfícies validadas:\n- Link de Conversão;\n- Oferta de Produto;\n- Oferta da Loja;\n- campanhas;\n- outras encontradas no Recon.\n\nSem crawling massivo.", SP + "\n\nRDR-100 cobre validação de link manual; GENERATE_SHOPEE_AFFILIATE_LINK não é capability operacional do Bridge V1. Não implementar alias que automatize o portal. Sem crawling massivo.")
replace("docs/07_BROWSER_BRIDGE.md", "- Radar Beauty Channel\n- Casa em Ordem Channel\n- sandbox channel para testes", "- Radar Beauty Group\n- Casa em Ordem Group\n- grupo sandbox separado para testes")
add("docs/07_BROWSER_BRIDGE.md", "## Mercado Livre", ML)
add("docs/07_BROWSER_BRIDGE.md", "## WhatsApp", GROUP)
replace("docs/09_PUBLISHING.md", "WhatsApp Channel", "WhatsApp Group")
add("docs/09_PUBLISHING.md", "## Destinations", GROUP)
add("docs/09_PUBLISHING.md", "### Mercado Livre", ML)
add("docs/09_PUBLISHING.md", "### Shopee", SP)
add("docs/12_SECURITY_AND_COMPLIANCE.md", "## WhatsApp", "WA V1 usa GROUP registrado, com vínculo/reverificação provados; homônimos ou vínculo inválido causam zero clique. Nome/header isolado e message-id não comprovam group-id. Recibo sem confirmação suficiente gera resultado desconhecido, nunca retry automático. Portal Shopee fica manual/diagnóstico: não alternar rotas para contornar CAPTCHA, rate limit ou entitlement.")
replace("docs/ERROR_CATALOG.md", "| RAD-WA-002 WHATSAPP_DESTINATION_MISMATCH | canal errado |", "| RAD-WA-002 WHATSAPP_DESTINATION_MISMATCH | grupo/vínculo diferente do destino cadastrado; zero clique |")
replace("docs/ERROR_CATALOG.md", "| RAD-WA-003 WHATSAPP_SEND_FAILED | envio não confirmado |", "| RAD-WA-003 WHATSAPP_SEND_FAILED | falha de envio confirmada; não usar para resultado desconhecido |\n| RAD-WA-004 WHATSAPP_SEND_RESULT_UNKNOWN | evidência insuficiente; suspender, HumanAction e zero reenvio automático |\n| RAD-WA-005 WHATSAPP_DESTINATION_IDENTITY_UNVERIFIED | vínculo/identidade não comprovados; bloquear envio |")
replace("docs/ERROR_CATALOG.md", "| RAD-SP-002 SHOPEE_API_AUTH_REQUIRED | API precisa reautenticar |", "| RAD-SP-002 SHOPEE_API_AUTH_REQUIRED | credencial/assinatura/timestamp exige classificação e ação segura; não é sessão browser |\n| RAD-SP-003 SHOPEE_API_ACCESS_REQUIRED | entitlement pendente, não NOT_SUPPORTED global |\n| RAD-SP-004 SHOPEE_API_RESULT_INCOMPLETE | HTTP 200 com errors/data parcial não satisfaz contrato |\n| RAD-SP-005 SHOPEE_LINK_RESULT_UNKNOWN | mutation sem confirmação; reconciliar, sem retry cego |\n| RAD-ML-003 ML_TRACKING_LABEL_INVALID | etiqueta inválida ou mapeamento/associação não verificado |\n| RAD-ML-004 ML_LINK_RESULT_STALE | erro atual ou resultado sem correlação com tentativa atual |")
replace("docs/ERROR_CATALOG.md", "| RAD-BRW-010 BROWSER_VERSION_INCOMPATIBLE | protocolo/extensão incompatível | no |", "| RAD-BRW-010 BROWSER_VERSION_INCOMPATIBLE | protocolo/extensão incompatível | no |\n| RAD-BRW-011 CHALLENGE | proteção detectada; suspender parte afetada e ação humana | no |")
replace("docs/13_QA_ACCEPTANCE_MATRIX.md", "WhatsApp está no canal errado", "WhatsApp está no grupo/vínculo errado")
add("docs/13_QA_ACCEPTANCE_MATRIX.md", "### Browser", "Recon 2026-10-02 fornece 14 verificações de artefatos, não aceite de adapters. Registry/fallbacks candidatos precisam de testes completos, negativos e SAFE_LIVE no Chrome dedicado/VM antes de SIDE_EFFECT autorizado. CHALLENGE suspende somente parte afetada e exige revalidação na retomada.")
add("docs/13_QA_ACCEPTANCE_MATRIX.md", "### WhatsApp", """- GROUP allowlisted, marca e ambiente corretos; homônimos, vínculo ausente/inválido ou troca após preview produzem zero clique;
- serializer canônico multiline/preview/hash; innerText/textContent não são contrato implícito;
- Send ausente/duplicado e marker/status pós-envio ausentes;
- Enviada não comprova entregue/lida; receipt deve corresponder à publication/revision e tentativa;
- crash após envio antes de commit, reload/reconnect/MV3 e mensagem temporária de sete dias preservam dedupe;
- resultado desconhecido suspende e gera HumanAction, sem reenvio automático; restore mantém bloqueio GRILL-003.""")
add("docs/13_QA_ACCEPTANCE_MATRIX.md", "### Scoring", "Range Shopee/card/desconto riscado não prova preço de variante nem histórico independente. CHALLENGE ou dados atuais indisponíveis impedem revalidação pré-envio; cache não substitui essa evidência.")
add("docs/13_QA_ACCEPTANCE_MATRIX.md", "### Workflow", "Shopee API: 200 com errors/partial data falha fechado; Int64/Decimal preservados, assinatura de bytes exatos, paginação específica, 10020 por reason, 10030/backoff e 10035/entitlement. Mutation unknown não recebe retry cego. ML: etiqueta charset/30/unicidade, resultado stale, social landing com outro produto destacado e contexto catálogo/anúncio errado devem falhar.")
add("docs/10_PERSISTENCE_AND_RECOVERY.md", "## Time and money", "Dedupe/receipt/vínculo de destino e auditoria persistem independentemente de mensagens temporárias WA, cache ou bubble removido. Retenção não pode apagar proteção necessária contra reenvio/reconciliação; restore segue bloqueio dos envios até reconciliar intervalo pós-backup.")
add("docs/14_DELIVERY_PLAN.md", "## Vertical slices", "Shopee Slice 3 aceita captura API+link API, captura pública assistida+link API ou captura assistida+link manual validado. Portal afiliado não é fallback operacional por extensão. Cada rota exige dados atuais, guards, disclosure e sandbox autorizado. Recon finalizado não encerra API live/adapter/homologação.")

# Existing specs: decisions, dependencies, acceptance and tests reconciled together.
replace("docs/specs/00-delivery.md", "WhatsApp test channel ASSISTED", "WhatsApp grupo sandbox ASSISTED")
replace("docs/specs/00-delivery.md", "Provider/auth AI ainda requer SPIKE-01; Shopee API está PENDING SPIKE-02; superfícies reais e seletores dependem de SPIKE-03/04 e reconnaissance.", "Provider/auth AI ainda requer SPIKE-01; Shopee conta/API autenticada requer SPIKE-02. Recon funcional ML/SP/WA finalizado; adoção das fixtures, gaps e SAFE_LIVE Chrome/VM de adapters permanecem gates. Contratos/Fake Shopee podem avançar offline com documentação oficial, sem promover API_SUPPORTED.")
add("docs/specs/00-delivery.md", "## Implementation Decisions", EVIDENCE + "\n\n" + "RECON-001..005 governam GROUP, tracking ML e três rotas Shopee. Tickets existentes #1–#67 são a decomposição; preservar RDR-001..134 e não publicar specs/tickets duplicados. RDR-100 valida link manual, não automatiza portal.")
add("docs/specs/00-delivery.md", "### Acceptance Criteria", "- [ ] Contratos, objetivos, AC, testes e blockers usam GROUP e as rotas Shopee coerentes; documentação/recon não substitui os gates de adapter/API/produção.")
for filename, content in [
    ("01-foundation-domain.md", "Destino WA diferencia plataforma WHATSAPP e tipo GROUP; vínculo/receipt auditáveis não inferem ID externo. Tracking interno e externo são separados. IDs Int64 de marketplace atravessam contratos como strings decimais sem perda; dinheiro/comissão usa Decimal. Schemas/migrations de implementação devem cumprir SDD-04/09, sem prometer identidade do grupo ainda não provada."),
    ("05-publication-recovery.md", GROUP + "\n\n" + "Todas as rotas Shopee, inclusive link manual, exigem revalidação atual; indisponibilidade/challenge não é superada por cache ou aprovação humana isolada. Tracking ML e Sub IDs seguem SDD-04/09."),
    ("06-browser-marketplaces.md", EVIDENCE + "\n\n" + ML + "\n\n" + SP + "\n\n" + GROUP),
    ("07-operations-acceptance.md", "Gates G1..G7 de PRODUCTION_READINESS permanecem NO-GO. Homologar GROUP/vínculo, receipts/dedupe após mensagens temporárias, crash/reconnect/MV3/reboot/restore, segurança e soak no Chrome dedicado/VM. Captura API/pública/manual e link API/manual têm aceites separados; nenhum build ou teste de artefato aprova produção. UI só habilita capacidades reais e vínculos verificados.")
]:
    path = "docs/specs/" + filename
    add(path, "## Implementation Decisions", content)
    add(path, "### Acceptance Criteria", "- [ ] Refinamentos RECON-001..005 aplicáveis demonstrados na fronteira pública; limitations/gates explícitos, sem alias CHANNEL, ID inventado ou fallback de proteção.\n- [ ] Fixtures/Fake, SAFE_LIVE, API autenticada e SIDE_EFFECT sandbox têm evidências separadas; não marcar aceites reais por testes offline do recon.")
    add(path, "### Tests required", "Cobrir os negativos e recuperação aplicáveis da revisão RECON-001..005 e QA Matrix: identidade/charset/precisão/contexto, resultado stale/partial/unknown e dedupe persistente; estados positivos, falha e retomada auditáveis. Runtime/live permanecem opt-in nos gates autorizados.")
replace("docs/specs/06-browser-marketplaces.md", "SPIKE-02, SPIKE-03 e SPIKE-04 antes dos adapters dependentes.", "Recon funcional de SPIKE-03/04 finalizado; cada adapter depende da adoção de fixtures, negativos/gaps e SAFE_LIVE próprio. SPIKE-02 bloqueia runtime API da conta, não os contratos/Fake offline nem a rota manual validada.")
save("docs/specs/README.md", """# Specs de entrega V1

Specs e fronteiras aprovados em 2026-10-02, reconciliados com o recon em 2026-10-03 por autorização do operador. SDDs, Decision Log, CONTEXT e ADRs continuam autoridade.

- [SPEC-00: entrega geral](00-delivery.md)
- [SPEC-01: fundação e domínio](01-foundation-domain.md)
- [SPEC-02: seleção de oportunidades](02-opportunity-selection.md)
- [SPEC-03: workflow e autorização](03-workflow-authorization.md)
- [SPEC-04: IA e conteúdo](04-ai-content.md)
- [SPEC-05: publicação e recuperação](05-publication-recovery.md)
- [SPEC-06: browser e marketplaces](06-browser-marketplaces.md)
- [SPEC-07: operação e homologação](07-operations-acceptance.md)

## Tracker e rastreabilidade

Decomposição publicada: 67 tickets em [dsanti-lunara/radar-de-ofertas](https://github.com/dsanti-lunara/radar-de-ofertas/issues), #1–#67. IDs RDR-001..134 continuam canônicos; números GitHub/TKT são diferentes dos RDR. Links, corpos locais e manifesto em `.scratch/radar-v1/PUBLISHED.md`, `issues/` e `publication-plan.json`.

Specs permanecem arquivos locais de referência dos tickets. Esta revisão atualiza tickets existentes; não cria oito issues de specs duplicadas. A proposta anterior de autorização/recuperação está incorporada em SPEC-03/05.

## Revisão pós-recon

GROUP/identidade/preflight, tracking ML e três rotas Shopee foram incorporados nas SPEC-00/01/05/06/07. SPEC-02/03/04 preservam arquitetura e escopo. Investigação finalizada e 14 checks offline não aprovam API da conta, adapters, Chrome/VM ou produção. Entitlement Shopee exige operador; envios permanecem ASSISTED/sandbox com autorização específica e AUTO não é ativado.

Evidências em `docs/recon/2026-10-02/`; avaliação em `SPEC_ISSUE_REVIEW.md` e registro da aplicação em `UPDATE_HANDOFF.md` nesse diretório. Nenhuma implementação ou side effect comercial é autorizado pela publicação desta revisão.
""")

# Correct evidence summaries rather than weakening or inventing tests.
replace("docs/recon/2026-10-02/VALIDATION.md", "Sem confirmação de preço no detalhe, sem novo link/envio;", "Na etapa E-SP-PUB-07 não houve confirmação de preço. E-SP-PUB-08 confirmou R$63,70 da opção 12L após resolução humana; E-SP-PUB-09 não confirmou troca para a opção preta. Sem novo link/envio;")
replace("docs/recon/2026-10-02/VALIDATION.md", "Send ausente/ambíguo e marker/status ausentes.", "Send ausente/ambíguo; marker/status são checados somente na projeção positiva. Casos negativos de marker/status ausentes e classificação unknown/retry continuam testes requeridos do adapter, não cobertura destes verificadores.")
replace("docs/recon/2026-10-02/VALIDATION.md", "Site público ofertas relâmpago não investigado.", "Ofertas relâmpago/listas/filtros/detalhe público foram investigados em E-SP-PUB-01..09; estabilidade recorrente, variante preta e checkout permanecem inconclusivos.")
replace("docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md", "Fixtures/mutações offline cobrem destino diferente, texto diferente, botão ausente/duplicado e data-id/estado pós-envio ausentes.", "Fixtures/mutações offline cobrem destino diferente, texto diferente e botão ausente/duplicado; data-id/status são verificados na projeção positiva. Negativos de data-id/status ausentes e classificação unknown/retry pertencem à suite futura de adapter, não aos 14 verificadores atuais.")
replace("docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md", "incluindo ofertas relâmpago ainda não avaliadas", "incluindo ofertas relâmpago observadas em E-SP-PUB-01..09, com estabilidade/variantes/aceite ainda pendentes")
replace("docs/recon/2026-10-02/SP_CAPABILITY_MATRIX.md", "preço/variante não validados.", "após resolução humana, preço da opção 12L foi confirmado em E-SP-PUB-08; opção preta/checkout/recorrência não validados.")
replace("docs/recon/2026-10-02/SP_CAPABILITY_MATRIX.md", "E-SP-PUB-01..07", "E-SP-PUB-01..09")
replace("docs/SHOPEE_CAPABILITY_REPORT.md", "Destinos públicos foram abertos; ofertas relâmpago e estabilidade recorrente não investigadas.", "Destinos públicos, ofertas relâmpago/listas/filtros e detalhe foram investigados em E-SP-PUB-01..09; estabilidade recorrente e variante preta não foram comprovadas.")
replace("docs/BROWSER_RECONNAISSANCE.md", "seus contratos de Channels precisam ser revisados explicitamente para Groups antes da implementação.", "seus contratos foram reconciliados para Groups em 2026-10-03; identidade/fixtures/adapter/Chrome VM continuam gates antes do envio.")
replace("docs/BROWSER_RECONNAISSANCE.md", "WhatsApp Channels", "WhatsApp Groups")
replace("docs/BROWSER_RECONNAISSANCE.md", "canais configurados/test channel", "grupos cadastrados/grupo sandbox")
replace("docs/BROWSER_RECONNAISSANCE.md", "seleção do canal", "seleção do grupo")
replace("docs/BROWSER_RECONNAISSANCE.md", "estado de canal correto", "estado de grupo/vínculo correto")
add("docs/BROWSER_RECONNAISSANCE.md", "## WhatsApp Groups", "Consumir E-WA-01..06 e registrar gaps sem refazer ou inferir experimento. Nome/header não comprova identidade persistente; investigar pareamento/reverificação permitidos, sem storage/tokens. Fixtures/fallbacks/Chrome VM/unknown result são aceites próprios; nenhum novo envio é autorizado pelo roteiro.")
replace("docs/ISSUE_MAP.md", "Implement Shopee browser link fallback", "Validate operator-generated Shopee link (manual portal; no operational browser generation)")
replace("docs/ISSUE_MAP.md", "Implement assisted channel send", "Implement assisted registered group send")
replace("docs/ISSUE_MAP.md", "Validate sandbox channel E2E", "Validate sandbox group E2E")
replace("docs/ISSUE_MAP.md", "Validate real channels in Assisted mode", "Validate registered destinations and WhatsApp groups in Assisted mode")
add("docs/ISSUE_MAP.md", "# Issue Map", "Revisão pós-recon autorizada em 2026-10-03: preservar IDs RDR-001..134. Tickets publicados #1–#67 e cobertura no manifesto `.scratch/radar-v1/publication-plan.json`. RDR-100 valida link manual; RDR-103..111 WA usa GROUP/vínculo, sem Channels. RDR-076/124/125 têm cobertura dividida ML/SP/WA, não três IDs novos.")

# Remote bodies are authoritative; snapshots prevent overwriting concurrent edits later.
plan = json.loads(PLAN.read_text(encoding="utf-8-sig"))
meta = {int(t["id"].split("-")[1]): t for t in plan["tickets"]}
updates = {}

objectives = {
    36: "Consolidar o recon ML finalizado em 2026-10-02, adotar mapas/fixtures candidatos, testar artefatos e registrar gaps de implementação/homologação sem repetir investigação completa ou gerar novos links.",
    38: "Consolidar o recon Shopee API/portal/site público finalizado; separar superfícies e adotar fixtures/evidências existentes, registrando gaps sem automatizar o portal afiliado ou presumir API da conta disponível.",
    39: "Consolidar o recon WhatsApp Groups finalizado, adotar projeções sanitizadas do grupo sandbox e registrar identidade/serializer/fallback/recovery pendentes. O envio técnico histórico autorizado não autoriza novo envio.",
    47: "Implementar contratos/Fake e normalização Shopee pela documentação oficial Brasil; validar captura API real somente após entitlement/SPIKE-02 e aceites específicos. Sem acesso, expor capability indisponível sem declarar NOT_SUPPORTED global.",
    48: "Gerar AffiliateLink Shopee por API oficial a partir de Opportunity aprovada e contexto/tracking verificáveis, independentemente da rota que capturou o produto. Contratos/Fake primeiro; API autenticada depende de SPIKE-02.",
    49: "Capturar Shopee publicamente de forma assistida, por listas/filtros/campanha vigente e detalhe/variante, preservando RawCapture/Evidence/Candidate e CHALLENGE/HumanAction. Portal afiliado permanece manual/diagnóstico.",
    50: "Validar e persistir retorno literal de link Shopee gerado manualmente pelo operador no portal, após Opportunity aprovada, com contexto/tracking/evidência verificáveis. O Radar não automatiza a geração no portal nem usa essa rota para contornar bloqueios.",
    51: "Comprovar uma rota Shopee validada até Telegram sandbox: captura API+link API, captura pública assistida+link API ou captura assistida+link manual validado, sempre com revalidação atual e guards.",
    52: "Abrir grupo WhatsApp cadastrado com vínculo/identidade verificados e preparar preview canônico sem enviar, validando marca, destino e message hash; vínculo não provado bloqueia a fronteira de envio.",
}
titles = {39: "Consolidar recon WhatsApp Groups e validar fixtures", 50: "Validar link Shopee gerado manualmente", 52: "Preparar mensagem WhatsApp no grupo cadastrado", 55: "Homologar destinos reais e grupos WhatsApp em ASSISTED"}
groups = {
    "ML": [20, 44, 45, 46],
    "SP": [37, 47, 48, 49, 50, 51],
    "WA": [24, 39, 52, 53, 54, 55, 58, 62, 63, 64, 65, 66, 67],
    "BRIDGE": [36, 38, 40, 41, 42],
}
selected = sorted(set(sum(groups.values(), [])))
wa_checks = """- [ ] GROUP/marca/ambiente/vínculo são verificados; homônimos, vínculo ausente/inválido e troca após preview geram zero clique.
- [ ] Serializer multiline/preview/hash tem contrato e testes determinísticos; aprovação de Candidate/preview não autoriza Publication.
- [ ] Send ausente/ambíguo e marker/status ausentes são testados na fronteira do adapter; 14 checks do recon não substituem essa prova.
- [ ] Receipt/unknown result e dedupe persistem após crash/reload/reconnect/MV3 e desaparecimento de mensagem temporária; ausência de bubble não autoriza reenvio.
- [ ] Restore bloqueia envios recuperados e novos até reconciliação pós-backup; AUTO permanece desativado."""
ml_checks = """- [ ] Etiqueta externa charset/30/unicidade/associação é validada sem normalização silenciosa; TrackingContext interno preservado.
- [ ] Produto destacado/catalogo/anúncio/variante são verificados em full/social landing e short; outra recomendação não comprova contexto.
- [ ] Erro da tentativa atual junto a resultado stale nunca produz sucesso; gerador/barra/ausência/fallback têm provas separadas.
- [ ] Efeito Minhas recomendações é autorizado/auditado; timeout/crash não causa repetição cega de geração."""
sp_checks = """- [ ] API/portal manual/site público são capabilities distintas; sem extensão operacional recorrente de geração de link no portal ou fallback de proteção.
- [ ] Documentação/Fake não implica API_SUPPORTED; entitlement/credenciais/API live e limites desconhecidos bloqueiam só a fronteira dependente.
- [ ] Preço/variante/condições atuais e contexto shop/item são verificáveis; CHALLENGE/cache/DOM inicial não autorizam publicação.
- [ ] Tracking até cinco posições e retorno literal são preservados; falha/partial/unknown não produz link inventado nem retry cego."""

for number in selected:
    current = REMOTE[number]
    assert current["state"] == "OPEN", number
    body = current["body"].replace("\r\n", "\n")
    label = "ready-for-human" if number == 37 else "ready-for-agent"
    body = re.sub(r"^\*\*Status:\*\*.*$", f"**Status:** OPEN / {label}; ticket publicado, revisado em 2026-10-03. Escopo documental atualizado; blockers/gates não são considerados cumpridos.", body, count=1, flags=re.M)
    title = titles.get(number, current["title"].split("] ", 1)[1])
    body = re.sub(r"^# TKT-\d+:.*$", f"# TKT-{number:02d}: {title}", body, count=1, flags=re.M)
    body = body.replace("Investigar WhatsApp Channels e validar fixtures", titles[39]).replace("Preparar mensagem WhatsApp no canal certo", titles[52])
    if number in objectives:
        body = section(body, "## Objective / What to build", objectives[number])
    body = extend(body, "## Context / SDD references", EVIDENCE)
    if number in groups["ML"]:
        body = extend(body, "## Contracts", ML)
        checks = ml_checks if number != 20 else "- [ ] TrackingContext interno é separado do tracking externo; Fake valida mapping/charset/30/unicidade sem pressupor etiqueta existente.\n- [ ] Proveniência/retorno literal e Opportunity aprovada são testados com Fake; associação real ML/landing/geração pertence a #45/#46 e não bloqueia Slice 1 offline."
        body = extend(body, "## Acceptance criteria", checks)
        body = extend(body, "## Tests required", "Casos RECON-ML: charset/overflow/colisão/associação, outro produto destacado, short redirect, resultado stale, ausência de barra, autorização/auditoria e recuperação do side effect. Neste ticket, cobrir a fronteira que lhe pertence; integração completa em #46.")
    if number in groups["SP"]:
        body = extend(body, "## Contracts", SP)
        checks = sp_checks
        if number == 37:
            checks = "- [ ] Report separa documentação comprovada, conta sem entitlement, experimento API live pendente e superfícies portal/manual/pública.\n- [ ] Cada capability classificada contém evidência e motivo; ausência de acesso não é NOT_SUPPORTED global nem API_SUPPORTED.\n- [ ] Ambiguidades de auth, schemas/limites desconhecidos e requisitos para validação da conta estão registrados; não implementar adapter neste spike."
        if number == 47:
            checks = "- [ ] Contratos/Fake oficiais V2 e captura→RawCapture/Evidence/Candidate preservam Int64/Decimal/price range, origem e observed_at.\n- [ ] HTTP 200 parcial/errors, auth/reason, entitlement/rate limits/paginação específicos falham/classificam corretamente.\n- [ ] Runtime só passa após #37/live; falta de acesso é indisponibilidade da conta. Link API/manual permanece em #48/#50, não geração browser."
        if number == 48:
            checks = "- [ ] generateShortLink preserva originUrl e até cinco posições de subIds; retorno literal, Opportunity e produto/tracking validados.\n- [ ] Signature/precision/errors/entitlement/limites por campo cobertos; mutation unknown tem auditoria/idempotência/reconciliação sem retry cego.\n- [ ] Link não exige discovery #47 se contexto veio de #49; runtime continua bloqueado por #37; nenhuma geração browser de fallback."
        if number == 49:
            checks = "- [ ] Captura pública guarda shop/item/campanha/categoria/source_url/observed_at e evidência da variante/condições.\n- [ ] Loading não é EMPTY; campanha antiga, contexto/variante errados e CHALLENGE após DOM inicial bloqueiam ou pedem ação humana.\n- [ ] Fixture completa/negativos/fallback e SAFE_LIVE Chrome VM são aceites próprios; portal apenas manual/diagnóstico. Sem geração de link ou API autenticada neste ticket."
        body = extend(body, "## Acceptance criteria", checks)
        body = extend(body, "## Tests required", "Casos RECON-SP aplicáveis: 200+errors/partial data; Int64/Decimal/range de oferta; assinatura de bytes exatos; paginação específica; 10020/10030/10035; mutation unknown; loading/EMPTY, campanha atual, variante/contexto divergentes e CHALLENGE após render. Fake/fixture primeiro; API live e SIDE_EFFECT em gates próprios.")
    if number in groups["WA"]:
        body = extend(body, "## Contracts", GROUP)
        checks = wa_checks
        if number == 39:
            checks = "- [ ] Evidências E-WA-01..06 distinguem grupo sandbox, envio histórico autorizado, Enviada, membro único e mensagem temporária.\n- [ ] Identidade persistente não comprovada, homônimos, serializer/fallback/auth/recovery/Chrome VM ficam gaps explícitos; não implementar envio/vínculo nesta adoção.\n- [ ] Negativos offline realmente executados são separados de testes futuros do adapter, inclusive marker/status ausentes e unknown result."
        if number == 24:
            checks = "- [ ] Resultado WA sem confirmação suficiente é desconhecido, nunca falha confirmada ou reenvio automático.\n- [ ] Receipt/dedupe/auditoria sobrevivem à ausência/expiração do bubble; review/recovery exige evidência suficiente, conforme GRILL-002. Guards de composer/identidade pertencem a #52/#53."
        if number == 58:
            checks = "- [ ] Retention não elimina dedupe/receipts/vínculos/auditoria necessários à reconciliação; sete dias da mensagem temporária não são TTL automático do ledger.\n- [ ] Bubble/diagnóstico/cache pode expirar sem autorizar reenvio; retenção/disco crítico preservam proteção de GRILL-002/003. Não implementar publisher/compositor neste ticket."
        if number in [62, 63, 64, 65, 66, 67]:
            checks = "- [ ] Gate de homologação deste ticket diferencia evidência offline, adapter/API e Chrome/VM real; identidade GROUP e rotas Shopee têm aceites rastreáveis.\n- [ ] Nas falhas/soak aplicáveis, receipts/dedupe permanecem apesar de crash/reload/reconnect/mensagem temporária; unknown/restore não reenviam automaticamente.\n- [ ] Nenhuma capability fica pronta por nome/header, build ou 14 checks de artefatos; manter NO-GO nos gates pendentes e não ativar AUTO."
        body = extend(body, "## Acceptance criteria", checks)
        body = extend(body, "## Tests required", "Casos RECON-WA aplicáveis à fronteira deste ticket: vínculo/homônimos/troca após preview, serializer/hash, ausência/ambiguidade de Send, marker/status ausentes, unknown result, crash pós-envio antes de commit, mensagem temporária, reconciliação/restore. Zero envio em negativos; observação Enviada não comprova entregue/lida. Live só opt-in no ambiente autorizado.")
    if number in groups["BRIDGE"]:
        body = extend(body, "## Contracts", "Registry é candidato; consumir evidências sem declarar fallbacks/Chrome/VM aprovados. Contratos versionados, CHALLENGE/AUTH_REQUIRED/DOM_CHANGED, nonce/replay, host/produto/destino e persistência MV3 devem falhar fechados. Recon finalizado não implementa recovery nem aceita adapter.")
        body = extend(body, "## Acceptance criteria", "- [ ] Evidências atuais e gaps são separados; ausência/ambiguidade/contexto errado/CHALLENGE bloqueiam a fronteira afetada, sem contornar proteção.\n- [ ] Fixture/Fake e SAFE_LIVE Chrome/VM têm provas separadas; não inferir estabilidade de selector/fallback ou persistência pelo recon.")
    if number in [36, 38, 39]:
        body = extend(body, "## In scope", "Adotar pacote existente e rastrear cada etapa como OBSERVADO, SIMULADO ou NÃO EXECUTADO. Os AC que exigem auth/fallback/SAFE_LIVE/recuperação reais permanecem pendentes até evidência; registrar gaps não os marca como aprovados. Não fechar este ticket automaticamente pela existência do relatório nem iniciar adapter como parte desta adoção.")
    if number == 37:
        body = section(body, "## External gates / prerequisites", "A documentação oficial Brasil e mapa de capabilities foram investigados. Conta sem entitlement; operador deve obter acesso e provisionar AppID/Secret no SecretsProvider, sem chat/Git/log/fixtures. Estado ready-for-human para essa ação. API autenticada, ambiguidade Credential/Credentials, limites e schemas reais continuam pendentes; não promover API_SUPPORTED. Contratos/Fake offline de #47/#48 não exigem concluir o gate live.")
    if number == 47:
        body = body.replace("Somente endpoints/auth/capabilities provados no SPIKE-02.", "Contratos/Fake usam documentação oficial Brasil identificada; execução autenticada somente após endpoints/auth/capabilities provados no SPIKE-02.")
        body = body.replace("Se capability não suportada, não simular adapter real; registrar gap e rota assistida dependente.", "Se acesso/capability não disponível, expor indisponibilidade com motivo/evidência; não simular adapter real nem declarar NOT_SUPPORTED global por falta de entitlement.")
    if number == 48:
        body = body.replace("AffiliateLink ou NOT_SUPPORTED.", "AffiliateLink, capability indisponível ou resultado desconhecido, classificados por evidência.")
        body = body.replace("API não suportada é conclusão explícita; fallback browser recebe o mesmo contrato de tracking.", "API indisponível tem causa explícita; não acionar fallback browser de geração. Link manual validado pertence a #50 e mantém o mesmo contrato de tracking.")
        meta[number]["blockedBy"] = ["TKT-20", "TKT-37"]
        meta[number]["externalGate"] = "Contratos/Fake offline permitidos; runtime/API autenticada de link exige entitlement e SPIKE-02, Opportunity/contexto e limites validados. Discovery API #47 não é obrigatório."
    if number == 49:
        body = body.replace("SP BROWSER_ASSISTED confirmado; sem crawling massivo.", "Site público BROWSER_ASSISTED candidato; fixtures completas/negativos/Chrome VM e contexto/variante exigidos. Portal afiliado fica manual/diagnóstico; sem crawling massivo.")
    if number == 50:
        meta[number]["blockedBy"] = ["TKT-20", "TKT-49"]
        meta[number]["externalGate"] = "Operador gera link manual após Opportunity aprovada; Core valida produto/tracking/retorno literal com evidência atual. Sem geração por extensão; sem dependência de entitlement API."
        body = section(body, "## Contracts", "approved Opportunity + retorno literal de link gerado manualmente + evidência de produto/variante/tracking → AffiliateLink validado ou rejeição/HumanAction. Source explícito MANUAL_SHOPEE_PORTAL, operator action/observed_at/correlation_id e auditoria; nunca sintetizar ou editar URL.\n\n" + SP)
        body = section(body, "## Acceptance criteria", """- [ ] Geração no portal é inteiramente humana, depois da Opportunity aprovada; nenhum clique autenticado de geração pelo Bridge.
- [ ] Entrada literal identifica Opportunity, contexto shop/item/variante, tracking/Sub IDs e evidência de origem, ator e observed_at, sem PII/secrets.
- [ ] Core valida HTTPS/host/redirect/produto/tracking/contexto e revalidação atual antes de persistir/publicar; clipboard não é dependência obrigatória.
- [ ] Link/contexto/tracking incorretos, expiração ou dado atual indisponível resultam em rejeição/HumanAction, nunca correção da URL pela IA.
- [ ] Idempotência da entrada manual e auditoria preservadas; não acionar geração por browser/API para contornar proteção.
- [ ] Tests/docs/QA e RDR-100 rastreáveis; nenhum side effect real ou produção aprovado por este ticket documental.""")
        body = section(body, "## Tests required", "Entrada manual válida pelo contrato público; duplicata idempotente; outra Opportunity/produto/variante/Sub IDs; host/redirect inválido; evidência ausente/stale; revalidação indisponível; auditoria/sem secrets. Não testar geração browser como fallback. Fixture/Fake primeiro; validar redirects live somente opt-in permitido, sem novo clique de geração por agente.")
        body = extend(body, "## Out of scope", "Geração de links pelo Browser Bridge no portal affiliate.shopee.com.br e alternância para contornar proteção/indisponibilidade; criação/edição de URL pela IA. Não executar geração humana nesta revisão documental.")
    if number == 51:
        meta[number]["blockedBy"] = ["TKT-35"]
        meta[number]["alternativeRoutes"] = [["TKT-47", "TKT-48"], ["TKT-49", "TKT-48"], ["TKT-49", "TKT-50"]]
        meta[number]["externalGate"] = "Uma rota completa validada e sandbox autorizado; API exige SPIKE-02 via #47/#48, manual não exige entitlement. Todas exigem revalidação atual/guards/disclosure."
        old = "Concluir uma rota suportada: API (tickets 47+48) OU assistida (tickets 49+50); não exigir implementação da alternativa sem suporte."
        new = "Concluir uma rota validada: captura API+link API (#47+#48) OU captura pública assistida+link API (#49+#48) OU captura assistida+link manual validado (#49+#50). Não exigir as três; sem fallback operacional de geração pelo portal."
        assert old in body
        body = body.replace(old, new)
    if number in [48, 50, 51]:
        blockers = "\n".join(f"- [TKT-{int(x.split('-')[1]):02d}](https://github.com/dsanti-lunara/radar-de-ofertas/issues/{int(x.split('-')[1])}) — {titles.get(int(x.split('-')[1]), meta[int(x.split('-')[1])]['title'])}" for x in meta[number]["blockedBy"])
        if number == 51:
            blockers += "\n\nBloqueio alternativo obrigatório: concluir #47+#48 OU #49+#48 OU #49+#50. A rota API herda o gate #37 via #47/#48; a rota manual validada não requer entitlement. Registrar a rota escolhida e sua evidência; não cadastrar os três pares como blockers cumulativos nativos."
        body = section(body, "## Blocked by", blockers)
        body = section(body, "## External gates / prerequisites", meta[number]["externalGate"] + "\n\nready-for-agent significa escopo especificado, não gates cumpridos. Só trabalhar fronteira autorizada/desbloqueada; nenhum novo side effect ou AUTO autorizado por esta revisão.")
    if number == 39:
        body = body.replace("identificação de canal", "identificação de grupo/vínculo").replace("Destinos só cadastrados/test channel", "Grupos só cadastrados/grupo sandbox")
    body = extend(body, "## Documentation to update", "Sincronizar SDD-04/07/09, QA, Decision Log RECON-001..005, specs aplicáveis e corpo/manifesto local. Referências documentais não substituem os AC e contratos concretos deste corpo. Preservar cobertura canônica RDR e histórico de evidência.")
    body = extend(body, "## Completion report", "Revisão documental em 2026-10-03: escopo/contratos/AC/testes/gates atualizados; issue permanece aberta. 14 checks offline do recon passaram, sem testes de produto/live ou migrations. Evidência de conclusão técnica ainda deverá ser registrada pela implementação; não marcar todos os AC como cumpridos por esta revisão.")
    path = ".scratch/radar-v1/" + meta[number]["bodyFile"]
    save(path, body)
    meta[number]["title"] = title
    for published in plan["published"]:
        if published["number"] == number:
            published["title"] = title
    updates[number] = {"number": number, "title": f"[TKT-{number:02d}] {title}", "bodyFile": path, "label": label, "blockedBy": meta[number]["blockedBy"], "beforeUpdatedAt": current["updatedAt"], "beforeBodySha256": hashlib.sha256(current["body"].encode()).hexdigest()}

plan["reconRevision"] = {"date": "2026-10-03", "status": "prepared", "source": "Operator authorized specs and existing issue updates after recon assessment.", "updatedTickets": selected}
save(".scratch/radar-v1/publication-plan.json", json.dumps(plan, ensure_ascii=False, indent=2) + "\n")

readme = read(".scratch/radar-v1/README.md")
readme = readme.replace("TKT-47+48 OU TKT-49+50", "TKT-47+48 OU TKT-49+48 OU TKT-49+50 (link manual validado)")
readme = readme.replace("com label `ready-for-agent`, referências reais e blocking nativo", "com referências reais e blocking nativo; revisão 2026-10-03 mantém `ready-for-agent` conforme gates e encaminha TKT-37 para `ready-for-human`")
for number, title in titles.items():
    old_title = REMOTE[number]["title"].split("] ", 1)[1]
    readme = readme.replace(old_title, title)
    published = read(".scratch/radar-v1/PUBLISHED.md")
    save(".scratch/radar-v1/PUBLISHED.md", published.replace(old_title, title))
for number in [48, 50, 51]:
    pat = rf"(^{number}\. \*\*.*?\*\* — \*\*Bloqueado por:\*\* )([^\n]*?)(\. \*\*Entrega:\*\* )"
    deps = ", ".join(meta[number]["blockedBy"])
    if number == 51:
        deps += "; uma rota alternativa 47+48, 49+48 ou 49+50"
    readme, count = re.subn(pat, lambda m: m[1] + deps + m[3], readme, flags=re.M)
    assert count == 1, (number, "readme blockers")
    pat2 = rf"(^{number}\. .*?\*\*Entrega:\*\* )([^\n]*?)( \[Ticket completo\])"
    readme, count = re.subn(pat2, lambda m: m[1] + objectives[number] + m[3], readme, flags=re.M)
    assert count == 1, (number, "readme objective")
save(".scratch/radar-v1/README.md", readme)
(TASK / "updates.json").write_text(json.dumps(list(updates.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(TASK / "changed-files.json").write_text(json.dumps(sorted(set(CHANGED)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"changed_files": len(set(CHANGED)), "updated_tickets": selected, "publication": "NOT_STARTED"}, ensure_ascii=False))
