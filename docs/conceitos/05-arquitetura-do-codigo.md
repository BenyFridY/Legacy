# Aula 5 — A arquitetura do código (o mapa das pastas)

> Onde cada conceito das Aulas 1-4 vira código, e o que acontece em cada etapa.

## O fluxo completo

```
╔═ FASE 1 — PREPARAÇÃO (offline, roda quando chega dado novo) ═══════════════════╗
║                                                                                ║
║   ingestion/  ── traz dado CRU das fontes públicas ──┐                         ║
║      bacen.py    → linhas (banco, período, modalidade, saldo)   ─┐             ║
║      releases.py → PDFs (releases/transcrições) → texto           │            ║
║                                                                   │            ║
║         ┌─────────────────────────────────┐      ┌───────────────▼──────────┐ ║
║         │ structured/  (NÚMEROS)           │      │ index/  (TEXTO)          │ ║
║         │  store.py: carrega no DuckDB     │      │  chunking.py: corta      │ ║
║         │  market_share.py: cálculos (SQL) │      │  embed.py: BGE-M3→vetor  │ ║
║         └─────────────────────────────────┘      │  store_texto.py: idx     │ ║
║                                                   │   DuckDB (vetor+metadados)│ ║
║                                                   └──────────────────────────┘ ║
╚════════════════════════════════════════════════════════════════════════════════╝

╔═ FASE 2 — CONSULTA (roda a cada pergunta) ═════════════════════════════════════╗
║                                                                                ║
║   pergunta ─► router/ ─┬─ número ─► structured/  (roda SQL: calcula)      ─┐    ║
║                        ├─ texto  ─► retrieval/   (BM25+vetor+RRF→rerank)   ┤    ║
║                        └─ ambos  ─► os dois (ex.: B3 promete × entrega)    │    ║
║                                                                            ▼    ║
║                                          generation/  (monta prompt + LLM)      ║
║                                              └─► resposta COM CITAÇÃO            ║
║                                                  ou RECUSA (se não há base)      ║
╚════════════════════════════════════════════════════════════════════════════════╝

   eval/  ── mede tudo (retrieval, recusa, faithfulness) ── roda sempre
```

## O mapa das pastas

> Estado: **tudo abaixo está construído e testado** (suíte verde). A coluna marca ✅.

| Pasta / arquivo | Responsabilidade (uma só) | Conceito | Status |
|---|---|---|---|
| `config.py` | constantes: bancos do núcleo, modalidades, URLs do Bacen, modelos, caminhos | — | ✅ |
| `ingestion/` | **coletar** dado cru (API do Bacen; PDFs via CDN mziq). Não calcula nada. | Aula 1, etapa 1 | ✅ |
| `structured/` | **caminho dos números**: tabela DuckDB + market share em SQL (`store.py`) | Aula 4 | ✅ |
| `index/` | **preparar o texto**: chunking + embeddings (BGE-M3) + tabela de vetores+meta | Aulas 1-2 | ✅ |
| `retrieval/` | **caminho do texto**: busca híbrida (BM25+vetor, fusão RRF) + rerank | Aulas 2-3 | ✅ |
| `router/` | **decidir** texto vs. número (determinístico) + modalidade/período | Aula 4 | ✅ |
| `generation/` | **montar prompt + LLM** (interface trocável) + citação/recusa | Aulas 1, 4 | ✅ |
| `eval/` | **medir**: retrieval (hit@k/MRR) + recusa + faithfulness | "comece pelo eval" | ✅ |

## Princípios da organização (perguntas de banca)

1. **Cada pasta tem UMA responsabilidade.** Coletar (`ingestion`) ≠ processar número (`structured`) ≠
   processar texto (`index`) ≠ buscar (`retrieval`) ≠ decidir (`router`) ≠ responder (`generation`)
   ≠ medir (`eval`). Fácil de testar e de explicar.
2. **Os dois caminhos são separados de propósito** (ADR-0001). Número e texto não se misturam até a
   resposta final — é o que evita o "RAG ingênuo" que quebra nos números.
3. **A ingestão alimenta os dois lados.** O dado cru entra uma vez; `structured/` e `index/` consomem.
4. **O DuckDB é um store só**: tabela de números + vetores + metadados (o BM25 é calculado em
   memória em `retrieval/lexical.py`, via rank-bm25). Menos peças móveis = mais reprodutível.
5. **Dependências fluem num sentido só:** `ingestion → {structured, index} → {retrieval} → router →
   generation`, com `config` no centro e `eval` medindo de fora. Sem importações circulares.

## Ordem em que foi construído (e por quê)

1. **`structured/` primeiro** (Bacen + `market_share`) — é o nosso diferencial, a API já está validada
   ao vivo, e resolve cedo o risco nº 1 (o crosswalk do consignado). Dá o "gold" numérico do eval.
2. Depois `ingestion/releases` + `index/` (texto) → `retrieval/`.
3. Depois `router/` + `generation/`.
4. Por fim `eval/runner.py` (+ os eval de retrieval e faithfulness) amarra tudo e mede contra `eval/questions.yaml`.
