# Apresentação — Case Estágio AI · Sistema de Retrieval para Research de Equities

> **Como usar este arquivo:** cada bloco separado por `---` é um slide. Sob cada slide:
> - 🎤 **Fale:** o que dizer em voz alta (roteiro curto — não leia, fale com suas palavras)
> - 💡 **Lógica:** por que este slide existe (pra você entender e defender)
> - 🛡️ **Se perguntarem:** pergunta provável da banca + resposta pronta
>
> No fim a gente renderiza isto num PDF/HTML pra projetar (Marp). A **demo ao vivo do chat** é o centro.

---

## 🗺️ Mapa dos slides (o arco da história)

| # | Slide | Papel na história |
|---|---|---|
| 1 | **Capa** | Planta a frase que a banca tem que lembrar |
| 2 | **O problema** | Por que research de equities é difícil pra um RAG |
| 3 | **A sacada central** | Separar TEXTO de NÚMERO — o coração de tudo |
| 4 | **A arquitetura** | O diagrama dual-path roteado |
| 5 | **Responder ou recusar** | Recusa em 2 estágios — honestidade como feature |
| 6 | **Caso B — ao vivo** | As 4 rotas + DEMO do chat (o ponto alto) |
| 7 | **Resultados do eval** | "Comece pelo eval" — os números medidos |
| 8 | **O que me surpreendeu** | Aprendizados não-óbvios sobre RAG |
| 9 | **Prós e contras** | Trade-offs honestos da minha escolha |
| 10 | **Como escala** | 500+ docs/dia: o que muda e o que não |
| 11 | **Fecho** | O que eu faria com mais tempo + impacto |

> **Frase-âncora:** *"Separei texto de número — por isso o número está certo e o sistema recusa em vez de inventar."*
> Duração-alvo: ~12 min de fala + ~3 min de demo. 1 ideia por slide.

---

# 1 · Capa

# Sistema de Retrieval para Research de Equities
### RAG *dual-path* roteado — **texto que cita, número que computa**

Beny Frid · Legacy Capital · junho/2026

> 🎤 **Fale:** "Construí um sistema de retrieval pra apoiar o research de equities. A ideia central — que vou defender hoje — é simples: **separar o que é texto do que é número.** É exatamente aí que o RAG ingênuo quebra, e foi a primeira decisão de arquitetura que tomei."
>
> 💡 **Lógica:** a capa já entrega a tese. Quem ouve a primeira frase já sabe do que se trata. Não comece por "fiz um RAG" — comece pela *decisão* que te diferencia.
>
> 🛡️ **Se perguntarem "o que é dual-path?":** "Dois caminhos separados — um pra texto, um pra número — que só se encontram na resposta final. Vou mostrar no diagrama."

---

# 2 · O problema (por que é difícil)

**O research lê uma montanha** de releases, transcrições de call e balanços. Precisa de resposta:
- **rápida**,
- **com a fonte** (citável, auditável),
- **com o número certo**.

**O "RAG ingênuo"** (joga tudo num vetor, pede pro LLM responder) falha em dois pontos:
1. **Número:** o LLM *lembra* o número aproximado — e erra. "1,2%" e "12%" moram em textos quase idênticos.
2. **Honestidade:** quando não sabe, ele **inventa** (alucina) em vez de dizer "não tenho".

> 🎤 **Fale:** "Num contexto de research, errar um número ou inventar uma fonte não é um bugzinho — é perder a confiança do analista. O RAG ingênuo, aquele de jogar tudo num índice vetorial e pedir pro modelo responder, falha justamente nessas duas coisas: número e honestidade."
>
> 💡 **Lógica:** a banca precisa **sentir a dor** antes de você mostrar a cura. Sem problema claro, a solução parece complicação gratuita.
>
> 🛡️ **Se perguntarem "por que não só um índice grande + GPT?":** "Porque número não se recupera por similaridade — 1,2% e 12% têm vizinhança semântica quase igual, o vetor não distingue. E sem um portão de evidência, o modelo preenche a lacuna inventando. Os dois problemas têm a mesma raiz: tratar número como se fosse texto."

---

# 3 · A sacada central

## Texto e número são problemas DIFERENTES. Trate cada um do seu jeito.

