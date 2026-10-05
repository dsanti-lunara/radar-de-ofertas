from pathlib import Path
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[1]
changed = set(json.loads((TASK / "changed-files.json").read_text(encoding="utf-8")))
plan_path = ROOT / ".scratch/radar-v1/publication-plan.json"
plan = json.loads(plan_path.read_text(encoding="utf-8"))
updates = json.loads((TASK / "updates.json").read_text(encoding="utf-8"))
remote = {i["number"]: i for i in json.loads((TASK / "remote-before.json").read_text(encoding="utf-8-sig"))}


def save(path, text):
    p = ROOT / path
    old = p.read_bytes()
    data = text.replace("\r\n", "\n").replace("\n", "\r\n" if b"\r\n" in old else "\n").encode("utf-8")
    if data != old:
        backup = TASK / "before" / path
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
        p.write_bytes(data)
        changed.add(path)


def edit(path, replacements):
    text = (ROOT / path).read_text(encoding="utf-8-sig")
    for old, new in replacements:
        assert old in text, (path, old[:70])
        text = text.replace(old, new)
    save(path, text)


titles = {36: "Consolidar recon ML e validar fixtures", 38: "Consolidar recon Shopee e validar fixtures", 39: "Consolidar recon WhatsApp Groups e validar fixtures", 50: "Validar link Shopee gerado manualmente", 52: "Preparar mensagem WhatsApp no grupo cadastrado", 55: "Homologar destinos reais e grupos WhatsApp em ASSISTED"}
for update in updates:
    p = ROOT / update["bodyFile"]
    text = p.read_text(encoding="utf-8")
    for number, title in titles.items():
        old_title = remote[number]["title"].split("] ", 1)[1]
        text = text.replace(old_title, title)
    if update["number"] == 54:
        text = text.replace("test Channel", "grupo sandbox cadastrado")
    if update["number"] == 49:
        text = text.replace("assisted portal capture → Candidate e estado browser.", "assisted public site capture → RawCapture/Evidence/Candidate e estado browser por superfície.")
        text = text.replace("Casos RECON-SP aplicáveis: 200+errors/partial data; Int64/Decimal/range de oferta; assinatura de bytes exatos; paginação específica; 10020/10030/10035; mutation unknown; loading/EMPTY, campanha atual, variante/contexto divergentes e CHALLENGE após render. Fake/fixture primeiro; API live e SIDE_EFFECT em gates próprios.", "Casos RECON-SP captura pública: loading/EMPTY, campanha atual/expirada, shop/item e Int64/Decimal preservados, card/detalhe/variante divergentes, CHALLENGE após DOM inicial e retomada humana revalidada. Fixture/negativos/fallback primeiro; SAFE_LIVE Chrome VM em gate próprio. Não exigir auth/mutation API neste ticket de captura.")
    if update["number"] in [36, 38]:
        text = text.replace("ausência/ambiguidade/contexto errado/CHALLENGE bloqueiam a fronteira afetada", "ausência/ambiguidade/contexto errado/CHALLENGE têm candidatos, projeções e gaps de adapter explícitos")
    if update["number"] in titles:
        update["title"] = f"[TKT-{update['number']:02d}] {titles[update['number']]}"
    save(update["bodyFile"], text)
for t in plan["tickets"]:
    number = int(t["id"].split("-")[1])
    if number in titles:
        t["title"] = titles[number]
for t in plan["published"]:
    if t["number"] in titles:
        t["title"] = titles[t["number"]]
