# Suspender publicação com resultado de envio desconhecido

Decisão aceita em 2026-10-02. Um crash ou perda de resposta pode deixar um envio remoto concluído sem confirmação persistida; a chave local de idempotência não elimina essa janela. Quando faltar evidência suficiente, registrar o resultado desconhecido, suspender a publicação afetada, impedir reenvio automático e abrir uma HumanAction para revisão.

Concluir o envio ou autorizar uma nova tentativa exige evidência suficiente; autorização humana isolada não prova que o envio anterior falhou. A nova tentativa permanece sujeita à revalidação e aos guardrails vigentes. Aceitamos perder a validade de uma oferta enquanto a dúvida é resolvida para evitar duplicação, em vez de tratar resultado desconhecido como falha transitória e repetir o envio.

Após restore, o banco pode perder registros de publicações realizadas depois do backup. Diagnóstico e processamento seguro podem retomar, mas os envios permanecem bloqueados até reconciliar esse intervalo com evidência suficiente. A ausência de registro restaurado não autoriza reenvio; resultados ainda desconhecidos seguem a revisão humana acima. Essa extensão foi aceita em 2026-10-02.
