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
3.650 fichas → embedding (top 50) + BM25 (top 50) → RRF (funde por posição)
            → reranker relê os ~10 finalistas juntos → top 5 → GATE 0,60
```

> 🎤 **Fale:** "Toda pergunta passa por um **roteador determinístico** que decide: é número ou texto? **Número** vai pro SQL — carteira do banco dividida pelo sistema, conta exata e auditável. **Texto** entra num funil: duas buscas baratas pegam 50 candidatos cada (embedding por significado, BM25 por palavra exata), o RRF funde por posição, e o reranker entrevista os 10 finalistas a fundo. No fim, um **portão de evidência (0,60)** decide: se nada é bom o bastante, **recusa**; senão o LLM redige **com citação** — mas o LLM **nunca faz a conta**."
>
> 💡 **Lógica:** este slide é a **prova visual** da tese do slide 3 ("separar texto de número"). Cada caixa existe por um motivo que você sabe defender.
>
> 🛡️ **Se perguntarem "por que roteador de regras e não um agente LLM?":** "Porque o eval pesa 50% e roda o sistema repetidamente — **mesma pergunta → mesmo caminho** mantém a avaliação **reproduzível e auditável**. Um agente LLM seria mais flexível, mas traria não-determinismo e 3-5 chamadas por pergunta. Troquei flexibilidade por confiabilidade — a escolha certa pra um número de mercado."

---

# 5 · Responder ou recusar (honestidade como feature)

**Recusar bem é tão importante quanto responder.** Duas camadas, responsabilidades separadas:

**Estágio 1 — ESCOPO** (o roteador, *antes* de buscar — barato): a pergunta cabe na base?
- **R1 · futuro** — pede o *valor* de uma métrica num ano além da cobertura (> 2026). *Mas* uma **data
  documentada** (ex.: vigência de norma em 2027) **passa**: uma trava de aterramento só responde se um
  trecho recuperado citar aquele ano.
- **R2 · bases incompatíveis** — cruza **IFRS × Cosif** (ex.: Nubank × Itaú) numa métrica de release.
  É **conjunção de sinais** — nunca o nome do banco — e exige os **dois lados** reais presentes.
- **R3 · verbatim ausente** — pede a *frase literal* de quem não tem transcrição oficial na base.
- **R7 · sub-produto fora do Bacen** — pede o *número* de um recorte que o IF.data não separa
  (*consignado INSS*, *cheque especial*, *SFH*). Recusa apontando a modalidade-pai (SQL) ou o release.
- **R8 · recomendação de investimento** — *"vale a pena comprar?"* → recusa: a base documenta **fatos**
  (cotação histórica, consenso de analistas no release, tudo citável); aconselhar compra/venda, não.

**Estágio 2 — EVIDÊNCIA** (o gate, *depois* de buscar): mesmo no escopo, se a melhor nota do reranker
fica **< 0,60** (calibrado), recusa em vez de redigir sobre evidência fraca.

**Toda recusa diz o MOTIVO** (R1/R2/R3/R7/R8 ou "evidência fraca") — auditável, nunca um "não sei" seco.
Medido: **over-recusa 0%**.

> 🎤 **Fale:** "Num sistema de research, recusar não é falha — é feature. Recuso em duas camadas. Primeiro **escopo**: antes de gastar busca, o roteador vê se a pergunta cabe na base — futuro, bases contábeis incompatíveis, ou citação literal que não existe. Depois **evidência**: mesmo dentro do escopo, se o melhor trecho não passa de uma nota mínima calibrada, recuso. E toda recusa vem com o **motivo**."
>
> 💡 **Lógica:** a banca vai testar isso ("e se eu perguntar algo que não está na base?"). O slide mostra que a honestidade é **projetada em camadas**, não acidente — e o "0% over-recusa" prova que recusar não virou paranoia.
>
> 🛡️ **Se perguntarem "e se recusar demais?":** "Medi: **0% de over-recusa** nas 12 perguntas de comportamento. E refinei o caso mais sutil — uma pergunta sobre uma **data futura documentada** (vigência de norma em 2027) é **respondida**, porque uma trava confere se um trecho realmente cita o ano. Recuso o valor que eu inventaria, não a data que está escrita."
> 🛡️ **Se perguntarem "de onde vem o 0,60?":** "Calibrei: variei o limiar contra um mini-gold de respondíveis × fora-da-base e achei o 'joelho' — respondíveis pontuam ~0,72, fora-da-base ~0,50, e 0,60 separa com 0% vazamento e 0% over-recusa. Antes era 0,30, um placeholder que deixava tudo passar."

---

# 6 · Caso B — ao vivo (as rotas em ação)

**A demo é o centro.** Abro o chat e colo perguntas que exercitam cada rota — o sistema mostra a
**rota escolhida**, a **resposta citada** ou a **recusa com motivo**.

| pergunta | rota | resultado |
|---|---|---|
| *Resultado Recorrente Gerencial do Itaú no 4T25?* | **texto** | **R$ 12,3 bi**, citado da **pág. 8** |
| *Market share do Nubank em cartão no 4T25?* | **número** | SQL — **qualquer banco × modalidade**, sem precisar dizer "IF.data" |
| *Qual banco teve o maior share em consignado no 4T25?* | **ranking** | sem banco nomeado → compara **todos** e elege o líder com gap em p.p. |
| *Entre BB e Bradesco, quem ganhou mais share de consignado de 2023 a 2024?* | **comparativo** | BB **+0,7 p.p. a mais** (cross-bank, **janela escolhida**) |
| *O share do Bradesco no balanço bate com o que computamos do Bacen?* | **multi-fonte** | declarado **14,2%** (call) / **14,1%** (release) × computado **13,8%**, **lado a lado e citados** — a confirmação (~0,3 p.p.) se lê na hora |
| *Custo de crédito do Bradesco no 2T2027?* | **recusa** | **R1** — futuro fora da base, diz o motivo |

> 🎤 **Fale:** "Agora ao vivo. [abrir o chat] **Texto**: o lucro do Itaú — ele acha na página 8 e **cita**. **Número**: market share do Nubank em cartão, computado em SQL — e repara que funciona pra **qualquer banco e produto**, não só consignado. **Comparação entre bancos numa janela de anos**: quem ganhou mais share, com o **número exato** da diferença. O **coração do Caso B**, multi-fonte: cruzo o que o Bradesco **declarou** na call com o que **computei** do Bacen — os dois lados saem **citados, lado a lado**, e a confirmação (uns 0,3 p.p. de diferença) se lê na hora. Se o redator hesitar diante das tabelas, o sistema **não inventa nem recusa**: entrega a evidência citada. E a **recusa**: pergunto o futuro, ele recusa **com o motivo**."
>
> 💡 **Lógica:** aqui a tese vira concreta — cada pergunta é uma rota, e a banca vê o sistema **decidir e citar** em tempo real. Tenha as 6 perguntas **coladas** num bloco de notas pra não digitar errado ao vivo. **Ritual de demo:** abra a `ui_demo` com antecedência (a carga dos modelos leva ~1-2 min e o torch importa em silêncio antes do primeiro print); **não rode** `resolver_caso`/`perguntar` com o chat aberto (DuckDB é single-writer); cada pergunta é **independente** — sem follow-up curto ("e o Bradesco?"), refaça a pergunta completa.
>
> 🛡️ **Se a demo falhar (sem internet/modelo):** "Sem chave de LLM o sistema ainda **roteia, recupera, computa o número e cita** — só não redige o texto livre. A parte crítica não depende do LLM." (tenha um print/saída salvo como backup)
> 🛡️ **Se perguntarem "isso é mocado?":** "Não — é o backend real. Roteador é regra, número é SQL sobre o Bacen, citação é anexada por código. Posso mostrar o teste, ou rodem a pergunta que quiserem."
> 🛡️ **Se o multi-fonte não "narrar" um veredito:** "É desenho: o LLM só redige quando reconcilia com segurança; senão o sistema mostra declarado × computado **citados lado a lado** — não inventa nem recusa. A leitura (14,1% × 13,8%, ~0,3 p.p.) é imediata."
> 🛡️ **Se perguntarem "por que IF.data e não SCR.data (mensal)?":** "Escolha deliberada: o confronto declarado×computado é **trimestral por natureza** — release e call são trimestrais. Mensal não adicionaria nada ao Caso B e triplicaria a ingestão. O SCR é o upgrade natural se o uso pedir série mensal — mesma API Olinda, mesmo store."
> 🛡️ **Se pedirem o tom macro ENTRE ANOS (B2 do enunciado, ex.: 2023→2025):** "O corpus tem release/transcrição por trimestre e a pergunta vai pro caminho de texto; com 2+ períodos o pré-filtro de período é abandonado (fraqueza nomeada no README) — o retrieval semântico ainda recupera, mas sem garantia de cobertura de todos os trimestres. A trajetória completa pede mais transcrições ingeridas: no manifesto, é **1 linha por documento**."
> 🛡️ **Se perguntarem "vale a pena comprar?" / cotação:** "Regra **R8**: pedido de recomendação de investimento → recusa explícita. A base documenta **fatos** — cotação histórica e até o consenso de analistas publicado no release, tudo citável — mas **aconselhar compra/venda não é papel do sistema**. Numa gestora, essa recusa É a resposta certa." *(par de demo que prova a fronteira: "devo investir no Bradesco?" → recusa R8; "qual a recomendação dos analistas para BBDC4, segundo o release?" → responde o fato citado: Comprar 9, Manter 5, Vender 0.)*
> 🛡️ **Se a pergunta vier informal/sem trimestre e o texto recusar ("quanto o Itaú lucrou no último trimestre?"):** "Nomeie o trimestre ('no 4T25') — o pré-filtro de período fixa o documento certo num corpus multi-período; pergunta *period-ambígua* é fraqueza nomeada no README, com o fix futuro descrito (inferir o trimestre mais recente como default)."
> 🛡️ **Se perguntarem dado de TEMPO REAL ("Selic hoje"):** "A base é documental e **datada** — releases trimestrais e notas do Bacen com período. 'Hoje' não existe nela: o gate de evidência recusa, ou a resposta cita **o período do documento**. Tempo real é outra classe de fonte (API de mercado), que entraria pela mesma camada de ingestão."
> 🛡️ **Se a banca digitar a pergunta B1 do PDF ao pé da letra (Bradesco 2023):** "Recusa honesta — a janela de **texto** ingerida para a prova é 3T25→1T26 (números: 3T23→4T25). A pergunta é respondível pelo **desenho** (guidance num doc, realizado noutro — é a Q5 do eval com BB 2025); cobrir 2023 é ingestão, 1 linha por documento no manifesto."

---

# 7 · Resultados do eval ("comece pelo eval")

**Medi antes de otimizar.** Tudo reproduzível por script (`docs/resultados-eval.md`).

**Retrieval** (BGE-M3 + reranker reais; gold por **página**, curado por busca lexical + leitura → *anti-circular*):
- **hit@3 81,8%** · **MRR 0,686** · **hit@5 86,4%** — em **22 sondagens**, **5 fontes, 4 tipos** de doc
- **90%** nas sondagens *realistas* (sem gíria/paráfrase, que falham de propósito)

**Recusa por escopo** (determinístico): **12/12** comportamento certo · **over-recusa 0%** · **0 alucinação**

**Fidelidade** (faithfulness, juiz LLM **independente** — gpt-oss-120b ≠ gerador): **6/6** sustentadas

**Gate** calibrado: **0,60** é o joelho medido (0% vazamento, 0% over-recusa). **217 testes** de fluxo (sem rede/modelo).

> **O eval pegou um bug real:** um documento rotulado "Bradesco 3T25" era, na verdade, o release de
> **4T19** (URL errada na fonte). O hit@3 caiu, investiguei, troquei a URL — e subiu **77% → 82%**.
> *"Comece pelo eval"* funcionou na prática, não só no slide.

> 🎤 **Fale:** "O case diz 'comece pelo eval', e comecei. Retrieval: **hit@3 de 82%**, 90% nas perguntas realistas, num conjunto **heterogêneo** — releases longos e notas curtas, 5 fontes. Recusa: **12 de 12** certas, **zero** over-recusa. Fidelidade: 6 de 6, com um juiz de **outra família** de modelo pra não ter viés de auto-avaliação. E o melhor: o eval **pegou um erro real** — um documento que eu achava 3T25 era de 2019; o número caiu, investiguei e corrigi. Medir antes de afirmar."
>
> 💡 **Lógica:** o slide que mais pontua (eval = 50%). Lidere com os números, mas a **história do bug pego** é o que mostra maturidade — qualquer um cola um número; poucos deixam o eval **governar** a decisão.
>
> 🛡️ **Se perguntarem "n é pequeno":** "É, e sou explícito: escopo n=12, fidelidade n=6. **Sanidade forte**, não estatística de população. Em produção o gold cresce, idealmente por modalidade. Mas o arcabouço de medição está pronto e roda em segundos."
> 🛡️ **Se perguntarem "por que hit@3 e MRR?":** "hit@3 = a página certa está entre as 3 primeiras (o analista olha poucas). MRR = quão **no topo** ela vem, em média. Juntos dizem 'achei' **e** 'achei cedo'."

---

# 8 · O que me surpreendeu

**1. O LLM não é determinístico — nem a temperatura 0.** A mesma pergunta deu *responde → recusa →
responde* em 3 tentativas. Isso **confirmou** a arquitetura: confinar o não-determinismo ao texto
livre e manter roteador (regra), conta (SQL) e citação (código) **determinísticos**.

**2. O LLM faz conta BEM — quando recebe o contexto certo.** Testei e **refutei meu próprio
pressuposto** de que ele erraria a aritmética. Escolhi SQL mesmo assim — não por incapacidade do LLM,
mas por **auditabilidade** (re-executo e confiro o número).

**3. Uma "fraqueza" virou feature.** O Nubank reporta em IFRS (incomparável com os bancos Cosif em
guidance). Em vez de mascarar, isso virou a **recusa R2** — honestidade orgânica que o case valoriza.

**4. Uma auditoria adversarial do meu próprio código** achou que a comparação entre bancos
**ignorava os anos** da pergunta (dois recortes davam a mesma resposta). Corrigi e provei com dados
reais. **Duvidar do próprio código** achou o que os testes não pegavam.

> 🎤 **Fale:** "Quatro surpresas. Primeiro: o LLM **não é determinístico nem a zero grau** — a mesma pergunta mudou de resposta três vezes; isso me **convenceu** a deixar número e roteamento determinísticos. Segundo: eu **achava** que ele erraria contas, testei, e ele **acerta** com o contexto certo — então minha escolha por SQL é por **auditabilidade**, não por achar o modelo burro. Terceiro: a fraqueza do Nubank virou a recusa R2. Quarto: rodei uma **auditoria adversarial do meu próprio código** e ela achou um bug que os testes não pegavam — a comparação entre bancos ignorava o ano da pergunta. Corrigi."
>
> 💡 **Lógica:** mostra **honestidade intelectual** — você mudou de ideia com evidência (item 2) e duvidou do próprio trabalho (item 4). É o que separa "fiz funcionar" de "entendo o que fiz".
>
> 🛡️ **Se perguntarem "se o LLM faz conta, por que SQL?":** "Auditabilidade e reprodutibilidade. Um número de mercado eu quero poder **re-executar e conferir**, não depender de uma geração que pode variar. O LLM acerta a conta; eu só não quero *depender* disso."

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

> 🎤 **Fale:** "Crescer o corpus é **acrescentar linha ao manifesto** — o pipeline não muda. O que muda são os índices: hoje uso força-bruta porque é exata e instantânea nas 3.650 fichas; passando de ~100 mil, **não migro de banco** — ligo um índice **HNSW no próprio DuckDB** com a extensão VSS, um `CREATE INDEX`. Dedup vira por hash de conteúdo e o embedding vira incremental. Tudo projetado; não medi benchmark — não quis afirmar o que não testei."
>
> 🛡️ **Se perguntarem "e os 500+ do enunciado?":** "O case pede 500+ e crescendo. Provei a fundo com 11 documentos heterogêneos porque o critério nº 1 é **qualidade de retrieval**, não volume; o caminho de volume está desenhado e cabe no mesmo store. Preferi um problema **provado** a um número **alegado**."

---

# 11 · Fecho

**Com mais tempo, eu faria (em ordem de impacto):**
1. **Chunking ciente de tabela** — pra ler o número *declarado* na célula do release (hoje vai pelo SQL).
2. **Recalibrar o gate** com um gold maior, incl. gíria/paráfrase — fecha a over-recusa do caso difícil.
3. **Expansão de query** pra gíria (*"calote"* → *"inadimplência"*) — o limite mais visível do retrieval.
4. **Benchmark do HNSW in-place** (DuckDB VSS) — medir o ponto em que a força-bruta deixa de bastar.

**O que entrego hoje:** uma **fundação de retrieval confiável** — número **exato** (SQL), fonte
**sempre citada** (por código) e recusa **honesta com motivo** — provada a fundo por eval e pronta
pra crescer por manifesto.

> *"Separei texto de número — por isso o número está certo e o sistema recusa em vez de inventar."*

> 🎤 **Fale:** "Com mais tempo, minha lista é priorizada: ler tabela no texto, recalibrar o gate pra gíria, expansão de query, e medir o HNSW. Mas o que entrego hoje é o que importa numa fundação de research: o número é exato porque vem de SQL, a fonte é sempre citada porque é anexada por código, e quando não sei, recuso com o motivo. Provei por eval e desenhei como cresce. Obrigado — e bora pras perguntas."
>
> 💡 **Lógica:** feche pela **tese** (a frase-âncora) e por um roadmap **priorizado** — mostra que você sabe o que falta e em que ordem. Convide perguntas com confiança.
>
> 🛡️ **Se perguntarem "qual o item nº 1?":** "Chunking de tabela — destrava ler o número declarado direto do release, hoje o único lugar onde dependo do SQL pra contornar."
