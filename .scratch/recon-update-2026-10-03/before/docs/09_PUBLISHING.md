# 09, Publishing, Tracking and Offer Lifecycle

## Limites de autorização e recuperação

SHADOW registra avaliações e previews, sem envio comercial. Em ASSISTED, o envio exige aprovação humana explícita da publicação; a aprovação do Candidate não autoriza enviar. Toda autorização permanece sujeita à revalidação, compliance e Publishing Policy.

Se o resultado remoto de um envio for desconhecido, registrar essa condição, suspender a publicação afetada, bloquear reenvio automático e criar HumanAction de revisão. Não classificar a ausência de confirmação como falha confirmada. Concluir ou autorizar nova tentativa exige evidência suficiente; a oferta pode expirar durante a revisão. Ver `adr/0001-unknown-publication-result.md`.

## Publishers

```text
Publisher
├── TelegramPublisher
└── WhatsAppPublisher
```

Telegram usa Bot API.

WhatsApp usa Browser Bridge.

## Destinations

`PublishingDestination` contém:
- brand;
- platform;
- destination_type;
- external_id;
- enabled;
- automation_mode.

Destinos iniciais:
- Radar Beauty Telegram
- Casa em Ordem Telegram
- Radar Beauty WhatsApp Channel
- Casa em Ordem WhatsApp Channel
- sandboxes separados para testes

## Renderer

A IA entrega:
- headline;
- body;
- CTA.

Renderer adiciona deterministicamente:
- preço validado;
- affiliate URL;
- botão quando aplicável;
- disclosure;
- tracking.

IA nunca cria/edita URL.

## Telegram

- um bot operacional pode atender ambos os canais;
- `sendMessage`/edição por API;
- armazenar `chat_id/message_id`;
- idempotency obrigatória;
- lifecycle por revision.

## WhatsApp

- usa Browser Bridge;
- mesma VM/browser de ML/Shopee;
- destination allowlist;
- message hash verification;
- começa ASSISTED;
- AUTO somente após gate específico.

Não enviar para contatos/grupos arbitrários.

## Tracking

### Shopee

Sub IDs conceituais:
- brand
- channel
- content_type
- category
- publication/internal reference

Sem PII.

### Mercado Livre

Usar etiquetas conforme capacidade real validada no Recon.

Sem redirect próprio na V1.

## Publication states

- DRAFT
- READY
- PUBLISHING
- PUBLISHED
- UPDATED
- EXPIRED
- FAILED
- DELETED

## Revisions

Cada edição preserva revision history.

Exemplo:
- REV1 preço original;
- REV2 preço melhor;
- REV3 oferta encerrada.

Preferir editar/expirar a apagar automaticamente.

## Publication Policy

Controla:
- frequência;
- hard cap;
- burst;
- cooldown;
- diversidade;
- threshold por canal.

Cap não é meta.

Referência inicial:
- soft target Telegram 4-8 boas ofertas/dia/marca;
- hard cap inicial 12/dia/marca;
- burst inicial: no máximo 2 posts em 15 minutos.

Todos configuráveis.

WhatsApp deve ter threshold igual ou mais rigoroso que Telegram.

## Quiet Hours

Publishing pode pausar enquanto discovery continua.

Oferta aguardando janela deve revalidar antes de enviar.

## Lifecycle post-publication

Checks limitados, por exemplo:
- +30m
- +2h
- +6h

Configurável.

Tempo sozinho não prova que oferta terminou.

## Compliance

`ChannelCompliancePolicy` decide:
- affiliate_link_allowed;
- automatic_publication_allowed;
- disclosure_required;
- policy_version.

Se policy bloqueia:
- discovery/scoring/link podem continuar;
- side effect de publicação é bloqueado.

## Attribution

TrackingContext deve permitir:
`conversion report → publication → opportunity → candidate`

Quando houver volume, conversões alimentam `ConversionEvidence`.
