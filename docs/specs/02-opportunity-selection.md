# SPEC-02: Seleção de oportunidades

## Problem Statement

Seleção subjetiva ou baseada em comissão pode recomendar ofertas ruins e produzir claims sem evidência.

## Solution

Entregar seleção de oportunidades como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero normalizar categorias pelas prioridades das duas marcas, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero avaliar Price Opportunity pelo histórico próprio, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero considerar comparação de marketplace, cupom e frete confiáveis, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero avaliar Seller Quality com dados ausentes tratados explicitamente, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero normalizar sinais de Demand por categoria, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero medir Brand Fit das duas marcas, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero calcular Deal Score deterministicamente, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero calcular Monetization Score sem alterar Deal Score, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero medir Confidence separadamente, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero aplicar Hard Rules antes de score e IA, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero encaminhar decisões pela matriz Deal × Confidence, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero comparar fontes de compra sem privilegiar comissão, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero bloquear duplicações e respeitar regras de repost, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero produzir allowed_claims sustentados por Evidence, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

- Manter pesos macro Deal 40/25/20/15 e componentes aprovados no SDD de scoring; guardar decimal, breakdown e feature snapshot.
- Thresholds <60, 60..<80 e >=80 conforme Decision Matrix; Confidence LOW/MEDIUM/HIGH separado.
- Histórico insuficiente e ausência de referência usam valores neutros previstos e penalizam Confidence; dado ausente não vira zero arbitrariamente.
- Compra materialmente mais cara segue review/substituição conforme guardrail de referência >8%; Monetization apenas ordena oportunidades aceitáveis.
- Configuração versiona parâmetros; lacunas de normalização/calibração devem ser explicitadas na issue dependente, nunca preenchidas silenciosamente pela IA.

## Testing Decisions

- Fronteira aprovada: Avaliação pública de Candidate com fatos e relógio controlados.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- boundaries 59.99/60/79.99/80.
- precedência de Hard Rules e Deal 45/Monetization 97 rejeitado sem IA/link.
- precisão monetária, freshness e histórico insuficiente.
- dedupe/repost e provenance dos claims.

## Out of Scope

ML preditivo, auto-tuning, conversões inventadas e calibração sem decisão humana.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 03, 04, 05, 12 e 13. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-022..RDR-033. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Evidência verificável para normalizar categorias pelas prioridades das duas marcas.
- [ ] Evidência verificável para avaliar Price Opportunity pelo histórico próprio.
- [ ] Evidência verificável para considerar comparação de marketplace, cupom e frete confiáveis.
- [ ] Evidência verificável para avaliar Seller Quality com dados ausentes tratados explicitamente.
- [ ] Evidência verificável para normalizar sinais de Demand por categoria.
- [ ] Evidência verificável para medir Brand Fit das duas marcas.
- [ ] Evidência verificável para calcular Deal Score deterministicamente.
- [ ] Evidência verificável para calcular Monetization Score sem alterar Deal Score.
- [ ] Evidência verificável para medir Confidence separadamente.
- [ ] Evidência verificável para aplicar Hard Rules antes de score e IA.
- [ ] Evidência verificável para encaminhar decisões pela matriz Deal × Confidence.
- [ ] Evidência verificável para comparar fontes de compra sem privilegiar comissão.
- [ ] Evidência verificável para bloquear duplicações e respeitar regras de repost.
- [ ] Evidência verificável para produzir allowed_claims sustentados por Evidence.
- [ ] Falhas e recuperação cobertas na fronteira aprovada, com guardrails preservados.
- [ ] Docs e contratos atualizados; limitações e gates pendentes explícitos.

### Tests required

Unit e contract relevantes; integration com dependências locais reais quando aplicável; segurança funcional e E2E do fluxo. Live/fixtures/sandbox somente nos gates descritos, nunca por padrão.

### Observability

Estado/saúde e erros acionáveis do fluxo, Correlation ID, eventos auditáveis e HumanActions quando necessária intervenção. Sem secrets/PII desnecessária em logs ou evidências.

### Documentation to update

SDDs referenciados, contratos afetados, QA traceability, Error Catalog/runbooks quando aplicáveis e Issue Map com links de execução. Registrar novas decisões difíceis de reverter em ADR quando justificadas.

### Completion report

Arquivos, testes/resultados, testes não executados/motivos, limitações, mudanças de contrato, migrations/config changes e riscos restantes. Atualizar a issue com evidência e critérios verificados; não ativar AUTO.

