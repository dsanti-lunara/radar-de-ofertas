# 06, AI Engine and Knowledge Pack

## Papel da IA

Permitido:
- interpretação editorial;
- contextualização;
- classificação semântica quando necessária;
- escolha de ângulo;
- warnings;
- geração de copy;
- adaptação por marca/canal.

Proibido:
- inventar preço;
- calcular scores;
- alterar scores;
- afirmar cupom sem Evidence;
- criar/alterar link;
- ignorar Hard Rule;
- decidir compliance;
- publicar diretamente.

## Providers

Interface:
- `evaluate_candidate`
- `generate_content`
- `review_content`
- `classify_product`, quando necessário

Implementações:
- `FakeAIProvider`
- provider real validado por SPIKE-01
- API paga futura opcional

O projeto deve detectar capability real do provider. Não presumir que a assinatura ChatGPT garante qualquer fluxo técnico específico sem validação.

## Knowledge Pack

Estrutura alvo:

```text
knowledge/
├── manifest.yaml
├── brands/
│   ├── radar_beauty.yaml
│   └── casa_em_ordem.yaml
├── editorial/
│   ├── principles.md
│   ├── telegram.md
│   └── whatsapp.md
├── compliance/
│   ├── general.md
│   ├── mercado_livre.md
│   └── shopee.md
├── claims/
│   └── allowed_claims.md
├── taxonomy/
│   └── categories.yaml
└── examples/
    ├── approved.jsonl
    └── rejected.jsonl
```

Runtime carrega somente contexto necessário por:
`brand + channel + task`.

Não colocar lógica matemática no prompt.

## Prompt layering

```text
SYSTEM CONTRACT
+ TASK CONTRACT
+ BRAND CONTEXT
+ CHANNEL CONTEXT
+ CANDIDATE FACTS
+ ALLOWED CLAIMS
+ UNTRUSTED MARKETPLACE CONTENT, somente quando indispensável
```

HTML bruto nunca entra.

## System Contract

Deve conter semanticamente:
- você é componente editorial do Radar;
- use somente fatos fornecidos;
- não crie valores comerciais;
- não altere scores;
- não altere URLs;
- siga schema;
- allowed claims e hard rules precedem criatividade.

## Allowed/Forbidden Claims

A entrada deve fornecer `allowed_claims`.

Forbidden por padrão:
- BEST_PRICE_ON_THE_INTERNET
- LAST_UNITS
- WILL_SELL_OUT
- GUARANTEED_ORIGINAL
- PERSONAL_EXPERIENCE
- UNVERIFIED_COUPON

## Tasks

### EDITORIAL_REVIEW

Resposta estruturada:
- decision;
- editorial_angle;
- reason_codes[];
- warnings[].

Decisões:
- APPROVE
- REVIEW
- REJECT

### GENERATE_CONTENT

Resposta:
- headline;
- body;
- cta;
- warnings.

URL, preço final renderizado e disclosure são inseridos pelo backend.

### CONTENT_REVIEW

Opcional/seletiva para casos de risco.

## Validators locais

Após IA:
1. schema validation;
2. numeric guard;
3. claim guard;
4. prohibited expressions;
5. content/channel rules;
6. compliance;
7. deterministic renderer.

Número comercial não sustentado bloqueia publicação.

## Link Guard

A IA não é responsável por URL. O renderer lê `AffiliateLink.validated=true`.

## Cache

`ai_input_hash` permite reutilizar resultado quando:
- produto/oferta relevantes iguais;
- scores iguais;
- warnings iguais;
- Knowledge/Prompt versions iguais.

Mudança relevante invalida o hash.

## Feedback

Guardar:
- generated_content;
- final_content;
- diff;
- human decision.

Correções não viram regra automaticamente. Devem alimentar relatório/calibração e atualização versionada do Knowledge Pack.

## Failure

Estados:
- AUTH_REQUIRED
- PROVIDER_UNAVAILABLE
- USAGE_UNAVAILABLE
- RATE_LIMITED
- TIMEOUT
- INVALID_SCHEMA
- CONTENT_VALIDATION_FAILED
- REFUSAL

Falha da IA nunca resulta em publicação cega.

Circuit breaker pode suspender AUTO quando houver sequência de respostas inválidas.

## Implementação (TKT-19, RDR-045..RDR-047/050)

