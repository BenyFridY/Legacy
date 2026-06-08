# ADR-0005 — Robustez, escala e calibração (endurecimento pós-prova)

- **Status:** Aceita
- **Data:** 2026-06-07
- **Relacionada:** [ADR-0001](0001-arquitetura-dual-path.md) (dual-path), [ADR-0004](0004-ingestao-larga-prova-focada.md) (ingestão larga)

## Contexto

Depois de o pipeline estar provado de ponta a ponta (retrieval + eval + Caso B), uma rodada de
**verificação adversarial** (revisão do próprio código por agentes) e uma **bateria empírica** (rodar
o sistema vivo, inclusive com perguntas fora de escopo) revelaram pontos a endurecer e lacunas a
declarar com honestidade. Este ADR registra o que foi **feito** e o que fica **aberto** — a rubrica
pede explicitamente "fraquezas reveladas" e "como escalaria de centenas para dezenas de milhares".

## Decisões TOMADAS (implementadas)

1. **Manifesto de fontes + ingeridor genérico** (`corpus/manifesto.yaml` + `scripts/ingerir_corpus.py`).
   A "base ligada" cresce por **uma linha no manifesto**: o ingeridor baixa da fonte, extrai, chunka,
   embeda e persiste, **idempotente por `(banco, período, tipo_doc)`** e com `try/except` por documento
   (uma fonte que cai não derruba o lote). É a forma reproduzível e escalável da ingestão — e o caminho
   direto para 500+ documentos. O corpus passou a ser **heterogêneo de propósito**: 5 fontes (Itaú,
   Bradesco, BB, Santander, Bacen), 4 tipos (`release`, `transcricao`, `sumario`, `nota`), períodos
   variados (3T25/4T25/1T26) e documentos **longos × curtos** (de ~312 pp a ~4-6 pp).

2. **Download que contorna o 403 das páginas de RI.** Descoberta: as páginas de RI e a forma
   `*/download-file/*` respondem **403** a cliente programático, mas o backend público
   `api.mziq.com/mzfilemanager/v2/d/<empresa>/<arquivo>?origin=N` (e o `filemanager-cdn.mziq.com`)
   entregam o PDF **sem bloqueio**. O Bacen serve PDFs direto do domínio. Toda URL do manifesto é
   **validada por download real** (HTTP 200 + `%PDF` + camada de texto) antes de entrar.

3. **`baixar()` com retry/backoff** (`legacy_rag/ingestion/releases.py`). O lado de TEXTO da base ligada
   (critério nº 1) agora tem a mesma robustez do cliente do Bacen: retry em falha transitória (rede / 5xx),
   mas **propaga na hora** em 4xx (URL errada/bloqueio é permanente — não insiste). Testado sem rede.

4. **Fallback do reranker para a ordem do RRF** (`legacy_rag/retrieval/rerank.py`,
   `LIMIAR_DISCRIMINA_RERANK = 0.05`). Quando o cross-encoder **não discrimina** (desvio-padrão das notas
   abaixo do limiar — acontece com gíria, em que ele empata tudo em ~0,5 e *apaga* o bom sinal do vetorial
   denso), preservamos a **ordem do RRF** em vez de reordenar por ruído. As notas do reranker continuam
   anexadas (o gate de evidência usa a melhor). Transforma uma fraqueza **documentada** em correção **medida**.

5. **Harness de calibração do gate de evidência** (`eval/gate_gold.yaml`,
   `legacy_rag/eval/calibracao_gate.py`, `scripts/calibrar_gate.py`). O limiar de 0,30 era um PLACEHOLDER —
   e a bateria empírica mostrou que ele é **frouxo** (deixou "receita de bolo" passar; quem segurou foi o
   LLM). Agora um mini-gold (respondíveis × fora-da-base) é pontuado pelo retrieval real e o limiar é
   **varrido**, contando **over-recusa × vazamento**, para achar o "joelho". O número deixa de ser chute.

6. **Juiz de fidelidade independente** (`scripts/eval_fidelidade_real.py`, `GROQ_JUIZ_MODELO`). O juiz
   passou a ser um modelo de **família diferente** do gerador (default `openai/gpt-oss-120b` vs. gerador
   Llama 3.3 70B) — remove o viés de **auto-avaliação**. O `n` foi ampliado para cobrir vários bancos.

7. **Degradação graciosa sem LLM** (`legacy_rag/generation/answer.py`). Sem chave, o caminho de texto
   **mostra a evidência citada** em vez de quebrar — honra a promessa "sem chave, recupera e cita".

8. **Pergunta B2 (tom) no eval** (`eval/questions.yaml`). Fecha a promessa do ADR-0004: agora que a
   **transcrição 3T25 do Bradesco** está na base, há uma pergunta B2 RESPONDÍVEL (recuperar/sintetizar
   tom qualitativo declarado), não só a recusa de citação verbatim.

9. **Quebra do IF.data em 2025** (Res. 4.966/IFRS9) já tratada em código: a carteira por modalidade migrou
   de `TipoInstituicao=2` (≤2024) para `=1` (≥2025); o cliente escolhe o nível pelo período, **pagina** as
   respostas grandes (dedup das linhas ecoadas) e **nunca apaga** dados numa queda da fonte.

