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
radarctl migrate
radarctl doctor
radarctl pause
radarctl resume
radarctl drain
radarctl backup
radarctl version
```

Estado no foundation (TKT-01): `status`, `migrate` e `version` já existem. `doctor` pertence a RDR-116 e `pause`/`resume`/`drain`/`backup` aos tickets de controles/backup. `status` é read-only e sai com código diferente de zero quando o serviço não está operacional.

Configuração e secrets (TKT-02): `radarctl config` valida e exibe a configuração sanitizada (`schema_version`, `config_hash`, referências de secret por nome) sem revelar valores. O arquivo `config/radar.json` é opcional (base em `config/radar.example.json`); variáveis `RADAR_*` sobrepõem. Secrets são resolvidos por `RADAR_SECRET_<NOME>` (ou variável explícita na seção `secrets`) e nunca são gravados em config, banco ou logs. Config inválida bloqueia CLI/API com `RAD-CFG-001`/`RAD-CFG-002`.

Taxonomia de marcas (TKT-05): `config/brand-taxonomy.json` é opcional (base em `config/brand-taxonomy.example.json`); `RADAR_TAXONOMY_FILE` força um arquivo explícito. Taxonomia inválida bloqueia a criação da API com `RAD-CFG-005`. O baseline aprovado é usado quando o arquivo não existe.

Control Center (TKT-25): o frontend React/TypeScript/Vite vive em `packages/control-center`; `pnpm --filter @radar/control-center build` gera `packages/control-center/dist`, servido localmente pelo `radar-api` em `127.0.0.1` (sem porta pública e sem CORS). `RADAR_CONTROL_CENTER_DIST` aponta para um build alternativo; sem build, a API continua operando (a UI não é pré-requisito do Core). O read model da Home é `GET /health/overview`.

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