O Knowledge Pack é uma configuração editorial versionada e hasheada
(`radar.domain.knowledge`; `config/knowledge-pack.json` opcional, use
`config/knowledge-pack.example.json`, `RADAR_KNOWLEDGE_FILE` força um arquivo) e o
Runtime seleciona somente o contexto de `brand + channel + task`. O baseline
aprovado é intencionalmente vazio: um slice sem contexto é lacuna explícita
(`KNOWLEDGE_CONTEXT_NOT_CONFIGURED`), nunca guidance inventada.

O contrato `AIProvider` (RDR-046) é o seam por onde o provider real (SPIKE-01/
RDR-048) entrará; o `FakeAIProvider` (RDR-047) é determinístico, offline, não
acessa rede nem credenciais e respeita os Hard Rules: uma Evaluation
`REJECT`/`REVIEW` nunca vira aprovação. O Editorial Review (RDR-050) é validado
antes de qualquer persistência: schema/enum inválido, `AUTO_PUBLISH`, refusal,
timeout, auth e indisponibilidade retornam erro estruturado
(`RAD-AI-001..004`/`RAD-AI-010`) e nunca criam Opportunity por aprovação cega. O
`AIReview` append-only guarda provider/model, `knowledge_version`/`prompt_version`
e os `allowed_claims` que sustentam a decisão. `GENERATE_CONTENT` (RDR-051) foi
implementado no TKT-21 e o cache `ai_input_hash` (RDR-055) no TKT-22; `CONTENT_REVIEW`
e o Circuit Breaker permanecem fora deste ticket.

## Implementação (TKT-21, RDR-019/RDR-051..054/RDR-069)

`GENERATE_CONTENT` (RDR-051) é implementado em `radar.domain.content`: o provider
(contrato `ContentProvider`, satisfeito pelo `FakeAIProvider`) devolve somente
`headline`/`body`/`cta`/`warnings`, e o `ContentGenerationService` valida a resposta
antes de persistir. Os validators locais de `docs/06_AI_ENGINE.md` são
determinísticos (AUT-082): schema (`RAD-AI-004`, campo sensível `RAD-AI-007`, URL da
IA `RAD-AI-013`), Numeric Guard (RDR-052, número comercial sem Evidence →
`RAD-AI-005`), Claim Guard (RDR-053, claim proibido/não sustentado → `RAD-AI-006`),
regras de canal (`RAD-AI-014`) e compliance (`RAD-AI-015`). O renderer determinístico
(RDR-069) insere o preço sustentado pela claim `CURRENT_PRICE`, a `AffiliateLink`
literal e o disclosure, nunca uma URL da IA (AUT-163/AUT-164). `generated_content` e
`final_content` ficam separados com suas versões e o `facts`/`fact_hash` permitem
marcar a geração como `STALE` quando um fato relevante muda, sem mutar a linha.
`CONTENT_REVIEW` continua em ticket próprio; o cache `ai_input_hash` (RDR-055) foi
implementado no TKT-22.

## Implementação (TKT-22, RDR-055)

O cache de resultado de IA é um `ai_input_hash` canônico do input versionado do
provider (`radar.domain.content.canonical_ai_input_hash`, RDR-055): o hash cobre
produto/oferta, scores da Evaluation, `allowed_claims` sustentados pelo backend,
warnings e as versões de Knowledge/Prompt (com `knowledge_hash`), então um input
equivalente reutiliza o resultado e qualquer mudança relevante invalida o cache. O
`ContentGenerationService.generate` consulta o store append-only por
`(opportunity_id, ai_input_hash)`; um resultado persistido ainda não-`STALE` é
reusado sem nova chamada ao provider (`cache_hit=true`, o `POST` responde com
`cache_hit`) e um miss gera, valida e persiste normalmente. O cache **nunca**
contorna a validação: uma resposta inválida (schema/URL/número/claim) falha fechada
antes de persistir e não é cacheada, e um resultado que virou `STALE` (nova
observação de preço, link vigente, versão de knowledge/prompt) é ignorado. A
migration `0016_ai_input_cache` acrescenta `ai_input_hash` e o índice
`ix_content_generation_ai_input`; linhas anteriores carregam hash vazio e nunca
casam. O provider real segue o gate SPIKE-01/RDR-048.
