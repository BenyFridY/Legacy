# ADR-0001 — Arquitetura: sistema dual-path roteado (não "RAG ingênuo")

- **Status:** Aceita
- **Data:** 2026-06-03
- **Contexto do projeto:** [README](../../README.md)

## Contexto

O case pede uma "fundação de RAG". A primeira pergunta honesta foi: **RAG ingênuo é a melhor opção?**
Por "RAG ingênuo" entende-se: fatiar tudo em chunks → embeddar → busca por similaridade (top-k cosseno) → enfiar os chunks no LLM → gerar resposta.

As perguntas que o case usa para avaliar **não são** "ache este parágrafo". São:
- **Agregações** ("capex total que as hyperscalers projetam") — Caso A.
- **Multi-hop temporal** ("o que foi prometido no 1T vs. realizado no 3T") — Caso B1.
- **Computações numéricas** (market share calculado do Bacen — B3; aceleração de RPO — C).

Esse é exatamente o conjunto onde a similaridade vetorial falha de forma **estrutural**.

## Decisão

Construir uma **fundação genérica dual-path com roteador determinístico**, e não um clone de NotebookLM:

1. **Caminho de texto** — busca **híbrida (BM25 + densa)** com **filtro de metadados** (`entidade`, `período`, `tipo_doc`, `fonte`) aplicado **antes** do ranqueamento, seguida de **rerank** (cross-encoder). Para discurso: transcrições, comentários de management, MD&A, notícias.
2. **Caminho estruturado** — séries numéricas (Bacen IF.data/SCR.data, financials, RPO, capex) em um **store SQL (DuckDB/SQLite)**. Toda aritmética (razões, crescimento, aceleração, market share, somas) é **computada em código/SQL**, nunca pelo LLM no texto. A linha da tabela **é** a citação.
3. **Roteador determinístico** (regras/classificador, **não** um agente LLM aberto) que classifica a pergunta em `{doc-único, multi-fonte, computada, não-respondível}` e sequencia as ferramentas. Manter o roteador determinístico é o que mantém o **eval reprodutível**.
4. **Citação e recusa por construção** — cada chunk e cada linha carregam `fonte/url/período`; recusa ("não disponível na base") quando a recuperação volta abaixo do limiar ou o SQL volta vazio. Verificação pós-hoc de que o chunk citado de fato sustenta a afirmação.

> Em uma frase: **o RAG que pediram é o *caminho de texto* de um sistema texto+estruturado roteado**, com o trabalho numérico feito de forma determinística. Isso não foge do enunciado — é a única forma de cumpri-lo (o eixo de heterogeneidade de 10% e a categoria multi-fonte do eval **exigem** o caminho estruturado).

## Justificativa (com evidências verificadas)

> ⚠️ Todas as estatísticas abaixo foram **verificadas de forma adversarial** contra a fonte primária. Ver a tabela completa, vereditos e URLs em [`../pesquisa/evidencias-verificadas.md`](../pesquisa/evidencias-verificadas.md). Onde uma afirmação foi corrigida/refutada, está sinalizado.

**1. Agregação quebra o top-k.** Você não soma o que não recuperou. Em benchmark de agregação (AGGBench, arXiv 2602.01355), o recall do RAG ingênuo é ~**0,008** — erra ~99% das entidades. → Caso A precisa enumerar por entidade e somar em código.

**2. Embeddings são "cegos" a números.** Mudar um valor de US$15k → US$65k dá similaridade de cosseno **0,9998** (RAGShield, arXiv 2604.00387) — a busca vetorial devolve o número/período errado silenciosamente. → Números vão para o store SQL, não para o índice vetorial.

