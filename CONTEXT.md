# Radar Engine

Vocabulário de seleção e publicação de ofertas afiliadas das marcas Radar Beauty e Casa em Ordem.

## Language

**Grupo WhatsApp cadastrado**:
Destino GROUP associado à marca e ao ambiente por vínculo verificado; nome de exibição isolado não comprova identidade.

**Vínculo de destino**:
Registro versionado de pareamento/evidência e reverificação do grupo. Não habilita envio enquanto identidade segura estiver pendente.

**Etiqueta externa ML**:
Valor alfanumérico minúsculo até 30 caracteres, mapeado explicitamente ao TrackingContext interno e configurado pelo operador.

**TrackingContext**:
Referência interna auditável que correlaciona conversão → publicação → opportunity → candidate, separada da etiqueta externa do marketplace e sem PII. Nunca é normalizada silenciosamente.

**AffiliateLink**:
Entidade própria e auditável com URL original, URL afiliada literal (nunca editada pela IA), método de geração e tracking; só existe após Opportunity aprovada e linkável. Um provider Fake não é link produtivo.

**Link Shopee manual validado**:
Retorno literal gerado pelo operador no portal, após Opportunity aprovada, aceito pelo Core somente com contexto/tracking/evidência válidos; não é fallback automático do Browser Bridge.

**SHADOW**:
Modo de avaliação que registra decisões humanas e do sistema e permite previews, sem envio comercial.

**ASSISTED**:
Modo em que o envio de uma publicação depende de aprovação humana explícita dessa publicação.

**Aprovação de Candidate**:
Decisão de aceitar uma oferta avaliada como Opportunity; não constitui autorização de envio.

**Aprovação de publicação**:
Autorização humana explícita para enviar uma publicação em ASSISTED, sujeita às validações e políticas vigentes.

**Resultado de envio desconhecido**:
Situação em que não há evidência suficiente para confirmar se uma publicação foi enviada ao destino externo.
_Avoid_: Falha confirmada de envio
