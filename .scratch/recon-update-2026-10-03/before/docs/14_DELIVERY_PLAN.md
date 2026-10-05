# 14, Delivery Plan and Scope Freeze

## Scope Freeze

Ao final do SDD-13, arquitetura e escopo da V1 estão congelados.

Nova feature após o freeze exige decisão explícita.

Durante Hardening:
- bug;
- security;
- recovery;
- compliance;
- usability blocker.

Nada além disso entra.

## Spikes

### SPIKE-01
Validar provider/autenticação ChatGPT:
- fluxo real;
- structured output;
- persistence/refresh;
- capabilities;
- limits;
- fallback.

### SPIKE-02
Shopee Affiliate API:
- credenciais;
- endpoints;
- product/offers;
- link generation;
- conversion reports;
- rate limits.

### SPIKE-03
Browser Recon ML + Shopee.

### SPIKE-04
Browser Recon WhatsApp Channels.

## Milestones

0. Specification Bootstrap
1. Foundation
2. Domain & Persistence
3. Scoring Engine
4. Workflow Engine
5. AI & Knowledge
6. Control Center & Operations
7. Telegram
8. Browser Reconnaissance
9. Browser Bridge
10. Mercado Livre Adapter
11. Shopee Adapter
12. WhatsApp Publisher
13. Runtime & Recovery
14. Hardening
15. Shadow Pilot
16. V1 Production

## Vertical slices

### Slice 1
Manual/Fake Offer
→ Real Scoring
→ Fake AI
→ Fake Link
→ Fake Publisher
→ Publication

### Slice 2
Manual URL
→ Real Scoring
→ Real AI
→ Real Telegram Sandbox

### Slice 3
ML/Shopee real
→ real affiliate link
→ real AI
→ Telegram Sandbox

### Slice 4
Real offer
→ WhatsApp Test Channel
em ASSISTED.

## Critical path

```text
Foundation
→ Domain
→ Persistence
→ Scoring
→ Workflow
→ Fake E2E
→ AI
→ Telegram
→ Browser Recon
→ Browser Bridge
→ Marketplaces
→ WhatsApp
→ Runtime
→ Hardening
→ Shadow
```

Control Center e Knowledge Pack podem avançar em paralelo após Foundation.

## V1.1

- importação de conversões mais completa;
- analytics comercial;
- calibração assistida de pesos;
- digest comercial;
- monitoramento pós-publicação mais inteligente;
- auto-tuning de frequência;
- WhatsApp AUTO se gates forem satisfeitos;
- novas fontes oficiais;
- comparação cross-marketplace melhor.

## Backlog

- Amazon;
- publishers sociais adicionais;
- ML preditivo;
- cloud;
- multi-node;
- multi-user;
- mobile;
- crawler genérico;
- infraestrutura distribuída.

## Definition of V1 complete

- VM sobe e Radar recupera;
- ML/Shopee entram no pipeline pelas capabilities validadas;
- Deal/Monetization/Confidence funcionam;
- AI review/content funcionam;
- links corretos;
- Telegram testado e preparado para produção controlada;
- WhatsApp ASSISTED validado;
- Control Center operável;
- backup/restore;
- security suite;
- Shadow pilot;
- nenhum P0 aberto.

AUTO ativado não é requisito de conclusão técnica.
