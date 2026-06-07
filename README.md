# Legacy — Sistema de Retrieval para Research de Equities

> Case de estágio AI · **Legacy Capital — Equities Team**

Fundação **genérica** de retrieval para pesquisa de equities: uma base **ligada e auto-alimentada**
(ingestão direto da fonte, sem upload manual) que lida tanto com **texto** (earnings releases,
transcrições, notícias) quanto com **dados estruturados** (séries do Banco Central, financials), e
que foi **provada a fundo** num fio condutor — bancos brasileiros, crédito **consignado**.

**Duas regras inegociáveis (garantidas por construção, não por sorte do prompt):**
1. Toda resposta **cita a fonte** — a citação é anexada **por código**, a partir dos trechos que
   embasaram a resposta; não dependemos de o LLM lembrar de citar.
2. A resposta vem **estritamente da base** — se a informação não está lá, o sistema responde
   *"não disponível na base"* (com o **motivo**) em vez de alucinar.

---

## Abordagem em uma frase

**Não é RAG ingênuo.** É um **sistema dual-path roteado**:

- **Caminho de texto** → busca **híbrida** (densa BGE-M3 + BM25) fundida por **RRF** + **filtro de
  metadados** (entidade, período, tipo de doc) + **rerank** (cross-encoder).
- **Caminho estruturado** → **store SQL** (DuckDB) para números e séries, com o **cálculo feito em
  código/SQL** (não pelo LLM) — auditável por re-execução.
- **Roteador determinístico** (regras, **não** um agente LLM aberto) decide o caminho e une os dois.
- **Citação e recusa** garantidas por construção.

**Por que o caminho estruturado** (e não jogar tudo no LLM): o gargalo é a **recuperação**, não a
aritmética. (1) Agregação derrota o top-k; (2) embeddings são **cegos a magnitude numérica**; (3)
número computado em código é **auditável e citável**. O racional completo, as alternativas
rejeitadas (RAG ingênuo, long-context, fine-tuning, GraphRAG) e as **evidências verificadas
adversarialmente** estão em [`docs/decisions/0001-arquitetura-dual-path.md`](docs/decisions/0001-arquitetura-dual-path.md)
e [`docs/pesquisa/evidencias-verificadas.md`](docs/pesquisa/evidencias-verificadas.md).

---

## Resultados do eval

> *"Comece pelo eval."* Medimos antes de otimizar. Saídas **reproduzíveis** (com comandos) em
> [`docs/resultados-eval.md`](docs/resultados-eval.md). Corpus de texto = **Itaú 4T25** (514 fichas /
> 169 páginas); números = **Bacen IF.data** (6 trimestres).

**1) Qualidade de retrieval — hit@k / MRR (BGE-M3 + reranker reais).** Gold por **página**, curado
por busca **lexical + leitura** (independente do embedding → anti-circular), com **2 sondagens-limite
de propósito**:

| conjunto | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| **6 sondagens realistas** | — | **100%** | 100% | — |
| **8 sondagens** (inclui 2 limite) | 62,5% | 75,0% | 75,0% | **0,688** |

As 2 "difíceis" (gíria *"calote"*; paráfrase *"descontado direto da folha"*) **falham como esperado**
e viram narrativa de engenharia (ver abaixo) — não são escondidas.

**2) Recusa por escopo — Estágio 1 (roteador determinístico, sem modelo).** 11 perguntas, 3
categorias de comportamento + 1 distrator anti-over-recusa:

| métrica | valor |
|---|---|
| acurácia de comportamento | **11/11** |
| recusa correta (dos que deviam recusar) | **100%** |
| over-recusa (recusou um respondível) | **0%** |
| alucinação (respondeu o que devia recusar) | **0** |

**3) Resolução do Caso B — ponta a ponta (modelos reais, incl. Groq/Llama 3.3 70B).** As 3
categorias resolvidas ao vivo: *lucro Itaú 4T25* **R$ 12,3 bi** (pág. 8); *consignado Itaú 4T25*
**R$ 75,3 bi** (pág. 21); *market share BB consignado* **19,9% → 20,1%** (série trimestral, IF.data,
SQL); recusas **R1** (futuro 2027) e **R2** (Nubank IFRS × Itaú Cosif). Saída completa em
[`docs/resultados-eval.md`](docs/resultados-eval.md).

> **Honestidade estatística:** `n=11` é **sanidade forte, não estatística de população**. O Estágio 1
> mede só escopo; a **calibração do gate de evidência (Estágio 2)** e o **faithfulness por LLM-juiz**
> ainda são trabalho aberto (ver *Fraquezas* e ADR-0005, planejado).

---

## Arquitetura

