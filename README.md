# Radar Engine V1, pacote canônico de SDD

Este pacote consolida as 13 rodadas de planejamento aprovadas para a automação de afiliados das marcas **Radar Beauty** e **Casa em Ordem**.

O objetivo da V1 é executar, em um nó local persistente, o fluxo:

`descobrir → normalizar → historizar → pontuar → revisar com IA → aprovar → gerar link afiliado → gerar conteúdo → revalidar → publicar → monitorar`

Marketplaces iniciais:
- Mercado Livre
- Shopee

Destinos iniciais:
- Telegram
- Canais do WhatsApp

## Ordem de leitura para implementação

1. `AGENTS.md`
2. `docs/00_SDD_MASTER.md`
3. `docs/01_SCOPE_AND_PRINCIPLES.md`
4. Documento específico da issue
5. `docs/DECISION_LOG.md`
6. `docs/13_QA_ACCEPTANCE_MATRIX.md`
7. `docs/14_DELIVERY_PLAN.md`
8. `docs/BROWSER_RECONNAISSANCE.md` antes de qualquer adapter real de navegador

## Regra de autoridade

Em caso de divergência:
1. SDD e Decision Log
2. Contratos de domínio e dados
3. Acceptance Criteria e testes
4. Código
5. Comentários

O agente não deve redesenhar silenciosamente uma decisão aprovada. Se encontrar inviabilidade técnica, deve registrar um `ARCHITECTURE_CONFLICT` com evidência, impacto e alternativas.

## Fonte funcional

Este pacote foi consolidado a partir das rodadas SDD-01 a SDD-13 e das premissas do arquivo `Plano_Mestre_Radar_Beauty_Casa_em_Ordem_v1.4.docx`.

O arquivo original não precisa ser usado como contrato de implementação quando houver especificação equivalente neste pacote, mas continua sendo referência de negócio para as duas marcas.

## Desenvolvimento local

Toolchains fixadas: Python 3.13.16 (`.python-version`, gerenciado por `uv`) e Node LTS + pnpm (`packageManager` no `package.json`).

```bash
uv sync                       # cria .venv e instala ruff, pyright, pytest e hypothesis
uv run ruff check .           # lint Python
uv run ruff format --check .  # formatação Python
uv run pyright                # types Python
uv run pytest                 # testes seguros, sem credenciais

pnpm install                  # workspace TypeScript
pnpm lint && pnpm typecheck && pnpm test
```

Operação local da fundação (TKT-01):

```bash
uv run radarctl migrate       # aplica migrations até head (cria o diretório de dados quando necessário)
uv run radarctl status        # saúde por CLI; sai != 0 quando não operacional
uv run radarctl version
uv run radar-api              # API local em 127.0.0.1:8000 (GET /health, GET /version)
```

Testes live (browser/IA/Telegram/WhatsApp) são opt-in e ficam fora da suíte padrão.
