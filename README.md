<div align="center">

# ⚡ Selma — Inspeção de Subestações

**Assistente de Ordem de Serviço (OS) para inspeções elétricas** — coleta as
respostas em um chat (Streamlit ou Telegram), permite revisão/edição em formulário,
salva direto no Supabase e gera um **relatório técnico com IA (Gemini)**.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![Gemini](https://img.shields.io/badge/Google-Gemini-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

</div>

---

## 📋 Sobre

A **Selma** guia o técnico por um checklist completo de inspeção de subestação
(entrada de alimentação, proteção de média tensão, transformador, quadros,
banco de capacitores, condições gerais, serviços e observações), seguindo
**exatamente** a mesma lógica e ramificações dos fluxos originais em Typebot.

Diferenças em relação ao fluxo legado: tudo é **Python**, **desacoplado** de
qualquer app existente, salva **direto no banco** (sem edge functions) e gera o
relatório **no próprio script** via Gemini.

## ✨ Funcionalidades

- 💬 **Chat de preenchimento** com visual estilo WhatsApp (Streamlit) **ou** via **bot do Telegram**.
- 🔀 **Ramificações fiéis ao fluxo original** — transformador a seco, condutores
  Bus-Way, banco de capacitores inexistente, fusível HH, opções "OBS → Descreva a situação", etc.
- 🔑 **Login por técnico** — telefone (Streamlit) ou *compartilhar contato* (Telegram);
  lista as OS em aberto atreladas ao número.
- 📝 **Tela de revisão editável** — confira/ajuste cada resposta antes de salvar.
- 🗄️ **Salvamento incremental** no Supabase com whitelist de colunas (replica os upserts originais).
- 🤖 **Relatório técnico por IA (Gemini)** — resumo por seção + recomendações, gravado na tabela `relatory`.
- 🛟 **Salvar e relatório desacoplados** — se a IA falhar, os dados já ficam salvos e há botão para tentar de novo.

## 🏗️ Arquitetura

```
┌──────────────────────────┐         ┌──────────────────────────────┐
│   Telegram (bot.py)       │         │   Streamlit (app.py)         │
│   long polling            │         │   chat + revisão + relatório │
│                           │         │                              │
│  /start → compartilhar    │         │  login telefone → chat →     │
│  contato → escolhe OS →   │         │  revisão → salvar            │
│  responde perguntas       │         │                              │
└────────────┬──────────────┘         └──────────────┬───────────────┘
             │ grava respostas (JSON)                 │  ?draft=<token>
             ▼                                        │  abre revisão
   ┌───────────────────────┐                          │
   │ Supabase              │◄─────────────────────────┘
   │ inspection_draft      │   lê o rascunho pelo token
   │ + tabelas de checklist│
   │ + relatory (IA)       │
   └───────────────────────┘
```

Dois modos de uso, mesma base de código (`selma/`):

1. **Tudo no Streamlit** — login, chat, revisão e salvamento em um só lugar.
2. **Telegram + Streamlit** — técnico responde no Telegram; ao terminar recebe um
   link (`?draft=<token>`) que abre o formulário **já preenchido e editável** no
   Streamlit (Cloud) para revisar, confirmar e salvar.

## 📁 Estrutura

```
selma_python/
├── app.py                 # App Streamlit (chat, revisão, relatório, modo ?draft=)
├── bot.py                 # Bot do Telegram (long polling)
├── requirements.txt
├── .env.example
├── LICENSE                # MIT
└── selma/
    ├── config.py          # variáveis de ambiente (.env / st.secrets)
    ├── registry.py        # partes do checklist → tabelas/colunas (whitelist)
    ├── flow.py            # perguntas + ramificações de cada etapa (motor)
    ├── db.py              # Supabase: técnico, OS, save_checklist_part, progresso
    ├── drafts.py          # ponte Telegram ↔ Streamlit (inspection_draft)
    ├── gemini.py          # cliente Gemini (resumos / seções / recomendações)
    └── report.py          # geração e gravação do relatório (relatory)
```

## 🔧 Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|:---:|---|
| `SUPABASE_URL` | ✅ | URL do projeto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service Role Key (ignora RLS) |
| `GEMINI_API_KEY` | ✅ | Chave da Google Generative Language API |
| `GEMINI_MODEL` | — | Modelo (default `gemini-2.0-flash`) |
| `TELEGRAM_BOT_TOKEN` | bot | Token do @BotFather (só para `bot.py`) |
| `STREAMLIT_APP_URL` | bot | URL pública do app (link enviado pelo bot) |

> ⚠️ Use sempre a **Service Role Key** apenas no backend (`.env`/secrets), nunca no cliente.

## 🚀 Começando (local)

```bash
git clone https://github.com/DevJohnL/selma-inspecao.git
cd selma-inspecao

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # preencha as chaves

streamlit run app.py
```

## 💬 Preenchimento via Telegram

1. Aplique a migração da tabela `inspection_draft` no seu Supabase (ver abaixo).
2. Crie um bot no **@BotFather** e copie o token.
3. No `.env`: `TELEGRAM_BOT_TOKEN=...` e `STREAMLIT_APP_URL=` (URL do app no Cloud, ou `http://localhost:8501` para testes).
4. Rode o bot (processo separado, fica em *long polling*):
   ```bash
   python bot.py
   ```
5. No Telegram: `/start` → **compartilhar contato** → escolher a OS → responder.
   Ao final você recebe o botão **"Abrir formulário para revisar e salvar"**.

### Migração necessária (`inspection_draft`)

```sql
create table public.inspection_draft (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  token text not null unique,
  os_number bigint,
  service_order_id bigint,
  technical_id bigint,
  technical_name text,
  answers jsonb not null default '[]',
  status text not null default 'pending_review',
  saved_at timestamptz
);
create index inspection_draft_token_idx on public.inspection_draft (token);
alter table public.inspection_draft enable row level security;
```

## ☁️ Deploy no Streamlit Community Cloud

1. Tenha este repositório no GitHub.
2. Em **https://share.streamlit.io** → *Create app* → selecione o repo/branch e
   **Main file path** = `app.py`.
3. Em **Secrets**, cole (formato TOML):
   ```toml
   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
   SUPABASE_SERVICE_ROLE_KEY = "..."
   GEMINI_API_KEY = "..."
   GEMINI_MODEL = "gemini-2.0-flash"
   ```
4. **Deploy** → use a URL pública resultante como `STREAMLIT_APP_URL` no `.env` do bot.

> O `app.py` injeta automaticamente os *secrets* do Streamlit no ambiente, então a
> mesma base funciona local (`.env`) e na nuvem (`secrets`). O **bot** roda à parte
> (uma VM/serviço sempre ativo) — o Streamlit Cloud hospeda apenas o app web.

## 🧭 Etapas do checklist

`Entrada de Alimentação` · `Proteção em Média Tensão` · `Transformador` ·
`Quadro de Proteção Geral` · `Quadro Geral de Baixa Tensão (QGBT)` ·
`Banco de Capacitores` · `Condições Gerais` · `Serviços Executados` ·
`Observações Gerais` → **Relatório (IA)**

## ⚠️ Fora de escopo

- Upload de fotos (colunas `*_url` ficam `null`).
- Webhook do Telegram (usa *long polling*).
- Múltiplas instâncias de transformador/painel (usa instância fixa = 1).

## 📄 Licença

Distribuído sob a licença **MIT**. Veja [`LICENSE`](./LICENSE).
