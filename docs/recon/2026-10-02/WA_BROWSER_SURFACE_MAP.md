# WhatsApp Browser Surface Map — grupo sandbox

[Relatório vigente](BROWSER_RECON_COMPLETION.md), E-WA-01..06. Usuário decidiu Groups em lugar de Channels; contratos/SDDs precisam de revisão explícita.

| Região | Seletores candidatos | Observação/risco |
|---|---|---|
| Sessão/destino | conversation-header; conversation-info-header | READY, grupo sandbox esperado; nome isolado não resolve homônimos |
| Compositor | conversation-compose-box-input; textbox/contenteditable scoped | Três blocos; innerText/textContent divergem; serialização explícita |
| Preview | Região preview no compositor; Cancelar | example.com observado; não fixa comportamento comercial |
| Envio | Enviar dentro main/footer com cardinalidade = 1 | Botão de voz quando vazio; um clique autorizado |
| Pós-envio | data-id e conv-msg-<id> | Bubble com Enviada; ID real omitido das fixtures |

Destino autorizado: grupo sandbox CASA EM ORDEM | PROMOS #1. Um membro observado, mensagens temporárias sete dias, configuração não alterada. Uma mensagem técnica enviada às 22:57; nenhuma repetição. Enviada não prova Entregue/Lida.

Nenhum ID persistente do grupo encontrado no header. Não deduzir group_id do message-id, storage ou cookies. Seletores são candidatos, não contrato de estabilidade.

Auth expirada/offline/reconnect/reload/crash não provocados. Unknown result exige HumanAction/reconciliação, sem reenvio automático; dedupe persistente não pode depender da retenção do bubble. Registry e projeções sanitizadas: FOLLOWUP_EVIDENCE.json.