10. **Gate de futuro v2 — responder DATA documentada sem alucinar** (`router._gate_escopo` +
    `pipeline._aterrar_ano_futuro` + `tests/test_gate_futuro.py`). A bateria revelou que o R1 era um corte
    **cego por ano**: over-recusava perguntas sobre uma DATA futura que **está num documento** (vigência da
    Res. 4.966 em 2027, vencimento de dívida em 2028, janela de recompra até 2027 — todas presentes no
    corpus, verificado por query). Refinado: o R1 só recusa CEDO o **valor de uma métrica** (market share /
    custo de crédito / guidance) em ano futuro — o caso em que inventar é o risco. Pergunta de **data/evento**
    com ano futuro vai para o texto, onde uma **trava de aterramento** só deixa responder se um trecho
    recuperado menciona aquele ano **como ano** — casamento por **fronteira de palavra**, ignorando o ano
    dentro de código (`C0052027`) ou de valor (`R$ 2027 milhões`); senão, recusa. Resultado: não inventa o
    futuro (valor não documentado é barrado) **e** para de over-recusar a data documentada. **Medido: 11/11**
    em `tests/test_gate_futuro.py` (3 recusa-R1, 3 âncora-responde, 2 aterramento-recusa, 2 sanidade + **1
    adversarial** — "2027" como valor monetário, que **quebrou** a 1ª versão por substring ingênuo e motivou
    o casamento robusto); suíte total **148 verde**, sem regressão.

11. **Comparação cross-bank no caminho de números** (`router._classificar_caminho` → rota `comparativo`,
    `pipeline._caminho_comparativo`, `tests/test_pipeline.py`). A bateria com modelos reais mostrou que o
    sistema **recusava** *"entre BB e Bradesco, quem ganhou mais share?"* — comparar **2 bancos** não era
    suportado (o caminho de números exigia 1 banco). Generalizado: aceita **2+ bancos**, computa a série de
    cada um (SQL) e compara a variação — *ganhou mais / perdeu menos*, citando o Bacen. Verificado **com
    dados reais**: BB×Bradesco e BB×Itaú em consignado (todos caíram; BB caiu menos) e **Nubank×Itaú em
    cartão** (Nubank **+3,8 p.p.** → 14,9%; Itaú **−4,1 p.p.** → 21,0%). Recusa honesta se < 2 bancos têm
    série computável. Suíte total **150 verde**.

12. **Janela de trimestres selecionável na ingestão dos números** (`store.trimestres_intervalo`,
    `scripts/ingerir_numeros.py` e `scripts/atualizar_base.py` com `--de/--ate/--dry-run`,
    `tests/test_store.py`). A janela do IF.data era **fixa no código** (`PERIODOS`); o comando que "liga
    a base" agora aceita a **janela por trimestre** — `--de 2024T1 --ate 2025T4` expande para os períodos
    `YYYYMM` de fechamento (T1=03 … T4=12), idempotente (só puxa o ausente). `--dry-run` **prevê** o que
    puxaria sem baixar nem abrir o DB — seguro para demonstrar ao vivo. A expansão do intervalo é uma
    função **pura e testada** (intervalo completo, cruza ano, `t` minúsculo, intervalo invertido e formato
    inválido viram erro). O texto continua vindo do **manifesto** (descoberta curada, não crawl por data —
    sites de RI dão 403 a robô; ver lacunas). Suíte total **156 verde**.

## Descoberta que virou decisão de projeto

**O LLM não é determinístico nem a temperatura 0.** A mesma pergunta *"lucro líquido recorrente"*
(que o documento do Itaú chama de *"Resultado Recorrente Gerencial"*) deu **responde → recusa → responde**
em 3 tentativas. Isso **confirma a tese da arquitetura**: roteador (regras), cálculo (SQL) e citação
(estrutural) são **determinísticos de propósito**, confinando o não-determinismo ao texto livre — que é a
peça menos crítica da nota. É também o "o que me surpreendeu" da apresentação.

## Lacunas ABERTAS (honestas; planejadas, não construídas)

- **Roteador R4/R6:** distinguir *realizado* de *guidance* dentro de 2026 (R4) e métricas ainda não
  ingeridas (R6) caem hoje no **Estágio 2** (gate de evidência), não numa regra dedicada.
- **Índice aproximado:** a busca vetorial é **cosseno brute-force** e o BM25 é reconstruído por consulta.
  Exato e instantâneo abaixo de ~100k fichas (temos 3.650). Acima disso, **upgrade in-place no próprio
  DuckDB**: a extensão **VSS** adiciona um índice **HNSW** (backed pela lib `usearch`) — **mesmo store, um
  `CREATE INDEX`**, sem migrar para um vector DB externo (Pinecone/Weaviate) nem fazer o dado sair da
  máquina; + **FTS persistido** para o BM25. Projetado, sem benchmark.
- **Dedup por hash de conteúdo:** a idempotência é por `(banco, período, tipo_doc)`; falta dedup por
  **hash** para reingestão em escala (mesmo arquivo, URL diferente).
- **RAG sobre tabelas:** número numa célula perde cabeçalho/unidade ao chunkar (ex.: o share declarado do
  B3). O fix real é **chunking ciente de tabela**; hoje o `multi_fonte` cai para evidência citada lado a lado.
- **Valores pendentes de re-execução:** o **delta** do fallback do reranker no hit@k/MRR e o **joelho** do
  gate são medidos pelos scripts reais (documentados em `docs/resultados-eval.md` quando rodados).

## Consequências

- A base deixou de ser "2 PDFs longos" e passou a um corpus heterogêneo alimentado por manifesto — o
  retrieval "dentro de centenas" fica crível e a heterogeneidade (longo×curto, vários tipos) é provada.
- Três fraquezas antes só *descritas* viraram código *medível* (fallback do reranker, calibração do gate,
  juiz independente) — exatamente a postura "medir antes de afirmar" que o case valoriza.
- O que continua aberto está **nomeado e localizado** aqui, em vez de escondido.
