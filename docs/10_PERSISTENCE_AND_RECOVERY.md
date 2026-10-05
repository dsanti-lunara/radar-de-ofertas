# 10, Persistence, Configuration, Secrets, Backup and Recovery

## Banco

SQLite é canônico na V1.

Configuração:
- WAL;
- foreign_keys ON;
- transactions;
- busy timeout;
- indexes;
- migrations.

SQLAlchemy 2 + Alembic.

## Append-only

Não sobrescrever:
- PriceObservation;
- Evaluation;
- AIReview;
- HumanReview;
- PublicationEvent;
- Domain/Audit events.

## Estrutura persistente alvo

```text
data/
  radar.db
  backups/

config/
knowledge/
logs/
diagnostics/
migrations/
runtime/
```

Código e dados persistentes devem permanecer separados.

## Config

Separar:
- `config`, comportamento operacional;
- `knowledge`, comportamento editorial/contextual.

Config deve ser validada por schema e versionada/hash.

Mudanças importantes geram snapshot.

Hot reload permitido para:
- thresholds;
- publishing caps;
- quiet hours;
- kill switches;
- automation modes;
- category weights.

## Secrets

Nunca em:
- Git;
- YAML comum;
- banco comum;
- logs;
- backup;
- Knowledge Pack;
- prompt.

Usar `SecretsProvider` com armazenamento seguro do OS/usuário.

Sessões ML/Shopee/WhatsApp ficam exclusivamente no browser profile.

## Browser profile

É runtime state, não dado canônico.

Pode ser recriado:
- novo profile;
- instalar extensão;
- parear;
- autenticar serviços.

## Logs

Application logs estruturados em JSON.

Audit events persistentes separados.

Nunca logar:
- password;
- authorization;
- cookies;
- OAuth tokens;
- API secrets;
- pairing secret.

## Retenção inicial

- browser screenshots: 7 dias
- debug logs: 14 dias
- application logs: 30 dias
- audit/domain events: permanente
- price history: permanente
- publications: permanente

## Backup

Usar mecanismo consistente de backup do SQLite.

Pacote:
```text
backup_TIMESTAMP/
├── radar.db
├── config/
├── knowledge/
├── manifest.json
└── checksums.sha256
```

Excluir:
- secrets;
- cookies;
- browser profile;
- diagnostics temporários;
- caches.

Retenção inicial:
- 7 diários;
- 4 semanais;
- 3 mensais.

Ao menos uma cópia deve ficar fora da VM, no host.

## Restore

Operação explícita:
```text
PAUSE
→ validate backup
→ safeguard current state
→ restore db/config/knowledge
→ migrations se necessárias
→ integrity check
→ recovery
→ retomar diagnóstico e processamento seguro com envios bloqueados
→ reconciliar intervalo posterior ao backup
→ liberar envios sujeitos às políticas vigentes
```

Restore nunca é automático.

Um backup pode não conter publicações realizadas após sua criação. A ausência de um registro no banco restaurado não prova que o envio remoto não ocorreu. Até reconciliar esse intervalo, manter os envios bloqueados, inclusive jobs recuperados e novas publicações. Registrar a evidência e a decisão de reconciliação em auditoria; resultados desconhecidos suspendem a publicação afetada e geram HumanAction, sem reenvio automático, conforme `adr/0001-unknown-publication-result.md`.

Após desastre completo, sessões/secrets precisam ser reconfigurados.

## Startup validation

```text
load config
→ validate
→ load knowledge
→ validate
→ database check
→ migrations check
→ recovery
→ workers
```

Migration failure impede side effects.

## Upgrade

```text
DRAINING
→ backup
→ stop
→ update code
→ dependency sync
→ migrate
→ integrity check
→ restart
→ doctor
```

## Time and money

Dedupe/receipt/vínculo de destino e auditoria persistem independentemente de mensagens temporárias WA, cache ou bubble removido. Retenção não pode apagar proteção necessária contra reenvio/reconciliação; restore segue bloqueio dos envios até reconciliar intervalo pós-backup.

- timestamps persistidos em UTC;
- timezone operacional configurado, alvo `America/Maceio`;
- dinheiro não usa floating point binário como representação de domínio.

## Low disk

Primeiro limpar:
- diagnostics expirados;
- logs;
- temp.

Persistindo nível crítico:
- pausar discovery;
- HumanAction.
