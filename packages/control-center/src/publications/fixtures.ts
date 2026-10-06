/**
 * Fixtures sanitizadas da tela Publicações (RDR-061/062).
 *
 * Nenhum dado real de marketplace, credencial ou PII: produto/link/destino são
 * sintéticos e o link produtivo é explicitamente `false` (AUT-164, AUT-299).
 */

export const inboxFixture = {
  schema_version: "1.0",
  status: "OK",
  correlation_id: "cid-inbox",
  count: 2,
  items: [
    {
      entry_id: "pub_1",
      kind: "PUBLICATION",
      publication_id: "pub_1",
      opportunity_id: "opp_1",
      content_generation_id: "ctg_1",
      brand: "RADAR_BEAUTY",
      channel: "TELEGRAM",
      destination_id: "dest-tg-sandbox",
      status: "PUBLISHED",
      revision: 1,
      external_message_id: "fake-telegram-dest-tg-sandbox-pub_1",
      published_price: "80.00",
      product: {
        marketplace: "MERCADO_LIVRE",
        external_id: "MLB-UI",
        title: "Perfume",
        url: "https://www.mercadolivre.com.br/p/MLB-UI",
        brand: "RADAR_BEAUTY",
        current_price: "80.00",
      },
      last_validation: {
        validated_at: "2026-10-06T12:00:00+00:00",
        allowed: true,
        reason_code: null,
        source: "CREATION",
      },
      updated_at: "2026-10-06T12:00:00+00:00",
    },
    {
      entry_id: "preview:opp_2",
      kind: "PREVIEW",
      publication_id: null,
      opportunity_id: "opp_2",
      content_generation_id: "ctg_2",
      brand: "CASA_EM_ORDEM",
      channel: "TELEGRAM",
      destination_id: null,
      status: "READY",
      revision: null,
      external_message_id: null,
      published_price: null,
      product: {
        marketplace: "MERCADO_LIVRE",
        external_id: "MLB-PREVIEW",
        title: "Aspirador",
        url: null,
        brand: "CASA_EM_ORDEM",
        current_price: "199.90",
      },
      last_validation: {
        validated_at: "2026-10-06T13:00:00+00:00",
        allowed: true,
        reason_code: null,
        source: "CREATION",
      },
      updated_at: "2026-10-06T13:00:00+00:00",
    },
  ],
};

const publicationSummary = {
  publication_id: "pub_1",
  opportunity_id: "opp_1",
  content_generation_id: "ctg_1",
  affiliate_link_id: "lnk_1",
  brand: "RADAR_BEAUTY",
  channel: "TELEGRAM",
  destination_id: "dest-tg-sandbox",
  status: "PUBLISHED",
  revision: 1,
  external_message_id: "fake-telegram-dest-tg-sandbox-pub_1",
  published_price: "80.00",
  correlation_id: "cid-publish",
  created_at: "2026-10-06T12:00:00+00:00",
  published_at: "2026-10-06T12:00:00+00:00",
};

const productView = {
  marketplace: "MERCADO_LIVRE",
  external_id: "MLB-UI",
  title: "Perfume",
  url: "https://www.mercadolivre.com.br/p/MLB-UI",
  brand: "RADAR_BEAUTY",
  current_price: "80.00",
};

const previewView = {
  content_generation_id: "ctg_1",
  channel: "TELEGRAM",
  status: "VALIDATED",
  stale: false,
  renderer_version: "renderer-1.0",
  headline: "Perfume em oferta",
  body: "Preço validado pelo backend",
  cta: "Comprar",
  text: "Perfume em oferta\nR$ 80,00\nLink: https://afiliado.example/lnk_1",
  price: "80.00",
  affiliate_url: "https://afiliado.example/lnk_1",
  disclosure: "Link de afiliado",
  tracking: { brand: "RADAR_BEAUTY", channel: "TELEGRAM" },
};

const linkView = {
  affiliate_link_id: "lnk_1",
  affiliate_url: "https://afiliado.example/lnk_1",
  productive: false,
  generation_method: "FAKE",
  status: "READY",
  tracking_context_id: "trk_1",
  tracking_internal_reference: "RADAR_BEAUTY:MERCADO_LIVRE",
  tracking_label: "rbtgoffer",
  tracking_mapping_version: "tracking-labels-1",
};

export const publicationDetailFixture = {
  schema_version: "1.0",
  status: "OK",
  correlation_id: "cid-detail",
  entry_id: "pub_1",
  detail: {
    kind: "PUBLICATION",
    opportunity_id: "opp_1",
    publication: publicationSummary,
    product: productView,
    preview: previewView,
    link: linkView,
    revision: 1,
    external_message_id: "fake-telegram-dest-tg-sandbox-pub_1",
    last_validation: {
      validated_at: "2026-10-06T12:00:00+00:00",
      allowed: true,
      reason_code: null,
      source: "CREATION",
    },
    timeline: [
      {
        event_type: "CREATED",
        source: "publication_event",
        occurred_at: "2026-10-06T12:00:00+00:00",
        correlation_id: "cid-publish",
        payload: {},
      },
      {
        event_type: "PUBLISHED",
        source: "publication_event",
        occurred_at: "2026-10-06T12:00:00+00:00",
        correlation_id: "cid-publish",
        payload: {},
      },
    ],
    human_actions: [],
  },
};

export const previewDetailFixture = {
  schema_version: "1.0",
  status: "OK",
  correlation_id: "cid-preview",
  entry_id: "preview:opp_2",
  detail: {
    kind: "PREVIEW",
    opportunity_id: "opp_2",
    publication: null,
    product: {
      marketplace: "MERCADO_LIVRE",
      external_id: "MLB-PREVIEW",
      title: "Aspirador",
      url: null,
      brand: "CASA_EM_ORDEM",
      current_price: "199.90",
    },
    preview: {
      ...previewView,
      content_generation_id: "ctg_2",
      text: "Aspirador em oferta\nR$ 199,90",
    },
    link: linkView,
    revision: null,
    external_message_id: null,
    last_validation: {
      validated_at: "2026-10-06T13:00:00+00:00",
      allowed: true,
      reason_code: null,
      source: "CREATION",
    },
    timeline: [
      {
        event_type: "OPPORTUNITY_CREATED",
        source: "workflow",
        occurred_at: "2026-10-06T13:00:00+00:00",
        correlation_id: "cid-opp",
        payload: {},
      },
    ],
    human_actions: [],
  },
};

export const unknownDetailFixture = {
  ...publicationDetailFixture,
  detail: {
    ...publicationDetailFixture.detail,
    publication: { ...publicationSummary, status: "UNKNOWN", external_message_id: null },
    revision: 1,
    external_message_id: null,
    timeline: [
      {
        event_type: "CREATED",
        source: "publication_event",
        occurred_at: "2026-10-06T12:00:00+00:00",
        correlation_id: "cid-publish",
        payload: {},
      },
      {
        event_type: "RESULT_UNKNOWN",
        source: "publication_event",
        occurred_at: "2026-10-06T12:00:00+00:00",
        correlation_id: "cid-publish",
        payload: {},
      },
    ],
    human_actions: [
      {
        human_action_id: "ha_1",
        action_type: "REVIEW_PUBLICATION",
        status: "OPEN",
        reason: "SEND_RESULT_UNKNOWN",
        error_code: "RAD-PUB-006",
        impact: "Uma publicação pode ter sido enviada sem confirmação local.",
        next_steps: "Reunir evidência suficiente e resolver o resultado desconhecido.",
      },
    ],
  },
};