save(".scratch/radar-v1/publication-plan.json", json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
(TASK / "updates.json").write_text(json.dumps(updates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for path in [".scratch/radar-v1/README.md", ".scratch/radar-v1/PUBLISHED.md"]:
    text = (ROOT / path).read_text(encoding="utf-8")
    for number, title in titles.items():
        text = text.replace(remote[number]["title"].split("] ", 1)[1], title)
    text = text.replace("Mapear destino/compositor/evidência pós-envio de Channels autorizados sem enviar mensagens nesta investigação.", "Consolidar o recon Groups já finalizado, adotar fixtures/evidências e registrar gaps; não autoriza novo envio.")
    text = text.replace("test Channel", "grupo sandbox cadastrado")
    text = text.replace("escolhida com evidência do SPIKE-02, nunca ambas por imposição artificial", "escolhida com evidência por capability; SPIKE-02 exigido nas rotas API, sem exigir as três rotas cumulativamente")
    save(path, text)
edit("docs/specs/00-delivery.md", [("SPIKE-02, SPIKE-03 e SPIKE-04 antes dos adapters dependentes.", "SPIKE-02 para runtime API da conta; recon funcional de SPIKE-03/04 finalizado, mas fixtures/negativos/SAFE_LIVE de adapter continuam gates próprios.")])
edit("docs/recon/2026-10-02/WA_CAPABILITY_MATRIX.md", [("Marker observado; simulações negativas", "Marker/status observados e projeção positiva; negativos de destino/hash/Send"), ("formalizar capability/destino/allowlist nos SDDs antes de implementar.", "capability/destino/allowlist foram formalizados em RECON-001 na revisão de 2026-10-03; identidade/reverificação e aceite permanecem pendentes.")])
edit("docs/recon/2026-10-02/GAP_REPORT.md", [("ML tracking RB_TG_OFFER contradiz charset/lowercase/30 da UI. Decisão explícita de contrato/mapeamento necessária.", "O exemplo anterior RB_TG_OFFER contradizia charset/lowercase/30. RECON-003 e SDD-04/09 definem mapping explícito da etiqueta externa, unicidade e auditoria; configuração/associação da conta e implementação permanecem pendentes."), ("Formalizar docs/contratos/issues; identidade persistente", "Docs/contratos formalizados em RECON-001; identidade persistente"), ("Nenhuma issue publicada/encerrada; nenhuma implementação ou revisão silenciosa de contratos.", "A investigação não publicou/encerrou issues nem implementou produto. Revisão documental explícita autorizada em 2026-10-03 aplica RECON-001..005; rastreabilidade e resultado da atualização do tracker em UPDATE_HANDOFF.md. Nenhuma capability promovida.")])
edit("docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md", [("Este é o **documento vigente para consumo na revisão/criação de issues**.", "Este é o **documento vigente para consumo na revisão/criação de issues**. Revisão normativa posterior autorizada em 2026-10-03: RECON-001..005 e UPDATE_HANDOFF.md registram aplicação nos contratos/specs/tickets; as limitações e o NO-GO deste estudo permanecem." )])
edit("docs/recon/2026-10-02/PRODUCTION_READINESS.md", [("Tracker remoto não auditado; IDs RDR são locais.", "Na fase de investigação o tracker remoto não foi auditado; IDs RDR são locais. A revisão documental posterior de 2026-10-03 consultou #1–#67 e reconcilia contratos/specs/issues (UPDATE_HANDOFF.md); isso não aprova os gates de produção abaixo.")])
edit("docs/recon/2026-10-02/SPEC_ISSUE_REVIEW.md", [("Data de referência: 2026-10-02, America/Sao_Paulo; investigação atravessou 2026-10-03 UTC.", "Data de referência: 2026-10-02, America/Sao_Paulo; investigação atravessou 2026-10-03 UTC.\n\n> Avaliação histórica: o operador autorizou aplicar esta proposta em 2026-10-03. A aplicação explícita e o estado final do tracker são registrados em [UPDATE_HANDOFF.md](UPDATE_HANDOFF.md). Os trechos abaixo descrevem o parecer anterior à aplicação; não substituem os contratos agora atualizados.")])
(TASK / "changed-files.json").write_text(json.dumps(sorted(changed), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"refined_files": len(changed), "tickets": len(updates)}))
