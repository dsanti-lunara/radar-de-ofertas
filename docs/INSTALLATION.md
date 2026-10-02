# Installation, target runbook

Este documento descreve o comportamento desejado. Comandos finais devem ser atualizados conforme scripts reais forem implementados.

## Ambiente alvo

- notebook Windows host;
- VM Linux LTS;
- desktop leve;
- usuário dedicado `radar`;
- Chrome Stable;
- pasta de backup no host montada na VM.

## Sequência alvo

1. criar VM;
2. instalar Linux/desktop;
3. criar/configurar usuário `radar`;
4. instalar Git, Python/uv, Node LTS/pnpm e Chrome;
5. clonar repo;
6. executar script idempotente de instalação;
7. bootstrap do Radar;
8. configurar secrets necessários;
9. instalar Browser Bridge como unpacked extension;
10. parear Browser Bridge;
11. autenticar ML;
12. autenticar Shopee;
13. autenticar WhatsApp Web;
14. validar AI provider;
15. configurar Telegram Bot/destinos;
16. configurar host backup path;
17. executar migrations;
18. `radarctl doctor`;
19. habilitar systemd;
20. configurar browser autostart;
21. configurar VM auto-start no host/hypervisor;
22. iniciar em SHADOW/ASSISTED.

## Target commands

A implementação deve oferecer interface equivalente a:

```text
radarctl status
radarctl doctor
radarctl pause
radarctl resume
radarctl drain
radarctl backup
radarctl version
```

## Verificação final

`radarctl doctor` deve validar:
- DB;
- schema;
- config;
- Knowledge;
- disk;
- backup;
- Scheduler;
- Workers;
- Browser Bridge;
- ML;
- Shopee;
- WhatsApp;
- AI;
- Telegram.

Doctor é read-only.

## Segurança

- nenhuma porta pública;
- nada de root para runtime;
- perfil Chrome dedicado;
- sem extensões desnecessárias;
- secret fora de Git/config comum;
- canais de teste separados dos canais de produção.
