# Evidências verificadas (fact-check adversarial)

Antes de fixar a arquitetura ([ADR-0001](../decisions/0001-arquitetura-dual-path.md)), cada afirmação quantitativa de apoio passou por uma **verificação adversarial**: um checador por afirmação, com a tarefa de **refutá-la** contra a fonte primária (PDF do arXiv, blog oficial, repositório do benchmark, portal do Bacen).

**Resumo:** 7 confirmadas · 5 parciais · 1 refutada. **Nenhuma era crítica para a decisão de arquitetura** — todas eram "de apoio", e a conclusão se sustenta no conjunto.

> **Como usar:** estes números servem para a apresentação, mas **abra o link primário antes de citar** — vários papers são de 2026 e a verificação foi via web (agentes podem errar).

| Afirmação | Veredito | Fonte / correção |
|---|---|---|
| RAG ingênuo erra ~99% em agregação | 🟡 Parcial | AGGBench, **arXiv 2602.01355**. Recall do RAG ingênuo = **0,008** (não "0,008–0,092"; o 0,092 era do HippoRAG). Direção certa. |
| FinanceBench: 19% (ingênuo) → 87,3% (agêntico); 100% numérico | ✅ Confirmado | Dewey (`meetdewey.com/blog/financebench-eval`); base de 19% do paper Patronus **arXiv 2311.11944**. É Opus 4.6. |
| "Com contexto perfeito, LLM só acerta 0,35 → nunca deve calcular" | ❌ **Refutado** | Na verdade **72–79%** de acerto com contexto oráculo (T2-RAGBench, **arXiv 2506.12071**). Gargalo é recuperação, não aritmética. Não usar o "0,35". |
| Aritmética = 38,8% dos erros; Program-of-Thought elimina 88% | ✅ Confirmado | FinAgent-RAG, **arXiv 2605.05409** ("88,0% ... de 208 para 25"). |
| Embeddings cegos a números: $15k→$65k = 0,9998; gap 1.459× | ✅ Confirmado | RAGShield, **arXiv 2604.00387** (verbatim). |
| BM25 0,644 > denso 0,587; híbrido 0,695; +rerank 0,816 (Recall@5) | ✅ Confirmado | **arXiv 2604.01733**, Tabela I (verbatim). |
| Contextual Retrieval: −35% / −49% / −67% de falhas | ✅ Confirmado | `anthropic.com/news/contextual-retrieval` (verbatim). |
| Header de metadados 50-60%→72-75%; ~1.800 chars ótimo; speaker-turn +34% | 🟡 Parcial | Os 2 primeiros são da **Snowflake** (verbatim). O **+34% é da FinTech Studios**, não da Snowflake — atribuição corrigida. |
| FinRetrieval: Opus 19,8% (web) → 90,8% (APIs estruturadas) | ✅ Confirmado | **arXiv 2603.04403** / benchmark Daloopa (verbatim). |
| Long-context: ~60% recall multi-fato; ~1.250× custo | 🟡 Parcial | Recall ~60% **sólido** (relatório Gemini 1.5, arXiv 2403.05530). Custo 1.250× é **estimativa grosseira**, mal atribuída. |
| Fine-tuning < RAG p/ fatos novos; FT "não cita / não recusa" | 🟡 Parcial | RAG > FT confirmado (Ovadia, **arXiv 2312.05934**, 0,875 vs 0,504). "Não cita/recusa" é propriedade geral do FT, **não** está no paper. |
| GraphRAG ~$33k; LazyGraphRAG 0,1% do custo; HybridRAG bate ambos | 🟡 Parcial | LazyGraphRAG 0,1% confirmado (Microsoft). $33k = estimativa de blog. HybridRAG (BlackRock+NVIDIA, **arXiv 2408.04948**) bate ambos só em **relevância**; em fidelidade **empata** com GraphRAG. |
| **Bacen: market share calculável via IF.data (trim.) + SCR.data (mensal), API pública** | ✅ **Confirmado ao vivo** | API **Olinda OData** consultada: retornou dados reais por instituição (ex.: ABC-Brasil, período 202403). Premissa do **Caso B** é real e reprodutível. |

## Implicação para o design

O caminho estruturado + cálculo em código continua certo — mas justificado por **(1) agregação quebra top-k, (2) embeddings são cegos a números, (3) código dá número auditável/citável** — e **não** por "LLM não sabe somar" (refutado).