```
                          pergunta
                             │
                    ┌────────▼─────────┐
                    │  ROTEADOR (regras)│  Estágio 1: escopo + caminho
                    └────────┬─────────┘
        ┌─────────────┬──────┴───────┬──────────────────┐
        ▼             ▼              ▼                  ▼
  não_respondível  doc_unico      computada         multi_fonte
   (recusa por    (texto:        (números:          (cruza
    escopo,        híbrido+       market share        DECLARADO no
    com motivo)    rerank +       em SQL,             texto  ×
                   gate de        determinístico,     COMPUTADO no
                   evidência →    auditável)          IF.data; LLM
                   LLM redige)                        reconcilia)
                        │
                  Estágio 2: nota do reranker < limiar → recusa
                        │
                  citação ESTRUTURAL anexada por código (dedup)
```

**Recusa em dois estágios, por responsabilidades separadas:**
- **Estágio 1 — escopo** (roteador): pergunta fora da cobertura → recusa *antes* de buscar. Três
  portões: **R1** (período no futuro além de 2026), **R2** (cruza bases contábeis incompatíveis —
  IFRS × Cosif — como **conjunção** de sinais, **nunca** pelo nome do banco), **R3** (pede frase
  *verbatim* que não existe na base).
- **Estágio 2 — evidência** (gate): mesmo no escopo, se a melhor nota do reranker fica **abaixo do
  limiar**, recusa em vez de redigir sobre evidência fraca.

**Roteador determinístico** (e não agente LLM aberto) é uma escolha de projeto deliberada: como o
eval pesa **50%** da nota e roda o sistema repetidamente, *mesma pergunta → mesmo caminho* mantém a
avaliação **reprodutível e auditável**. O preço (fragilidade léxica) é assumido e **medido** no eval.

---

## Decisões de chunking

- **Página = fronteira de chunk e âncora de citação.** Uma ficha **nunca cruza páginas** — assim a
  citação aponta para uma página real do documento. (`legacy_rag/index/chunking.py`)
- **~1200 caracteres por ficha, ~200 de sobreposição**, quebrando em **fim de frase / quebra de
  linha** — nunca no meio de uma unidade. (constantes `ALVO_CHARS=1200`, `OVERLAP_CHARS=200`)
- **Duas formas por ficha:** `.indexavel` = cabeçalho de metadados (`banco | período | tipo |
  página`) + trecho, que vai para o **embedding** (dá contexto à busca); `.texto` = trecho cru, que é
  o que se **cita**.

---

## Como a base é alimentada (ligada / automática)

Critério nº 1 do case. **Sem upload manual** — o sistema busca na fonte e indexa sozinho:

- **Texto (releases/transcrições):** `baixar(url)` pega os **bytes crus do PDF no CDN mziq**
  (`filemanager-cdn.mziq.com`) — *não* pela página de RI, que responde **403** a cliente
  programático. `extrair_paginas` (pypdf) devolve uma string **por página**; daí chunking → embedding
  (BGE-M3) → store. Tudo encadeado em `ingerir_release` e **idempotente por (banco, período, tipo)**.
- **Números (carteira por modalidade + cadastro):** API **Olinda IF.data** do Banco Central. A
  carteira PF por modalidade vem em `TipoInstituicao=2 / Relatório=11`; o **cadastro** mapeia cada
  instituição → **conglomerado prudencial**, e o market share é agregado **por conglomerado** (soma os
  vários CNPJs de um mesmo banco) — divisão `carteira_banco / Σ sistema` feita **em SQL**. Ingestão
  **idempotente por período**. (`scripts/ingerir_numeros.py`, `legacy_rag/structured/`)

> Hoje a base de **texto** tem **um documento ingerido (Itaú 4T25)**, suficiente para provar o
> pipeline e o eval de retrieval ponta a ponta. A camada de **números** tem 6 trimestres
> (202309–202412). Ampliar para BB/Bradesco e crescer para 500+ documentos é, em grande parte,
> **projeto documentado** (manifesto + dedup por hash de conteúdo + embedding incremental) — ver
> *Fraquezas e escala*.

---

## Como rodar

Stack **100% open/free**, sem chave paga no caminho crítico — ver [ADR-0003](docs/decisions/0003-stack-open-free.md). Python ≥ 3.11.

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          :: opcional: LLM_PROVIDER=groq_free + GROQ_API_KEY p/ a síntese

:: no Windows, prefixe os scripts pesados com estas 3 variáveis (carrega torch sem conflito de OpenMP):
set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8

