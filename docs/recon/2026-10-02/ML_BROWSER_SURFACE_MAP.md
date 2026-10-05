# Mercado Livre Browser Surface Map

| Superfície | Path | Estados/resultados |
|---|---|---|
| Central | /afiliados/hub | READY; ferramentas/cards repetidos; E-ML-01 |
| Gerador | /afiliados/linkbuilder | Vazio disabled, produto enabled, short/full/copy; inválido com erro e seção anterior visível; E-ML-02/03/08/09/12/13 |
| Etiquetas | /afiliados/adminlabel | Modal charset/lowercase/30; nenhuma criação/alteração persistida; E-ML-04/05 |
| Produto/barra | /.../p/MLB43187757 | Barra, dois Compartilhar, modal Gerar link / ID de produto; short igual; E-ML-06/11/12 |
| Landing social | /social/<affiliate> | Produto esperado destacado e outras recomendações; E-ML-10 |
| Ajuda | /ajuda/30084 | Gerar adiciona Minhas recomendações; confirmado após ação; E-ML-07/08 |

Seletores candidatos: URL #url-0 dentro do gerador; barra generate_link_button; campos text-field__label_link, text-field__label_id, text-field__label_suggested_text; ações copy-button__label_link e equivalentes, scoped no dialog. Preferir role/label dentro da região correta; falhar em ausência/ambiguidade. Não usar Compartilhar global ou P0-1 como identidade universal.

Auth READY observado; AUTH_REQUIRED/CHALLENGE não provocados. Loading e clipboard exigem observação posterior; falha da tentativa invalida resultado stale. Short/full retornados devem ser preservados literalmente, sem edição por IA. Geração tem efeito remoto autorizado nesta sessão, não autorização permanente.

[Relatório vigente](BROWSER_RECON_COMPLETION.md), fixtures/registry candidatos em FOLLOWUP_EVIDENCE.json e SELECTOR_REGISTRY_CANDIDATE.json. Sem aceite de adapter/AUTO.
