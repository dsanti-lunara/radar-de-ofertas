# ML Capability Matrix

| Capability | Evidência atual | Gate restante |
|---|---|---|
| DETECT_PAGE | Central/gerador/admin/produto observados | Negativos/fallback/Chrome |
| CHECK_MARKETPLACE_SESSION | READY | AUTH_REQUIRED/CHALLENGE não provocados |
| CAPTURE_CURRENT_PRODUCT | Produto público com barra | Variante/vendedor/contexto |
| CAPTURE_VISIBLE_AFFILIATE_OFFER | Cards Central | Dedupe/contexto/fixtures completas |
| GENERATE_ML_AFFILIATE_LINK | Gerador e barra executados com autorização; short igual | Efeito Minhas recomendações; tracking lowercase/30 contradiz RB_TG_OFFER; idempotência não provada |
| VALIDATE_AFFILIATE_LINK | Full social landing com produto destacado esperado; copy ML confirmado | Short redirect separado não testado; rejeitar outros recomendados |
| Failure detection | nao-e-url → erro, seção anterior ainda visível | Resultado stale nunca prova sucesso atual |
| RESUME_JOB | Sem runtime implementado | Persistência/MV3/recovery |

Candidatos ASSISTED; nenhuma promoção AUTO ou aceite de adapter. [Relatório vigente](BROWSER_RECON_COMPLETION.md), [mapa](ML_BROWSER_SURFACE_MAP.md).
