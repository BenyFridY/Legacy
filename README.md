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

## TL;DR — em 2 minutos ⏱️

**Sistema de retrieval *dual-path* para research de equities.** A sacada que organiza tudo: **separar
texto de número** — texto se **recupera e cita**; número se **computa em SQL** (o LLM **nunca** faz a
conta). Por isso o número é **exato e auditável**, e o sistema **recusa em vez de inventar**.

| retrieval — hit@3 | recusa por escopo | fidelidade (juiz independente) | alucinação |
|:---:|:---:|:---:|:---:|
| **95%** realista · 86,4% completo · MRR **0,667** | **12/12** · over-recusa **0%** | **6/6** sustentadas | **0** |

> **Corpus provado a fundo, não largo (escolha assumida):** 11 documentos reais — 5 fontes, 4 tipos,
> de **312 pp a 4 pp**, multi-período — + Bacen IF.data (10 trimestres). Escalar p/ **500+** é
> *acrescentar linhas ao manifesto*; o gargalo é índice/dedup, **não** o pipeline (ver *Fraquezas e escala*).

### Ver funcionando em 30 segundos

> O case diz, com razão, que **o backend é o que importa** (UI não é avaliada). O chat abaixo é só a
> **janela** mais rápida pra ver as rotas num lugar só:

```powershell
# pré-requisito na 1ª vez (clone fresco): pip install -r requirements.txt ; python scripts\atualizar_base.py
$env:KMP_DUPLICATE_LIB_OK="TRUE"; $env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"
python scripts\ui_demo.py
# -> abra http://localhost:8000
```

<details><summary>no <code>cmd</code> clássico</summary>

```bat
set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8
python scripts\ui_demo.py
```
</details>

![Chat de demo — Legacy · Research de Equities](assets/UI.png)

**Cole estas sete perguntas** — cada uma exercita um caminho diferente (o roteador ignora acento e maiúscula):

| pergunta | caminho | o que prova |
|---|---|---|
| *Quais bancos estão na base?* | **direta** | o sistema conhece a própria cobertura — responde do config, sem retrieval |
| *Qual foi o Resultado Recorrente Gerencial do Itaú no 4T25?* | **texto** | acha e cita **R$ 12,3 bi** (pág. 8) num corpus multi-período |
| *Qual o market share do Nubank em cartão de crédito no 4T25?* | **número genérico** | computado em SQL — **qualquer banco × modalidade**, não só consignado (sem precisar dizer "IF.data") |
| *Qual banco teve o maior market share em consignado no 4T25?* | **ranking** | sem banco nomeado → compara **todos os cobertos** e elege o líder com gap em p.p. |
| *Entre o BB e o Bradesco, quem ganhou mais participação em consignado de 2023 a 2024?* | **comparativo** | cross-bank por **janela escolhida**, gap quantificado (*BB +0,7 p.p. a mais*) |
| *O market share de consignado do Bradesco no balanço bate com o que computamos do Bacen?* | **multi-fonte** | **declarado** (texto) × **computado** (Bacen), lado a lado |
| *Qual será o custo de crédito do Bradesco no 2º trimestre de 2027?* | **recusa** | fora da base (futuro) → diz o **motivo**, não inventa |

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
> [`docs/resultados-eval.md`](docs/resultados-eval.md). Corpus de **texto** = **11 documentos** de
> **5 fontes** (Itaú, Bradesco, BB, Santander, Bacen), **4 tipos** (release, transcrição, sumário,
> nota), **longo × curto** (de 312 pp a 4 pp) e **multi-período** (3T25/4T25/1T26) — **3.650 fichas**,
> alimentadas por um **manifesto** (ver *Como a base é alimentada*); números = **Bacen IF.data,
> 10 trimestres (3T23–4T25)**.

**1) Qualidade de retrieval — hit@k / MRR (BGE-M3 + reranker reais).** Gold por **página**, curado
por busca **lexical + leitura** (independente do embedding → anti-circular). **22 sondagens** em
**5 fontes (4 bancos + Bacen) e 4 tipos** de documento, com **retrieval ciente de período** (quando a pergunta nomeia o
trimestre, um filtro de metadados fixa o documento certo no corpus multi-período):

