# ADR-0003 — Stack: 100% open/free, com LLM atrás de interface trocável

- **Status:** Aceita
- **Data:** 2026-06-03
- **Relacionada:** [ADR-0001](0001-arquitetura-dual-path.md) (arquitetura), [ADR-0002](0002-fio-condutor-caso-b-consignado.md) (escopo)

## Contexto

Era preciso escolher o stack (embeddings, busca, store, LLM de geração) sob a restrição do usuário: **preferência por tudo open/free; só pagar uma API se a diferença de qualidade for grande**.

## Decisão

**Stack 100% open/free**, com o LLM de geração atrás de uma **interface trocável**:

| Camada | Escolha | Custo |
|---|---|---|
| Embeddings (denso) | **BGE-M3** (multilíngue, ótimo p/ PT) — local | $0 |
| Léxico | **BM25** (FTS do DuckDB ou `rank-bm25`) | $0 |
| Rerank | **bge-reranker-v2-m3** — local | $0 |
| Store | **DuckDB** — um só store p/ estruturado (séries Bacen) + índice vetorial (VSS) + FTS | $0 |
| Numérico | **Python/SQL determinístico** (market share, guidance-vs-realizado) | $0 |
| Geração/síntese | **Interface `LLMClient` trocável** — default: Claude Code in-loop / free-tier (Gemini, Groq) / Ollama local | $0 |

## Justificativa

1. **Os 50% de maior peso não dependem do gerador.** Retrieval (25%) + eval (25%) dependem de embeddings + busca + rerank + metadados. O fact-check ([../pesquisa/evidencias-verificadas.md](../pesquisa/evidencias-verificadas.md)) mostrou que **trocar o gerador moveu <0,3%** — "o gargalo é a recuperação, não o LLM".
2. **BGE-M3 é forte em PT/finanças** — competitivo com (e às vezes melhor que) embeddings pagos da OpenAI nos benchmarks que verificamos. Para um corpus em português, é a escolha certa independentemente de custo.
3. **Números são computados em código**, não gerados pelo LLM → o gerador só narra o resultado já calculado e cita a fonte (tarefa fácil, ao alcance de modelos open).
4. **O case permite rodar no próprio Claude/Codex** → a síntese pode rodar dentro do Claude Code (qualidade Claude, custo $0, sancionado pelo enunciado).
5. **Citação e recusa são estruturais** (limiar de score / SQL vazio), não dependem do "bom senso" do LLM.

## Interface trocável (o ponto-chave da restrição do usuário)

O LLM fica atrás de `LLMClient.generate(prompt, context) -> answer+citations`, com adaptadores: `claude_code` (default), `gemini_free`, `groq_free` (Llama 3.3 70B), `ollama`, `anthropic`. Trocar de provider = mudar `LLM_PROVIDER` no `.env` (uma linha). Isso permite **A/B**: se algum dia a diferença justificar, paga-se um plano pequeno e troca-se sem refatorar. Expectativa honesta: **não será necessário** para esta rubrica.

## Consequências

- **Eval de retrieval + recusa roda 100% automático e grátis** (não precisa de LLM): hit@k, precision@k, recall@k, MRR, taxa de recusa correta.
- **Faithfulness** usa LLM-as-judge (Claude Code in-loop ou free-tier) sobre as ~10 perguntas — barato.
- Modelos baixam localmente (~3 GB: BGE-M3 + reranker); CPU dá conta de 500+ docs (mais lento que GPU, aceitável). Documentar no README.
- Sem dependência de chave paga para o caminho crítico → reprodutível por qualquer avaliador.