| | **TEXTO** ("o que o CEO disse") | **NÚMERO** ("qual o market share") |
|---|---|---|
| Como obter | **recuperar** o trecho e **citar** | **computar** com SQL (Bacen IF.data) |
| Quem faz | busca híbrida + rerank | DuckDB (conta determinística) |
| Papel do LLM | **escreve** a resposta com o trecho | **nenhum cálculo** — só redige o resultado |

**O LLM nunca faz a conta.** O SQL faz a conta; o LLM só veste o número em linguagem — e sempre cita a fonte.

> 🎤 **Fale:** "Essa é a sacada que organiza o projeto todo. Pergunta de texto eu **recupero e cito**. Pergunta de número eu **computo com SQL** sobre dados oficiais do Banco Central. O modelo de linguagem **nunca** faz a conta — ele só escreve a frase final com o número que o SQL já calculou. Assim o número é sempre exato e rastreável."
>
> 💡 **Lógica:** este é o slide do *coração*. Se a banca só lembrar de um slide, que seja este. A tabela deixa a separação visual e óbvia.
>
> 🛡️ **Se perguntarem "mas LLM não faz conta?":** "Faz, e bem, *quando recebe o contexto certo* — testei isso. Mas eu não quero *depender* disso pra um número de mercado: prefiro o SQL, que é determinístico e auditável. O LLM erra é quando precisa **lembrar** o número; aqui ele nunca precisa lembrar."
> 🛡️ **Se perguntarem "e quando a pergunta é as duas coisas?":** "Existe — é o coração do Caso B. Comparo o que a empresa **declarou** no texto com o que eu **computei** do Bacen. Mostro daqui a pouco."

---

# 4 · A arquitetura — *dual-path* roteado

```
                          pergunta
                             │
                  ┌──────────▼──────────┐
                  │  ROTEADOR (regras)  │   número ou texto? (determinístico)
                  └──────────┬──────────┘
            ┌────────────────┴────────────────┐
          TEXTO                             NÚMERO
            │                                  │
   embedding + BM25                    DuckDB (SQL):
    → RRF → reranker                   carteira_banco ÷ Σ sistema
            │                          = market share (EXATO)
   GATE 0,60: evidência forte?                 │
        │ não → RECUSA (com motivo)            │
        │ sim                                  │
        └────────► LLM REDIGE com CITAÇÃO ◄────┘
                   (nunca faz a conta; ou RECUSA, sem inventar)
```

**Zoom no caminho de texto — um funil de "barato/impreciso" → "caro/preciso":**

```
3.845 fichas → embedding (top 50) + BM25 (top 50) → RRF (funde por posição)
            → reranker relê os ~10 finalistas juntos → top 5 → GATE 0,60
```

> 🎤 **Fale:** "Toda pergunta passa por um **roteador determinístico** que decide: é número ou texto? **Número** vai pro SQL — carteira do banco dividida pelo sistema, conta exata e auditável. **Texto** entra num funil: duas buscas baratas pegam 50 candidatos cada (embedding por significado, BM25 por palavra exata), o RRF funde por posição, e o reranker entrevista os 10 finalistas a fundo. No fim, um **portão de evidência (0,60)** decide: se nada é bom o bastante, **recusa**; senão o LLM redige **com citação** — mas o LLM **nunca faz a conta**."
>
> 💡 **Lógica:** este slide é a **prova visual** da tese do slide 3 ("separar texto de número"). Cada caixa existe por um motivo que você sabe defender.
>
> 🛡️ **Se perguntarem "por que roteador de regras e não um agente LLM?":** "Porque o eval pesa 50% e roda o sistema repetidamente — **mesma pergunta → mesmo caminho** mantém a avaliação **reproduzível e auditável**. Um agente LLM seria mais flexível, mas traria não-determinismo e 3-5 chamadas por pergunta. Troquei flexibilidade por confiabilidade — a escolha certa pra um número de mercado."

---

# 5 · Responder ou recusar (honestidade como feature)

> _(a preencher — recusa em 2 estágios: escopo R1/R2/R3 + gate de evidência)_

---

# 6 · Caso B — ao vivo (as 4 rotas)

> _(a preencher — documento único · computada genérica · multi-fonte B3 · recusa; DEMO do chat)_

---

