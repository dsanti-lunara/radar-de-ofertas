# WhatsApp Capability Matrix — Groups

| Capability/guardrail | Resultado | Gate restante |
|---|---|---|
| Page/session detection | READY observado | Auth/offline/reconnect não exercitados |
| Destination selection/identity | Grupo sandbox/header/compositor confirmados | ID persistente e homônimos sem prova |
| Multiline/preview | Três blocos e preview observados | Serializer/hash de adapter |
| Send/result marker | Um envio autorizado; Enviada/data-id | Delivery/read, reload/recovery não testados |
| Destination mismatch | Simulação offline | Adapter deve provar zero clique |
| Message mismatch | Simulação offline | Hash/preview determinísticos reais |
| Send ambiguity/ausência | Simulações offline | Cardinalidade e fallback de adapter |
| Resultado desconhecido/idempotência | Marker observado; simulações negativas | Persistência/reconciliação/crash sem reenvio |

Reconnaissance não libera SPIKE-04/adapter/AUTO. Usuário mudou escopo de Channels para Groups; formalizar capability/destino/allowlist nos SDDs antes de implementar. Mensagem temporária não substitui dedupe persistente. [Evidências](BROWSER_RECON_COMPLETION.md).
