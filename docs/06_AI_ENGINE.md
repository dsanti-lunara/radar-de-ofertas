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