# 7 · Resultados do eval ("comece pelo eval")

> _(a preencher — hit@3, MRR, realista, recusa 12/12, faithfulness + honestidades)_

---

# 8 · O que me surpreendeu

> _(a preencher — LLM não-determinístico a temp 0; fraqueza do Nubank virou força; LLM faz conta bem com contexto)_

---

# 9 · Prós e contras — o que ganhei × o que sacrifiquei

| Escolha | Ganhei | Sacrifiquei |
|---|---|---|
| **Dual-path determinístico** (não agente LLM) | número exato e auditável; eval reproduzível; mesma pergunta → mesmo caminho | flexibilidade — regras léxicas quebram em gíria/fraseado não-previsto |
| **Stack aberto/local** (sem Cohere/Pinecone) | **US$ 0**, privado (dado não sai da máquina), reproduzível offline | talvez um delta de qualidade vs. APIs pagas — **não comprovado em PT** |
| **Vetor força-bruta** (não HNSW) | busca **exata** e instantânea na escala atual; zero peça móvel | é O(N): precisaria de índice HNSW acima de ~100k fichas |
| **LLM só redige** (SQL faz a conta) | nunca alucina número; resposta sempre citada | menos "esperto" que um agente que raciocina sozinho |

**Onde o sistema quebra (assumido, não escondido):**
- gíria extrema (*"calote"*) e paráfrase sem palavra em comum → *fix:* expansão de query;
- **transcrição** perde pro **release** formal no mesmo tema (achado real de corpus heterogêneo);
- número numa **célula de tabela** perde contexto ao chunkar → é *por isso* que número vai pelo SQL.

> 🎤 **Fale:** "Cada escolha minha trocou **flexibilidade/potência crua** por **reprodutibilidade e correção** — que é o trade-off certo em finanças, onde **errar um número ou inventar uma fonte custa a confiança do analista**. E sou honesto sobre onde quebra: gíria extrema, transcrição vs. release, número em tabela."
>
> 🛡️ **Se perguntarem "não é conservador demais?":** "Para uma fundação de research, sim, de propósito. A flexibilidade entra depois — a interface é trocável; dá pra ligar um reranker melhor ou um agente quando houver eval que justifique. Mas a base tem que ser confiável primeiro."

---

# 10 · Como escala — de dezenas → centenas → dezenas de milhares

**O que NÃO muda (já pronto):** o pipeline. Crescer o corpus = **acrescentar linhas ao manifesto**; a ingestão é idempotente e isola falha por documento (uma fonte que cai não derruba o lote).

**O que muda (projetado, não construído — honesto):**

| Gargalo | Hoje | Em escala |
|---|---|---|
| **Índice vetorial** | cosseno força-bruta (exato, instantâneo < 100k) | **HNSW in-place no DuckDB** (extensão VSS, `CREATE INDEX`) — *sem trocar de sistema* |
| **BM25** | reconstruído em memória por consulta | **FTS persistido** |
| **Dedup** | por (banco, período, tipo) | **+ hash de conteúdo** (mesmo arquivo, URL diferente) |
| **Embedding** | reprocessa o lote | **incremental** (só fichas com hash novo) |

**O que não escala sozinho (honesto):** a curadoria do *gold* do eval e cada fonte nova (= um conector). 

> 🎤 **Fale:** "Crescer o corpus é **acrescentar linha ao manifesto** — o pipeline não muda. O que muda são os índices: hoje uso força-bruta porque é exata e instantânea nas 3.845 fichas; passando de ~100 mil, **não migro de banco** — ligo um índice **HNSW no próprio DuckDB** com a extensão VSS, um `CREATE INDEX`. Dedup vira por hash de conteúdo e o embedding vira incremental. Tudo projetado; não medi benchmark — não quis afirmar o que não testei."
>
> 🛡️ **Se perguntarem "e os 500+ do enunciado?":** "O case pede 500+ e crescendo. Provei a fundo com 11 documentos heterogêneos porque o critério nº 1 é **qualidade de retrieval**, não volume; o caminho de volume está desenhado e cabe no mesmo store. Preferi um problema **provado** a um número **alegado**."

---

# 11 · Fecho

> _(a preencher — o que eu faria com mais tempo + 1 linha de impacto)_