**3. O gargalo é a RECUPERAÇÃO, não a aritmética** *(correção importante)*. Eu havia afirmado que "mesmo com contexto perfeito o LLM só acerta 0,35 dos números, logo nunca deve calcular". **Isso foi refutado.** Com os números certos em contexto, LLMs modernos fazem aritmética financeira **bem** (~72–79% no T2-RAGBench; 100% nas questões numéricas do FinanceBench com Opus 4.6). A justificativa correta para o caminho estruturado é (1) agregação, (2) cegueira numérica dos embeddings, e (3) **auditabilidade**: um número computado em código vem com o SQL + as linhas-fonte, o que satisfaz a regra "cite a fonte". Um módulo Program-of-Thought (LLM emite Python, sandbox executa) reduziu **88%** dos erros aritméticos (FinAgent-RAG, arXiv 2605.05409).

**4. Busca híbrida vence em finanças.** BM25 (0,644) **superou** denso `text-embedding-3-large` (0,587) no Recall@5; híbrido RRF → 0,695; + rerank → **0,816** (arXiv 2604.01733). Tickers, códigos de métrica e rótulos de período são tokens de match exato onde BM25 brilha.

**5. Metadados + contexto são o ganho barato.** Pré-pendurar metadados (empresa, data) a cada chunk levou a acurácia de 50-60% → **72-75%** (Snowflake). Contextual Retrieval (Anthropic) reduziu falhas de recuperação em **35% / 49% / 67%** (embeddings contextuais / + BM25 contextual / + rerank).

**6. Acesso a fonte estruturada domina.** Claude Opus foi de **19,8%** (só web) → **90,8%** com APIs de dados estruturados (FinRetrieval, arXiv 2603.04403). → Para números, ir à fonte estruturada (Bacen, XBRL), não raspar de prosa.

**7. Agêntico/roteado >> ingênuo em multi-hop financeiro.** No estudo FinanceBench da Dewey: RAG vetorial ingênuo **19%** vs. abordagem agêntica **87,3%** (Claude Opus 4.6), com 100% nas questões de raciocínio numérico.

## Alternativas consideradas e rejeitadas

- **RAG ingênuo puro** — falha estrutural em agregação, multi-hop temporal e números (itens 1–3). Rejeitado como sistema, **adotado como o caminho de texto**.
- **Long-context (enfiar tudo no contexto de 1M)** — inviável por capacidade (500+ docs → milhões de tokens) e recall: ~99,7% em "needle" único, mas só ~**60%** em recuperação multi-fato real (relatório Gemini 1.5). Custo por query muito maior. Rejeitado (útil, no máximo, como leitor sobre o top-k já recuperado).
- **Fine-tuning na base** — viola as duas regras inegociáveis: não cita, não recusa de forma confiável; e RAG vence fine-tuning para fatos novos (Ovadia et al., arXiv 2312.05934). Além disso briga com a base que cresce todo dia. Rejeitado.
- **GraphRAG completo** — sumidouro de tempo para 7 dias (indexação cara — estimativa de ~$33k para 1 dataset; LazyGraphRAG a 0,1% do custo), e fraco justamente nas perguntas numéricas/abstrativas que dominam o case. No máximo uma camada **leve** de entity-linking para a agregação do Caso A. Rejeitado como espinha dorsal.

## Consequências

**Ganhos:** cobre os 3 casos sem solvers bespoke; generaliza para as perguntas não-vistas que o case promete testar; cumpre o eixo de heterogeneidade (10%); citação e recusa viram propriedades da arquitetura, não "torcidas" de prompt; eval reprodutível (roteador determinístico).

**Sacrifícios / riscos:** mais peças que RAG ingênuo (ingestão + dois stores + roteador) → mais superfície de código a manter dentro de 7 dias. **Mitigação:** começar pelo eval, escopo apertado em **um** case (provável B), roteador por regras (não agente aberto), e ser honesto na apresentação sobre o que foi deixado como "trabalho futuro".

## Próximos passos

- Decidir o case-fio-condutor (ADR-0002) — recomendação: **B (bancos)**, único que exercita texto + estruturado + temporal com ground truth auditável e API pública reprodutível (Bacen, já validada).
- Montar o **eval harness** primeiro (~10 perguntas, 3 categorias).
- ADR de chunking.
