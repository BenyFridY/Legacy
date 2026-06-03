# Legacy — Sistema de Retrieval para Research de Equities

> Case de estágio AI · **Legacy Capital — Equities Team**

Fundação **genérica** de retrieval para pesquisa de equities: uma base **ligada e auto-alimentada** (ingestão direto da fonte, sem upload manual), que aguenta volume de verdade (500+ documentos e crescendo) e lida tanto com **texto** (transcrições de calls, earnings releases, notícias) quanto com **dados estruturados** (séries do Banco Central, ANP, financials).

**Duas regras inegociáveis:**
1. Toda resposta **cita a fonte**.
2. A resposta vem **estritamente da base** — se a informação não está lá, o sistema responde *"não disponível na base"* em vez de alucinar.

---

## Abordagem em uma frase

**Não é RAG ingênuo.** É um **sistema dual-path roteado**:

- **Caminho de texto** → busca **híbrida** (BM25 + densa) + **filtro de metadados** (entidade, período, tipo de doc) + **rerank**.
- **Caminho estruturado** → **store SQL** (DuckDB/SQLite) para números e séries, com **cálculo feito em código** (não pelo LLM).
- **Roteador determinístico** decide o caminho e une os dois por `(entidade, período)`.
- **Citação e recusa** garantidas por construção (cada chunk/linha carrega sua fonte; recusa quando a recuperação volta vazia).

> O racional completo, as alternativas rejeitadas (RAG ingênuo, long-context, fine-tuning, GraphRAG) e as **evidências verificadas** estão em
> [`docs/decisions/0001-arquitetura-dual-path.md`](docs/decisions/0001-arquitetura-dual-path.md).

---

## Estado atual (roadmap → entregáveis do case)

| | Entregável | Status |
|---|---|---|
| ✅ | Decisão de arquitetura documentada (ADR-0001) | feito |
| ✅ | Base de evidências verificada (fact-check) | feito |
| ✅ | Fio condutor escolhido: **Caso B · consignado · Bradesco+BB+Itaú** (ADR-0002) | feito |
| ⬜ | **Eval harness** (~10 perguntas; 3 categorias: doc-único / multi-fonte / não-respondível) | a fazer — *próximo* |
| ⬜ | Camada de ingestão (Bacen Olinda IF.data + releases via CDN mziq) | a fazer |
| ⬜ | Indexação dual (texto híbrido + store estruturado DuckDB) | a fazer |
| ⬜ | Retrieval + roteador + geração com citação/recusa | a fazer |
| ⬜ | Resolução do Caso B (B1 guidance-vs-realizado + B3 share computado) | a fazer |
| ⬜ | README final + apresentação | a fazer |

---

## Como rodar

> *Em construção.* Stack: **Python 3.13**. Instruções de setup (`.env`, dependências, comando do eval) serão adicionadas conforme o código nasce.

## De onde vêm os dados / como a base é alimentada

> Fontes do Caso B (consignado), todas públicas e acessíveis programaticamente — ver [ADR-0002](docs/decisions/0002-fio-condutor-caso-b-consignado.md):
> - **Estruturado:** Banco Central — **IF.data** (trimestral, API Olinda OData) e **SCR.data** (mensal, CSV) → carteira por instituição/modalidade; market share = `carteira_banco / carteira_sistema` *computado*. *(API Olinda já validada ao vivo.)*
> - **Texto:** releases / "Análise do Desempenho" e transcrições de **BB, Bradesco e Itaú** — baixados como bytes crus do **CDN mziq** (não pelas páginas de RI, que dão 403) e extraídos com `pdftotext`/`pypdf`.
> - **Não-respondível:** Nubank (USD/IFRS via Form 20-F) — incomparável com os peers BRL/Cosif.

## Decisões de chunking

> *Em construção* (será uma ADR dedicada): chunking ciente de estrutura (turnos de fala em transcrições, seções em filings), tabelas como unidade atômica, header de metadados por chunk.

## Resultados do eval

> *Em construção.* "Comece pelo eval" — medir antes de otimizar.

## Fraquezas e o que faria diferente em escala

> *Em construção.* Documentado com honestidade conforme o sistema evolui.

---

## Estrutura do repositório

```
.
├── README.md
├── docs/
│   ├── decisions/        # ADRs — registro de decisões (a "progressão de raciocínio")
│   │   ├── README.md
│   │   └── 0001-arquitetura-dual-path.md
│   └── pesquisa/
│       └── evidencias-verificadas.md
└── (ingestion/ · index/ · retrieval/ · eval/ — nascem nos próximos commits)
```

## Nota sobre uso de IA

Construído com apoio de IA (Claude), conforme **permitido e encorajado** pelo case. Toda decisão é documentada em `docs/decisions/` e defensável — incluindo um passo de **verificação adversarial** das afirmações técnicas (ver `docs/pesquisa/`).
