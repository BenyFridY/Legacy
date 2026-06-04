# Aula 1 — O que é RAG (o panorama)

> Material de estudo + rascunho de apresentação. Linguagem simples de propósito.

## O problema

A equipe de equities precisa responder perguntas sobre **milhares** de documentos
(releases, transcrições de call, notícias, tabelas do Bacen) que **crescem toda semana**.
Um humano lê ~50; a cobertura real são milhares. A pergunta do case:

> Como responder perguntas sobre uma montanha de documentos **citando a fonte** e **sem inventar**?

## Duas ideias ingênuas que falham (e motivam o RAG)

1. **"Joga tudo no Claude/ChatGPT e pergunta."**
   - Não cabe (limite da janela de contexto; 500+ docs = milhões de palavras).
   - Mesmo quando cabe, o modelo "perde" fatos no meio do texto, é caro/lento, **inventa** e **não cita**.
2. **"Treina/fine-tuna um modelo nos documentos."**
   - Ele "decora" nos pesos de forma nebulosa: **não aponta a fonte**, **não sabe dizer "não sei"**,
     e a base cresce todo dia (teria que re-treinar sempre).

Ambas falham justamente nas **duas regras inegociáveis**: citar a fonte e recusar quando não sabe.

## O que é RAG

**Analogia: prova com consulta (open-book).** O modelo não responde de cabeça — primeiro
**consulta** os documentos, acha os trechos certos e só então **escreve a resposta com base neles**,
apontando de onde tirou.

**RAG = Retrieval-Augmented Generation** (Geração Aumentada por Recuperação):
- **Retrieval** — recuperar os trechos certos.
- **Augmented** — colar esses trechos no pedido enviado ao modelo.
- **Generation** — o modelo gera a resposta *com base naqueles trechos*.

## O fluxo (duas fases)

```
FASE 1 — PREPARAÇÃO (offline)
  Coletar documentos → Cortar em pedaços (chunking) → Indexar (guardar "buscável" + metadados)

FASE 2 — CONSULTA (a cada pergunta)
  pergunta → Recuperar top-k trechos → Montar pedido (pergunta + trechos + instruções)
           → Modelo gera resposta COM CITAÇÃO   (ou RECUSA se nada relevante veio)
```

As duas regras caem naturalmente:
- **Citar:** cada pedaço carrega a origem (doc, página, período).
- **Recusar:** se a recuperação não traz nada relevante, o sistema diz "não está na base".

## Insights-chave (perguntas de banca)

- **Por que chunking?** A razão nº 1 é **precisão na busca**: em vez de puxar "livros inteiros",
  você puxa "fichas etiquetadas" e manda só o trecho relevante ao LLM → busca precisa, menos ruído,
  menos alucinação, mais barato. **Trade-off:** chunk grande demais volta ao calhamaço; pequeno demais
  corta o contexto. Por isso o corte é **uma decisão**: transcrição por fala, release por seção,
  **tabela inteira = 1 chunk** (nunca partir tabela).
- **Citar vs. recusar — o que é mais difícil?** **Recusar.** Citar é quase mecânico (a etiqueta de origem
  já vem no chunk). Recusar exige o sistema "saber que não sabe" e **segurar** a tendência do LLM de
  "completar" com algo plausível — LLMs são treinados pra sempre responder. Por isso o case insiste em
  perguntas **não-respondíveis** (ex.: Nubank): é o teste que separa um sistema honesto de um que enrola.

## No nosso código

| Etapa | Pasta |
|---|---|
| Coletar | `legacy_rag/ingestion/` |
| Cortar + indexar | `legacy_rag/index/` |
| Recuperar | `legacy_rag/retrieval/` |
| Montar pedido + gerar | `legacy_rag/generation/` |
| Medir (eval) | `legacy_rag/eval/` |
