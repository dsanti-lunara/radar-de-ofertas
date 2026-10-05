from pathlib import Path
import json
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[1]
plan = json.loads((ROOT / ".scratch/radar-v1/publication-plan.json").read_text(encoding="utf-8"))
updates = json.loads((TASK / "updates.json").read_text(encoding="utf-8"))
progress = json.loads((TASK / "publication-progress.json").read_text(encoding="utf-8"))
assert len(progress["verified"]) == 28 and progress["blockers"] == [48, 50, 51]
readme_path = ROOT / ".scratch/radar-v1/README.md"
text = readme_path.read_text(encoding="utf-8")
for number in [36, 38, 39, 47, 49, 52, 54, 55]:
    u = next(x for x in updates if x["number"] == number)
    body = (ROOT / u["bodyFile"]).read_text(encoding="utf-8")
    objective = re.search(r"^## Objective / What to build\n\n(.*?)(?=\n\n## )", body, flags=re.M | re.S)[1].strip()
    pat = rf"(^{number}\. .*?\*\*Entrega:\*\* )([^\n]*?)( \[Ticket completo\])"
    text, count = re.subn(pat, lambda m: m[1] + objective + m[3], text, flags=re.M)
    assert count == 1, number
text = text.replace("# Radar V1 — proposta de 67 tickets", "# Radar V1 — 67 tickets publicados e revisão pós-recon")
text = text.replace("## Breakdown para revisão", "## Breakdown vigente")
readme_path.write_text(text, encoding="utf-8")

# Inventory includes the handoff, while the immutable assessment remains historical.
changed_path = TASK / "changed-files.json"
changed = json.loads(changed_path.read_text(encoding="utf-8"))
changed.append("docs/recon/2026-10-02/UPDATE_HANDOFF.md")
changed = sorted(set(changed))
changed_path.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
groups = {
    "Specs": [x for x in changed if x.startswith("docs/specs/")],
    "Contratos, decisões e operação": [x for x in changed if (x.startswith("docs/") and not x.startswith("docs/recon/") and not x.startswith("docs/specs/")) or x == "CONTEXT.md"],
    "Evidência e revisão": [x for x in changed if x.startswith("docs/recon/")],
    "Espelhos de tickets e rastreabilidade": [x for x in changed if x.startswith(".scratch/radar-v1/")],
}
inventory = "\n\n".join(f"### {name}\n\n" + "\n".join(f"- `{x}`" for x in paths) for name, paths in groups.items())
links = ", ".join(f"[#{u['number']}](https://github.com/dsanti-lunara/radar-de-ofertas/issues/{u['number']})" for u in updates)
handoff = f"""# Aplicação da revisão pós-recon — specs e issues

Data: **2026-10-03**, America/Sao_Paulo. Status: **APLICADA E VERIFICADA**. Operador autorizou alterar os specs e issues após a avaliação; entrega exclusivamente documental/tracker, sem iniciar implementação.

## Resultado

- SPEC-00/01/05/06/07 e índice atualizados; SPEC-02/03/04 preservam escopo/arquitetura.
- RECON-001..005 formalizam GROUP/capability/vínculo, tracking ML e três rotas Shopee. AUT-101/102 têm refinamento/supersessão explícitos, preservando histórico.
- Shopee API recorrente; portal manual/diagnóstico; captura pública assistida candidata. RDR-100 agora valida link gerado manualmente pelo operador; sem geração recorrente pelo Browser Bridge.
- WhatsApp usa PUBLISH_WHATSAPP_GROUP e destino GROUP. Identidade/reverificação segura permanece gate, sem inferir ID de nome/header/message-id. Serializer/hash/preflight e receipt/unknown result/dedupe seguem GRILL-001..003.
- Correções de integridade: marker/status ausentes são negativos futuros do adapter, não cobertura dos 14 verificadores atuais; E-SP-PUB-08 confirmou preço somente da opção 12L, sem comprovar opção preta/checkout/recorrência.
- 28 issues existentes atualizadas e relidas do GitHub para confirmar corpo, título, estado e label; 67 issues preservadas, nenhuma criada/fechada. Os 134 IDs RDR e AC aplicáveis foram mantidos; nenhum AC de produto foi marcado concluído.

## Issues atualizadas

{links}

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

{inventory}
"""
(ROOT / "docs/recon/2026-10-02/UPDATE_HANDOFF.md").write_text(handoff, encoding="utf-8")
print(json.dumps({"handoff": "docs/recon/2026-10-02/UPDATE_HANDOFF.md", "updated_files": len(changed), "issues_verified": 28}, ensure_ascii=False))