| conjunto | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| **sondagens realistas** (sem gíria/paráfrase) | — | **95%** | — | — |
| **22 sondagens** (inclui 2 limite + transcrição/nota) | 50,0% | 86,4% | 86,4% | **0,667** |

*(re-medido em 10/06 após o chunking ciente de tabela: hit@3 **subiu** 81,8% → 86,4% — o consignado
do Santander, antes só no hit@5, entrou no top-3; custo honesto: hit@1 cedeu 1 sondagem e o MRR
0,686 → 0,667, porque o cabeçalho re-prefixado adiciona tokens e desloca ranks levemente — a
métrica que alimenta o LLM é o top-3/top-5, que melhorou.)*

**Limites honestos** (não escondidos): a gíria *"calote"* e a paráfrase *"descontado direto da folha"*
falham de propósito; a transcrição de *política de crédito* perde para o release formal (**embora** a de
*inadimplência 90d* acerte no top-3). Com o **filtro de período** (remove a competição 4T25/3T25/1T26),
as sondagens realistas do Itaú seguem no topo — incl. o RRG de 1T26 e 3T25 (mesmo banco, trimestres
quase idênticos).

**2) Recusa por escopo — Estágio 1 (roteador determinístico, sem modelo).** 12 perguntas, 3
categorias de comportamento + 1 distrator anti-over-recusa:

| métrica | valor |
|---|---|
| acurácia de comportamento | **12/12** |
| recusa correta (dos que deviam recusar) | **100%** |
| over-recusa (recusou um respondível) | **0%** |
| alucinação (respondeu o que devia recusar) | **0** |
| **bateria estendida** (36 fraseios extra, escritos após o congelamento das regras) | **36/36** comportamento · **36/36 rota** |

**3) Fidelidade da resposta — faithfulness (juiz LLM INDEPENDENTE, Groq temp 0).** Nas respostas
geradas (texto, **4 bancos**): **6/6 inteiramente sustentadas** pelo contexto citado — e o juiz é um
**modelo de família diferente** do gerador (`openai/gpt-oss-120b` ≠ Llama 3.3 70B → **sem viés de
auto-avaliação**). 2 perguntas foram **corretamente recusadas** (guidance ausente no contexto; share
do Bradesco numa célula de tabela) — defesa em profundidade. Ressalva: `n=6` é sanidade forte.

**3b) Calibração do gate de evidência — Estágio 2.** O limiar deixou de ser placeholder: varrendo um
mini-gold (6 respondíveis × 6 fora-da-base), as respondíveis pontuam **~0,72** e as fora-da-base
**~0,50**, com **joelho em 0,60** (0% over-recusa, 0% vazamento). O antigo **0,30 deixava 100% das
fora-da-base passarem** — agora a *"receita de bolo"* é barrada **pelo gate**, não só pelo LLM.
`LIMIAR_EVIDENCIA_PADRAO` foi ajustado **0,30 → 0,60** com esse lastro.

**4) Resolução do Caso B — ponta a ponta (modelos reais, incl. Groq/Llama 3.3 70B).** As 3
categorias resolvidas ao vivo: *lucro Itaú 4T25* **R$ 12,3 bi** (pág. 8); *consignado Itaú 4T25*
**R$ 75,3 bi** (pág. 21); *market share BB consignado* **19,9% → 19,2%** (série trimestral 3T23→4T25,
IF.data, SQL — e o caminho é **genérico**: *Nubank em cartão* **11,1% → 14,9%**, qualquer banco ×
modalidade, e **compara 2+ bancos por janela escolhida** (cross-bank **ciente de período**, alinhado
pelo trimestre comum e com o gap **quantificado** — ex.: *de 2023→2024 o BB ganhou **+0,7 p.p. a mais**
que o Bradesco; de 2024→2025 ambos caíram e o Bradesco **perdeu menos**, +0,4 p.p. à frente*));
recusas **R1** (futuro 2027) e **R2** (Nubank IFRS × Itaú Cosif).

