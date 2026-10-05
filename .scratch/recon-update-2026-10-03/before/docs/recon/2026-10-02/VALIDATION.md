# Validação do pacote

Complemento posterior: home/lista pública relâmpago/filtro de beleza/cards Shopee observados; E-SP-PUB-01..05 em SHOPEE_PUBLIC_FINDINGS.md supersede a indicação inicial de superfície não investigada abaixo. Não houve novo teste de adapter ou produção. Checklist dos gates em PRODUCTION_READINESS.md.

E-SP-PUB-06/07: filtro Casa e Cozinha observado; detalhe público transitou para Verifique para continuar, interrupção sem bypass. Sem confirmação de preço no detalhe, sem novo link/envio; URLs registradas em DISCOVERY_URL_GUIDE.md.

Comandos seguros, offline, sem dependências externas:

~~~powershell
python docs/recon/2026-10-02/verify_recon_fixtures.py
python docs/recon/2026-10-02/verify_followup_evidence.py
~~~

Resultado: **6 + 8 = 14 testes PASS**. Os resultados do fechamento são verificados novamente na entrega.

Primeira suite: fragmentos DOM, limites/estados, contexto público, cardinalidade testid presente/ausente/duplicado, registry→fixture e denylist de dados privados. Segunda: projeções posteriores, tracking, contexto, serialização/hash do draft, simulações de destino/texto divergentes, Send ausente/ambíguo e marker/status ausentes. São verificações de artefatos/simulações, não aceite de adapters.

SHA256 offline do texto técnico aprovado: 22fda5938fe9f747da4910af4a4dc47bf29188b9df1164ba9ea67dc747c800a2.

Observação live pelo host: geração/copy ML, full/short e barra, landing social, erro com resultado stale; Shopee conversor/modal/redirect/cinco Sub IDs, challenge e retomada humana, negativos no-result; documentação oficial API; grupo/compositor/preview, um envio autorizado e Enviada. Nenhum CAPTCHA automatizado ou chamada API autenticada.

Não executados: API autenticada (sem acesso), suite de adapter (não implementado), SAFE_LIVE de adapter Chrome/VM, falhas de sessão/rede/reboot/MV3/soak, recuperação persistente e entrega/leitura WhatsApp. Site público ofertas relâmpago não investigado. Relatos do operador sobre CAPTCHA/site público são USER_REPORTED, não testes instrumentados.

Nenhum segredo/screenshot integral/ID opaco afiliado ou message-id real persistido. Revisão de privacidade limitada aos artefatos desta task; denylist não garante sanitização universal. Sem migrations/config/contratos normativos alterados por esta avaliação. [Gaps atuais](GAP_REPORT.md).