python -m pytest -q                      :: 104 testes — sem rede, sem torch, sem chave (fakes)
python -m legacy_rag.eval.runner         :: matriz de recusa-por-escopo (sem modelo)
python scripts\ingerir_numeros.py        :: alimenta carteira_pf + cadastro (Bacen IF.data)
python scripts\prova_retrieval_real.py   :: ingere Itaú 4T25 + busca real (baixa BGE-M3 ~ na 1ª vez)
python scripts\eval_retrieval_real.py    :: hit@k / MRR reais
python scripts\resolver_caso.py          :: resolve o Caso B ponta a ponta (LLM real, se .env tiver chave)
```

Os **104 testes** rodam em segundos e provam o **fluxo e as recusas** com modelos **falsos** (encoder/
reranker/LLM injetáveis) — sem baixar nada. A **qualidade semântica** entra com os modelos reais nos
scripts. O LLM fica atrás de uma interface trocável (`LLMClient`): o provedor ativo é **Groq
(Llama 3.3 70B)**, selecionável por `LLM_PROVIDER` no `.env`; sem chave, o sistema ainda roteia,
recupera, computa números e recusa — só não redige o texto livre.

---

## Estrutura do repositório

```
legacy_rag/
  config.py            núcleo de bancos, modalidade, modelos, limiares
  env.py               carregador minimalista de .env (ambiente tem precedência)
  ingestion/           base auto-alimentada: baixar release (CDN) → orquestra baixar→chunk→embed→store
  index/               chunking (página=âncora) · embeddings (BGE-M3, interface trocável) · store de texto (DuckDB)
  retrieval/           vetorial (cosseno) · lexical (BM25) · híbrido (RRF) · rerank (cross-encoder)
  structured/          Bacen IF.data · market share por conglomerado (SQL) · store DuckDB
  router/              roteador determinístico (escopo R1/R2/R3 + caminho)
  generation/          gate de evidência · geração com citação estrutural · LLMClient (Groq)
  pipeline.py          orquestrador: pergunta → resposta citada ou recusa explicada
  eval/                métricas (hit@k, P@k, R@k, MRR, matriz de recusa) · eval de retrieval · runner de escopo
eval/
  questions.yaml       11 perguntas (3 categorias de comportamento + 1 distrator anti-over-recusa)
  retrieval_gold.yaml  8 sondagens (gold por página; 2 limite de propósito)
docs/
  decisions/           ADRs 0001–0004 — a "progressão de raciocínio" que o case pede
  conceitos/           5 docs didáticos (RAG, embeddings, BM25/híbrida, números/SQL, arquitetura do código)
  pesquisa/            fact-check adversarial das afirmações técnicas
  resultados-eval.md   saídas reproduzíveis do eval (lastro dos números deste README)
scripts/               ingerir_numeros · prova_retrieval_real · eval_retrieval_real · resolver_caso
tests/                 19 arquivos · 104 testes
```

---

## Fraquezas e o que faria diferente em escala

Documentado com honestidade — é o que o case pede.

- **Corpus de texto pequeno hoje:** só o Itaú 4T25 está ingerido. O pipeline e o eval de retrieval
  estão provados nele; ampliar para BB/Bradesco/Santander e múltiplos períodos é trabalho de
  ingestão (o código já é genérico).
- **Busca exata, sem índice aproximado:** vetorial é **cosseno brute-force** e o BM25 é reconstruído
  em memória por consulta. Ótimo e simples no tamanho atual; em escala (>~100k fichas) entraria um
  índice **HNSW** e um **FTS persistido** — projetado, não construído (sem benchmark medido aqui).
- **Limiar do gate de evidência = 0,30 é placeholder**, não calibrado. Falta varrer o "joelho"
  over-recusa × alucinação contra um mini-gold rotulado. As notas observadas (~0,71/0,73 quando há
  resposta vs ~0,5 quando não há) dão a intuição, mas o número final precisa de calibração.
- **Reranker que não discrimina:** com gíria, o cross-encoder empata tudo em ~0,5 e *apaga* o bom
  sinal do vetorial denso. Candidato a ADR: **cair de volta para a ordem do RRF** quando o reranker
  não separa.
- **Lacunas do roteador (R4/R5/R6):** distinguir *realizado* de *guidance* dentro de 2026 (R4) e
  métricas ainda não ingeridas (R6) caem hoje no Estágio 2. Roadmap em ADR-0005 (planejado).
- **Dedup só por (banco, período, tipo):** falta dedup por **hash de conteúdo** para reingestão em
  escala — projetado, não construído.
- **Faithfulness ainda não medido:** o eval cobre retrieval (hit@k/MRR) e escopo (Estágio 1); falta
  o **LLM-juiz** medindo fidelidade da resposta ao contexto.

---

## Decisões (ADRs) — a progressão de raciocínio

| ADR | Decisão |
|---|---|
| [0001](docs/decisions/0001-arquitetura-dual-path.md) | Arquitetura **dual-path roteada** (não RAG ingênuo) |
| [0002](docs/decisions/0002-fio-condutor-caso-b-consignado.md) | Fio condutor **Caso B · consignado · BB+Bradesco+Itaú** (Nubank = não-respondível orgânico) |
| [0003](docs/decisions/0003-stack-open-free.md) | Stack **100% open/free**; LLM atrás de interface trocável |
| [0004](docs/decisions/0004-ingestao-larga-prova-focada.md) | **Ingestão larga, prova focada** |
| 0005 | *(planejado)* Escala + lacunas do roteador + fallback do reranker + calibração do gate |

---

## Nota sobre uso de IA

Construído com apoio de IA (Claude), conforme **permitido e encorajado** pelo case. Toda decisão está
documentada em `docs/decisions/` e é defensável — incluindo um passo de **verificação adversarial**
das afirmações técnicas (`docs/pesquisa/`) e uma **auditoria automatizada do próprio código** antes de
escrever este README, para que nenhuma afirmação aqui ultrapasse o que o código realmente faz.