**5) Caso B3 ao vivo — DECLARADO × COMPUTADO (caminho `multi_fonte`).** O sistema cruza o que o
**Bradesco declara** — agora incluindo a **fala do CEO na teleconferência 3T25** (*"market share de
~14,2%; INSS 15,4%, público 14,3%, privado 7,5%"*, recuperada da **transcrição**) e a tabela do release
4T25 (**14,1%**) — com o que **computamos** do Bacen (**13,8%** no 4T25, SQL) → **confirma**. Quando o
LLM hesita diante de cifras próximas em tabelas cruas, o orquestrador **cai para as evidências citadas
lado a lado** (não inventa, não recusa). Saídas completas em [`docs/resultados-eval.md`](docs/resultados-eval.md).

> **Honestidade estatística:** os `n` são pequenos (escopo `n=12`, fidelidade `n=6`, calibração do
> gate `n=12`) — **sanidade forte, não estatística de população**. O gate **foi calibrado** e o juiz
> de fidelidade **agora é independente** (antes ambos pendentes); o que segue aberto está em
> *Fraquezas* e [ADR-0005](docs/decisions/0005-robustez-escala-calibracao.md).

---

## Arquitetura

```
                          pergunta
                             │
                    ┌────────▼─────────┐
                    │  ROTEADOR (regras)│  Estágio 1: escopo + caminho
                    └────────┬─────────┘
       ┌──────────────┬──────┴─────┬─────────────┬──────────────┐
       ▼              ▼            ▼             ▼              ▼
 não_respondível  doc_unico    computada    comparativo    multi_fonte
  (recusa por    (texto:      (números:    (share de 2+   (cruza
   escopo,        híbrido+     market       bancos, tudo   DECLARADO no
   com motivo)    rerank +     share em     em SQL:        texto  ×
                  gate de      SQL, deter-  janela comum,  COMPUTADO no
                  evidência →  minístico,   gap em p.p.,   IF.data; LLM
                  LLM redige)  auditável)   empate)        reconcilia)
                      │
                 Estágio 2: nota do reranker < limiar → recusa
                      │
                 citação ESTRUTURAL anexada por código (dedup)
```

**Recusa em dois estágios, por responsabilidades separadas:**
- **Estágio 1 — escopo** (roteador): pergunta fora da cobertura → recusa *antes* de buscar. Cinco
  portões: **R1** (período no futuro além de 2026), **R2** (cruza bases contábeis incompatíveis —
  IFRS × Cosif — como **conjunção** de sinais, **nunca** pelo nome do banco), **R3** (pede frase
  *verbatim* que não existe na base), **R7** (pede o *número* de um sub-recorte que o IF.data não
  separa — *consignado INSS*, *cheque especial* — e aponta a modalidade-pai ou o release), **R8**
  (pede *recomendação* de investimento — "vale a pena comprar?" — a base documenta fatos; aconselhar
  compra/venda não é papel do sistema, e a recusa diz o que ele *pode* mostrar).
- **Estágio 2 — evidência** (gate): mesmo no escopo, se a melhor nota do reranker fica **abaixo do
  limiar** (**0,60**, calibrado — ver *Resultados*), recusa em vez de redigir sobre evidência fraca —
  e a recusa **ensina a reformular** (nomeie o trimestre e use o termo do documento: *custo do
  crédito* no Itaú, não *PDD*; o retrieval acha o termo que está **escrito**, não o sinônimo).
- **Camada de UX (sem retrieval):** saudação (*"bom dia"*) e meta-pergunta sobre a cobertura
  (*"quais bancos estão na base?"*) recebem **resposta direta do roteador** — não são perguntas de
  conhecimento (a resposta vive no config, não em PDF). Sem isso, o "bom dia" ecoava a transcrição
  do Bradesco — que tem "bom dia" literal — com cinco fontes.

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
- **Ciente de tabela (10/06):** o overlap assume semântica de **prosa** (contexto = o que veio logo
  antes); numa **tabela**, o contexto é a linha de **cabeçalho das colunas** (`R$ milhões 4T25 3T25
  4T24...`). Quando uma tabela densa estoura o alvo e quebra em 2+ fichas, a continuação ficava com
  números **órfãos de rótulo de coluna**. O fix: ficha com linha de **dados** de tabela mas **sem**
  cabeçalho de colunas ganha, **re-prefixado**, o cabeçalho **mais próximo da mesma página** — mais
  próximo, e não "o anterior", porque o pypdf emite na ordem do *stream* do PDF (o cabeçalho às vezes
  sai **depois** dos dados, ex.: RAEF 3T25 pág. 41). É a regra do Excel de repetir a linha de título
  em cada página impressa. Heurístico e **conservador**: detecção por rótulos de período (`4T25`,
  `Dez24`, `12M25`) + densidade de números; página sem cabeçalho detectável = **no-op**; o cabeçalho
  repetido é texto **verbatim** da mesma página — a citação segue honesta.
- **Dado estruturado NÃO é "chunkado" — é a outra metade do *dual-path*.** Número não se recupera por
  similaridade (ADR-0001): a carteira do Bacen entra como **linhas numa tabela DuckDB** (banco ×
  período × modalidade) e o market share é **calculado em SQL na hora da pergunta** — não vira texto,
  não passa por embedding. Texto é chunkado e citado **por página**; número é computado e citado **pela
  fonte + a query**. Assim documento longo, documento curto e série numérica vão cada um pelo caminho certo.

---

## Como a base é alimentada (ligada / automática)

Critério nº 1 do case. **Sem upload manual** — o sistema busca na fonte e indexa sozinho:

- **Texto (releases/transcrições/notas):** um **manifesto** (`corpus/manifesto.yaml`) lista as fontes
  e `scripts/ingerir_corpus.py` abastece a base **sozinho** — baixa, extrai por página, chunka, embeda
  (BGE-M3) e persiste — **idempotente por (banco, período, tipo_doc)** e com `try/except` por documento
  (uma fonte que cai não derruba o lote). `baixar(url)` traz os **bytes do PDF** com **retry/backoff**
  do CDN/`api.mziq.com` (a página de RI dá **403** a robô; o backend do mziq **não**) ou direto do
  Bacen. `extrair_paginas` (pypdf) devolve uma string **por página** — a âncora da citação.
- **Números (carteira por modalidade + cadastro):** API **Olinda IF.data** do Banco Central. A
  carteira PF por modalidade vem em `Relatório=11`; o **cadastro** mapeia cada instituição →
  **conglomerado prudencial**, e o market share é agregado **por conglomerado** (soma os vários CNPJs
  de um mesmo banco) — divisão `carteira_banco / Σ sistema` feita **em SQL**, idempotente por período.
  **IF.data (trimestral), não SCR.data (mensal), de propósito:** o confronto declarado×computado é
  trimestral por natureza (releases/calls são trimestrais) — granularidade mensal não adicionaria nada
  ao Caso B e triplicaria a ingestão; o SCR é o upgrade natural se o uso pedir série mensal.
- **Lida com a quebra do IF.data em 2025** (Res. 4.966/IFRS9): a carteira por modalidade **migrou de
  `TipoInstituicao=2` (≤2024) para `TipoInstituicao=1` (≥2025)** — e nesse nível o código já é o
  conglomerado prudencial. O cliente **escolhe o nível pelo período**, **pagina** as respostas grandes
  (com dedup das linhas que a API ecoa), e **nunca apaga dados** numa queda da fonte (preserva o
  existente). Resultado: série de consignado **contínua e sem salto** de 3T23 a 4T25.

> A base de **texto** tem **11 documentos** (Itaú 4T25/3T25/1T26, Bradesco 4T25/3T25 + transcrição,
> BB 4T25 + sumário, Santander 4T25, 2 notas do Bacen; **3.650 fichas**) e a de **números**,
> **10 trimestres (3T23–4T25)**. Crescer para 500+ é **acrescentar linhas ao manifesto**; o que falta
> para essa escala (dedup por **hash de conteúdo**, índice **HNSW**, embedding incremental) está em
> *Fraquezas e escala*.

---

## Como rodar — do clone ao tudo rodando

Stack **100% open/free**, sem chave paga no caminho crítico — ver [ADR-0003](docs/decisions/0003-stack-open-free.md). Python ≥ 3.11.
Roteiro em **3 estágios**; cada comando diz **o que esperar** — se a saída bate, o estágio passou.

**Estágio 0 — preparar (~1 min):**

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
:: (a chave do Groq é OPCIONAL e só entra no Estágio 3)

:: no Windows, prefixe os scripts com estas 3 variáveis (carrega torch sem conflito de OpenMP)
set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8
:: em PowerShell:   $env:KMP_DUPLICATE_LIB_OK='TRUE'; $env:PYTHONPATH='.'; $env:PYTHONIOENCODING='utf-8'
:: em macOS/Linux:  export KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=. PYTHONIOENCODING=utf-8
```

**Estágio 1 — prova imediata, 100% offline (~1 min; sem rede, sem modelo, sem chave):**

```bat
:: suíte completa com fakes -> espere "252 passed" em poucos segundos
python -m pytest -q
:: matriz de recusa-por-escopo (roteador puro) -> espere "Acuracia de comportamento  12/12"
::   e, logo abaixo, a bateria ESTENDIDA: "36/36" de comportamento e "Rota correta 36/36"
python -m legacy_rag.eval.runner
```

**Estágio 2 — ligar a base e os modelos reais (internet; ~5–10 min na 1ª vez):**

> ⚠️ a **1ª execução** com modelos reais **baixa ~2,3 GB** (BGE-M3 + reranker do Hugging Face) —
> uma única vez, depois fica em cache. Se parecer "travado" no início, é o download.

```bat
:: UM comando: liga a base (números Bacen + os 11 PDFs do manifesto, idempotente) + valida períodos
:: aceita --de 2024T1 --ate 2025T4 (janela de trimestres) e --dry-run (só PREVÊ: não baixa, não grava)
python scripts\atualizar_base.py
:: ^ chama os dois abaixo; rode-os direto se quiser só um lado
python scripts\ingerir_numeros.py
python scripts\ingerir_corpus.py
:: auditoria da base (10 checagens, read-only) -> espere tudo [OK] (detalhe: resultados-eval.md §6)
python scripts\auditar_base.py
:: hit@k / MRR reais, ciente de período -> espere hit@3 86,4% / MRR 0,667 nas 22 sondagens
python scripts\eval_retrieval_real.py
:: calibração do gate (over-recusa × vazamento -> joelho 0,60) e do fallback do reranker
python scripts\calibrar_gate.py
python scripts\calibrar_discrimina_rerank.py
```

**Estágio 3 — opcional: o redator LLM (chave grátis do Groq no `.env`):** sem chave, **tudo acima
continua funcionando** — roteia, recupera, computa e recusa; só a redação de texto livre degrada
para "trechos citados". Com `LLM_PROVIDER=groq_free` + `GROQ_API_KEY`:

```bat
:: faithfulness com juiz INDEPENDENTE (gpt-oss-120b ≠ gerador)
python scripts\eval_fidelidade_real.py
:: resolve o Caso B ponta a ponta (7 perguntas, todas as rotas) -> compare com resultados-eval.md §4
python scripts\resolver_caso.py
:: o B3 ao vivo: DECLARADO (release + fala do CEO) × COMPUTADO (SQL)
python scripts\resolver_b3.py
:: pergunta LIVRE: mostra a rota + resposta citada ou recusa
python scripts\perguntar.py "..."
:: UI de demo local (http://localhost:8000) — extra p/ apresentação
python scripts\ui_demo.py
```

> ⚠️ **DuckDB é single-writer:** feche o chat (`ui_demo.py`) antes de rodar qualquer outro script —
> dois processos no mesmo `data/legacy.duckdb` dão `IOException` (só `--dry-run` não abre o DB).

Os **252 testes** rodam em segundos e provam o **fluxo e as recusas** com modelos **falsos** (encoder/
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
  router/              roteador determinístico (escopo R1/R2/R3/R7/R8 + caminho)
  generation/          gate de evidência · geração com citação estrutural · LLMClient (Groq)
  pipeline.py          orquestrador: pergunta → resposta citada ou recusa explicada
  runtime.py           fábrica única das dependências reais (modelos + DuckDB + LLM) p/ CLI e UI de demo
  eval/                métricas · eval de retrieval · runner de escopo · calibração do gate · faithfulness
corpus/
  manifesto.yaml       fontes da base de TEXTO (banco/período/tipo/url) — a "base ligada", reproduzível
eval/
  questions.yaml       12 perguntas (3 categorias de comportamento + 1 distrator + 1 B2 de tom)
  retrieval_gold.yaml  22 sondagens (gold por página; 5 fontes, 4 tipos; 2 limite de propósito)
  gate_gold.yaml       mini-gold da calibração do gate (respondíveis × fora-da-base)
docs/
  decisions/           ADRs 0001–0005 — a "progressão de raciocínio" que o case pede
  conceitos/           5 docs didáticos (RAG, embeddings, BM25/híbrida, números/SQL, arquitetura do código)
  pesquisa/            fact-check adversarial das afirmações técnicas
  resultados-eval.md   saídas reproduzíveis do eval (lastro dos números deste README)
scripts/               atualizar_base · ingerir_numeros · ingerir_corpus · ingerir_bradesco · auditar_base · prova_retrieval_real · eval_retrieval_real · calibrar_gate · calibrar_discrimina_rerank · eval_fidelidade_real · resolver_caso · resolver_b3 · perguntar · ui_demo
tests/                 24 arquivos · 252 testes
```

---

## Fraquezas e o que faria diferente em escala

Documentado com honestidade — é o que o case pede. **Vários itens antes "abertos" viraram código
medido** (ver [ADR-0005](docs/decisions/0005-robustez-escala-calibracao.md)); o que sobra está nomeado.

- **Corpus em dezenas, não centenas:** 11 documentos (5 fontes, 4 tipos, longo × curto, multi-período)
  — provam retrieval heterogêneo, eval e o B3, mas ainda longe dos 500+. Crescer é **acrescentar linhas
  ao manifesto** (`corpus/manifesto.yaml`); o gargalo de escala é índice + dedup (abaixo), não o pipeline.
- **Busca exata, sem índice aproximado:** vetorial é **cosseno brute-force** e o BM25 é reconstruído
  em memória por consulta — **exato e instantâneo abaixo de ~100k fichas** (temos 3.650; nesse regime,
  força bruta *vence* o índice aproximado, que pode errar o vizinho mais próximo). Acima disso, a migração
  é **in-place no próprio DuckDB**: a extensão **VSS** liga um índice **HNSW** (lib `usearch`) no **mesmo
  arquivo**, com um `CREATE INDEX` — **sem trocar de sistema nem mover dados** para um vector DB externo.
  Projetado, não construído (sem benchmark medido aqui).
- **Retrieval ciente de período exige o período na pergunta:** com 3 períodos do mesmo banco, uma
  pergunta *period-ambígua* faz a página de um trimestre competir com a do outro. O filtro de metadados
  resolve **quando a pergunta nomeia o trimestre** ("4T25"); sem período, fica à mercê do ranqueamento.
  Fix futuro: inferir o trimestre "mais recente" como default, ou desambiguar com o usuário.
- **Transcrição é irregular (não some):** a sondagem de *política de crédito* na teleconferência do
  Bradesco falha (a busca prefere o release **formal** à fala conversacional), **mas** a de *inadimplência
  90d* (também transcrição) acerta no top-3 — depende do quão "verbatim" é o trecho. Fix: peso por
  `tipo_doc` quando a pergunta o pede ("na teleconferência").
- **Gate calibrado num gold pequeno:** o limiar **0,60** veio de varrer um mini-gold (joelho com 0%
  over-recusa / 0% vazamento), mas `n=12`; produção pede um gold maior e idealmente por-modalidade.
- **Fallback do reranker:** caímos para a ordem do RRF quando o desvio-padrão das notas fica < 0,05.
  O limiar nasceu por inspeção; a medição (`scripts/calibrar_discrimina_rerank.py`) mostra que ele
  pega as duas sondagens difíceis (gíria/paráfrase, pstdev 0,004/0,042) **mas não separa populações**:
  8 das 20 fáceis/médias também disparam. Falha benigna — o fallback só troca a ordenação (nunca
  recusa) e o hit@3 de 86,4% foi medido com ele ativo — porém é **ponto de operação**, não joelho
  calibrado como o 0,60 do gate (detalhe em `docs/resultados-eval.md` §3c).
- **Interação fallback × gate (over-recusa em gíria/paráfrase):** quando o cross-encoder achata as notas
  (~0,50), o fallback recupera a **ordem** do RRF, mas as **notas** continuam achatadas; como o gate de
  evidência exige ≥ 0,60, uma pergunta **respondível porém difícil** (gíria/paráfrase) pode ser recusada
  mesmo com o trecho certo no topo. É a mesma família dos limites de gíria já declarados; o fix honesto é
  ampliar o `gate_gold.yaml` com casos "difícil-mas-respondível" e **recalibrar** (não feito: mexer no
  0,60 às vésperas arrisca vazamento). Achado da auditoria adversarial (ADR-0005).
- **Modalidade é por palavra-chave (determinística), com 3 guardas de honestidade:** *(A)* sinônimos
  coloquiais (*"carro"*→veículos, *"casa própria"*→habitação); *(B)* se a pergunta **não nomeia** o
  produto, a resposta **avisa** que assumiu consignado (sem default **silencioso**); *(C)* **R7** recusa o
  *número* de um sub-recorte fora dos 7 baldes do IF.data (*consignado INSS*, *cheque especial*, *SFH*) —
  aponta a modalidade-pai (SQL) ou o release (texto). **Limite residual:** um sinônimo fora da lista ainda
  cai no default — mas agora **avisado**, não silencioso (ver ADR-0005, item 14).
- **Carteira (R$) × share (%):** o caminho de números computa **os dois, cada um na sua unidade** —
  ranking, série e cruzamento de *carteira* respondem em **R$** (saldo IF.data; a auditoria de dados
  de 10/06 validou a unidade: Itaú consignado 4T25 = **R$ 75,3 bi** na base **e** no release), e share
  segue em % e p.p. O **nível** pontual ("qual o saldo no 4T25?") fica no **texto** por desenho:
  o release é a autoridade do próprio número gerencial, citado da página. **Limite residual:** o
  ranking compara só os **5 bancos cobertos** — e a auditoria mostrou a **Caixa em 2º no consignado
  do sistema** (14,7%, fora da base); por isso a resposta de ranking carrega o rótulo *"entre os 5
  bancos cobertos"* (sem ele, o "acima de" do vice lia-se como vice do sistema inteiro).
- **RAG sobre tabelas *(corrigida em 10/06)*:** o número *declarado* do B3 (consignado **14,1%**)
  vive numa **célula de tabela**; quando uma tabela densa estourava o tamanho-alvo e quebrava em 2+
  fichas, as continuações ficavam **sem a linha de cabeçalho de colunas** (o overlap só carrega a
  última linha de dado) e o LLM (corretamente) não lia os números órfãos — a auditoria confirmou.
  O fix nomeado aqui foi **implementado**: *chunking ciente de tabela* (ver *Decisões de chunking*) —
  a continuação re-prefixada com o cabeçalho mais próximo da página; o corpus foi re-ingerido e a
  ficha do 14,1% (RAEF 3T25 pág. 41) agora carrega os rótulos `Set25/Jun25/Set24`. **Limite
  residual:** a detecção é heurística — cabeçalho que a extração funde com dados ou página só de
  gráfico fica de fora (no-op conservador: nada é prefixado, nunca inventado). E o princípio segue:
  share *computado* vai pelo **caminho SQL**, não pela leitura de tabela em texto.
- **Lacunas do roteador (R4/R6):** distinguir *realizado* de *guidance* dentro de 2026 (R4) e métricas
  ainda não ingeridas (R6) caem hoje no Estágio 2 (gate), não numa regra dedicada.
- **Fronteira de futuro declarada à mão:** `ANO_COBERTURA_MAX=2026` é uma constante do config que
  espelha o que foi ingerido (realizado até 4T25, guidance falando de 2026) — ingerir guidance de
  2027 exige atualizá-la junto. A falha de esquecer é **conservadora** (over-recusa visível, nunca
  invenção); o fix de produção é derivar a fronteira da própria base na ingestão.
- **Dedup só por (banco, período, tipo_doc):** falta dedup por **hash de conteúdo** para reingestão em
  escala (mesmo arquivo, URL diferente) — projetado, não construído.
- **Janela mista ano+trimestre colapsa para o trimestre:** em *"de 2023 até o 4T25"* a precedência
  "trimestre manda" descarta o 2023 — a resposta rotula a janela usada (mitiga), mas responde uma
  pergunta mais estreita. Fix: combinar ano solto + trimestre na janela (3ª auditoria).
- **Comparação textual cross-bank cai no texto sem pré-filtro:** *"compare o custo de crédito do BB
  com o do Bradesco"* não é o comparativo SQL (que é só share computado) — vai pro doc_unico com
  retrieval misto dos 2 bancos, sem garantia de cobertura dos dois lados. Decisão de desenho
  (número comparável = SQL); o fix futuro é um ramo multi-doc por banco.
- **Citação = contexto integral entregue ao LLM:** no doc_unico, as fontes listam todo o top-5 que o
  LLM viu — o gate exige que a *melhor* nota passe 0,60, não todas (1-2 páginas marginais, 0,54-0,59,
  podem aparecer). É transparência do grounding (o multi_fonte, com k=10, filtra por nota antes).
- **Ingestão não-atômica:** `DELETE`+`executemany` sem transação — um crash no meio do INSERT deixa o
  período parcial, e a reexecução o pula ("já presente"); o denominador do share sairia silenciosamente
  menor. Não afeta a base atual (validada íntegra); fix: `BEGIN/COMMIT` na carga (3ª auditoria).
- **Guardas de borda do SQL:** denominador zero viraria share `NaN` (implausível no IF.data real —
  sistema na casa de centenas de bilhões); a paginação do Olinda para cedo se uma página *inteira* for
  duplicada (anti-loop deliberado; respostas atuais têm ~2 páginas). Registrados, sem guarda dedicada.
- **Faithfulness em n pequeno:** já com **juiz independente** (gpt-oss-120b ≠ gerador) e `n=6` em 4
  bancos (6/6); ainda assim é amostra pequena — produção pede `n` maior e mais bancos/períodos.

---

## Decisões (ADRs) — a progressão de raciocínio

| ADR | Decisão |
|---|---|
| [0001](docs/decisions/0001-arquitetura-dual-path.md) | Arquitetura **dual-path roteada** (não RAG ingênuo) |
| [0002](docs/decisions/0002-fio-condutor-caso-b-consignado.md) | Fio condutor **Caso B · consignado · BB+Bradesco+Itaú** (Nubank = não-respondível orgânico) |
| [0003](docs/decisions/0003-stack-open-free.md) | Stack **100% open/free**; LLM atrás de interface trocável |
| [0004](docs/decisions/0004-ingestao-larga-prova-focada.md) | **Ingestão larga, prova focada** |
| [0005](docs/decisions/0005-robustez-escala-calibracao.md) | **Robustez, escala e calibração**: manifesto + fallback do reranker + calibração do gate + juiz independente |

---

## Nota sobre uso de IA

Construído com apoio de IA (Claude), conforme **permitido e encorajado** pelo case. Toda decisão está
documentada em `docs/decisions/` e é defensável — incluindo um passo de **verificação adversarial**
das afirmações técnicas (`docs/pesquisa/`) e uma **auditoria automatizada do próprio código** antes de
escrever este README, para que nenhuma afirmação aqui ultrapasse o que o código realmente faz.
