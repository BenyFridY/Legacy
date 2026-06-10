# Resultados do eval — saídas reproduzíveis

> Este arquivo guarda a **saída real** dos avaliadores, para os números citados no
> [README](../README.md) terem **lastro reproduzível** — não "confie em mim".
> Corpus de **texto** = **11 documentos** (Itaú 4T25/3T25/1T26, Bradesco 4T25/3T25 + transcrição,
> BB 4T25 + sumário, Santander 4T25, 2 notas do Bacen; **3.650 fichas**) alimentado pelo
> `corpus/manifesto.yaml`; números = Bacen IF.data (10 trimestres) em `data/legacy.duckdb`.
>
> Execução registrada em **2026-06-07**. Prefixe os comandos no Windows com
> `set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &`.

---

## 1. Recusa por escopo (Estágio 1 — roteador determinístico, **sem modelo**)

Mede se o sistema **recusa o que está fora da base** e **responde o que está dentro**, usando
só o roteador determinístico (reproduzível, sem embedding/LLM). Comando:

```
python -m legacy_rag.eval.runner
```

```
========================================================================
EVAL - Recusa por ESCOPO (Estagio 1, roteador deterministico, sem modelo)
========================================================================
id                                     esperado  previsto  ok  rota
------------------------------------------------------------------------
bb-custo-credito-realizado-2025        answer    answer    ok  doc_unico
itau-guidance-custo-credito-2026       answer    answer    ok  doc_unico
bradesco-share-consignado-declarado    answer    answer    ok  doc_unico
bradesco-tom-macro-3t25                answer    answer    ok  doc_unico
bb-guidance-vs-realizado-2025          answer    answer    ok  multi_fonte
bradesco-share-declarado-vs-computado  answer    answer    ok  multi_fonte
itau-estrategia-clt-vs-share-real      answer    answer    ok  multi_fonte
bb-share-consignado-trajetoria         answer    answer    ok  computada
nubank-vs-itau-guidance-pdd            refuse    refuse    ok  nao_respondivel
bradesco-custo-credito-futuro          refuse    refuse    ok  nao_respondivel
itau-citacao-verbatim-inexistente      refuse    refuse    ok  nao_respondivel
nubank-share-cartao-respondivel        answer    answer    ok  computada
------------------------------------------------------------------------
Matriz de confusao de recusa:
  recusas corretas (recusou certo) ............. 3
  alucinacoes (respondeu o que devia recusar) .. 0
  respostas corretas (respondeu certo) ......... 9
  recusas indevidas (recusou demais) ........... 0

  Taxa de recusa correta ... 100%   (dos que DEVIAM recusar)
  Taxa de over-recusa ...... 0%   (dos respondiveis, recusou por engano)
  Acuracia de comportamento  12/12

Distribuicao de rotas: {'doc_unico': 4, 'multi_fonte': 3, 'computada': 2, 'nao_respondivel': 3}
```

**Leitura honesta:** isto mede **só o Estágio 1** (a ROTA). Inclui `bradesco-tom-macro-3t25` (B2 de
**tom**, respondível pela transcrição) e o distrator `nubank-share-cartao-respondivel` — Nubank em
**cartão** é respondível no Cosif e **responde ponta a ponta**: o caminho de números é **genérico**
(detecta a modalidade da pergunta e computa qualquer banco × modalidade — *Nubank cartão* **11,1% → 14,9%**).
A recusa do Nubank só ocorre ao **cruzar bases contábeis** (R2), nunca pelo nome. `n=12` é **sanidade
forte, não estatística** — e estas perguntas co-evoluíram com as regras (mede **consistência interna**).

---

## 2. Qualidade de retrieval (hit@k / MRR — **BGE-M3 + reranker reais**)

Mede se o trecho certo sobe ao topo. Gold ancorado por **página** (estável entre reingestões),
curado por busca **lexical + leitura** — **independente do embedding**, para não ser circular.
**22 sondagens** em **5 fontes (4 bancos + Bacen) e 4 tipos** de documento, com **retrieval ciente de período**
(a pergunta nomeia o trimestre → filtro de metadados fixa o documento certo). Inclui **de propósito**
2 sondagens-limite (gíria, paráfrase) que **devem falhar** — eval honesto, sem cherry-picking. Comando:

```
python scripts/ingerir_corpus.py          # alimenta a base de texto pelo manifesto (idempotente)
python scripts/eval_retrieval_real.py     # roda hit@k/MRR com os modelos reais (ciente de periodo)
```

```
================================================================
EVAL DE RETRIEVAL (hit@k / MRR) — gold por pagina
================================================================
sondagens: 22
  id                                  dif      h@1 h@3 h@5   RR
  itau-consignado-saldo               facil     ok  ok  ok  1.00
  itau-lucro-recorrente               media      .  ok  ok  0.33
  itau-inadimplencia-90d              facil     ok  ok  ok  1.00
  itau-guidance-2026                  media     ok  ok  ok  1.00
  itau-basileia-capital               media     ok  ok  ok  1.00
  itau-margem-clientes                facil     ok  ok  ok  1.00
  itau-calote-giria                   dificil    .   .   .  0.00
  itau-consignado-parafrase           dificil    .   .   .  0.00
  bb-consignado-4t25                  media      .  ok  ok  0.50
  bb-lucro-sumario-curto              facil     ok  ok  ok  1.00
  santander-lucro-4t25                facil      .  ok  ok  0.50
  bradesco-transcricao-politica-cred  media      .   .   .  0.00
  bacen-nota-credito                  media      .  ok  ok  0.50
  bradesco-lucro-recorrente-4t25      media      .  ok  ok  0.50
  bradesco-consignado-3t25            media     ok  ok  ok  1.00
  bradesco-inadimplencia-transcr-3t25 media      .  ok  ok  0.50
  itau-resultado-1t26                 media     ok  ok  ok  1.00
  itau-resultado-3t25                 media     ok  ok  ok  1.00
  santander-consignado-4t25           media      .   .  ok  0.25
  bb-guidance-custo-credito-2026      media     ok  ok  ok  1.00
  bb-inadimplencia-90d-4t25           media     ok  ok  ok  1.00
  bacen-inadimplencia-2026-01         media     ok  ok  ok  1.00
----------------------------------------------------------------
  hit@1:  54.5%
  hit@3:  81.8%
  hit@5:  86.4%
  MRR  : 0.686
================================================================
  Leitura: hit@3 nas sondagens realistas (sem giria/parafrase): 90%
```

**Leitura honesta:** o eval mede a **mesma busca da produção** (pré-filtro banco+período, funde 10,
rerank → 5). **Ampliamos o gold de 13 → 22 sondagens** para equilibrar os bancos (antes ~8 eram do Itaú)
e cobrir mais tipos/períodos. **Esse eval pegou um bug de dados:** o doc rotulado "Bradesco 3T25 release"
era, na verdade, o **4T19** (URL errada no manifesto) — corrigimos a URL e re-ingerimos o 3T25 real. Com
isso o hit@3 **subiu** (76,9% → **81,8%**) num conjunto maior **e correto**, e o MRR foi a **0,686**. Com o
**filtro de período**, **7 das 8** sondagens realistas do Itaú ficam em **rank 1** — incluindo o **RRG de
1T26 e de 3T25** (desambiguação entre trimestres quase idênticos). Nas **realistas**, **hit@3 = 90%**. Os
**limites honestos** que sobram: (1) gíria/paráfrase falham de propósito; (2) **transcrição conversacional**
— a fala sobre *política de crédito* do Bradesco perde para o release formal (mas a de *inadimplência 90d*,
também transcrição, acerta no top-3); (3) **Santander consignado** aparece só no hit@5 (a retração fica
enterrada na análise de carteira). A fraqueza de **número-em-tabela** segue real no **Caso B3** (o share
declarado de 14,1% vive numa célula), e é por isso que o número computado vai pelo **SQL**.

---

## 3. Fidelidade da resposta — faithfulness (**juiz INDEPENDENTE: openai/gpt-oss-120b ≠ gerador**)

A terceira perna: quando o sistema **responde**, cada afirmação está **sustentada pelo contexto
citado**? Um juiz (LLM) vê só `(pergunta, resposta, contexto)` e audita. O juiz é um **modelo de
família diferente** do gerador (gpt-oss-120b vs. Llama 3.3 70B) → **sem viés de auto-avaliação**.
Roda no pipeline **real** sobre 4 bancos. Comando:

```
python scripts/eval_fidelidade_real.py
```

```
>>> Eval de fidelidade — gerador=llama-3.3-70b-versatile | juiz INDEPENDENTE=openai/gpt-oss-120b
  [respondeu] itau-resultado: 'R$ 12,3 bi.'
  [respondeu] itau-consignado: 'R$ 75,3 bi.'
  [respondeu] itau-inadimplencia: '1,9%'
  [respondeu] itau-basileia: '15,2%'
  [pulado: recusou] itau-guidance: O LLM não encontrou a resposta no contexto fornecido.
  [pulado: recusou] bradesco-share: O LLM não encontrou a resposta no contexto fornecido.
  [respondeu] bb-lucro: 'R$ 5,7 bilhões.'
  [respondeu] santander-lucro: 'R$ 4,1 bilhões.'

================================================================
EVAL - Fidelidade (faithfulness): a resposta e sustentada pelo contexto?
================================================================
casos: 6
  id                               fiel?  alegacoes_sem_suporte
----------------------------------------------------------------
  itau-resultado                   ok
  itau-consignado                  ok
  itau-inadimplencia               ok
  itau-basileia                    ok
  bb-lucro                         ok
  santander-lucro                  ok
----------------------------------------------------------------
  Taxa de fidelidade: 100%  (6/6)
================================================================
```

**Leitura honesta:** **6/6** das respostas geradas (em 4 bancos) são **inteiramente sustentadas** pelo
contexto citado — agora com **juiz independente** (gpt-oss-120b ≠ gerador), removendo o viés de
auto-avaliação do `n=4` anterior (em que juiz = gerador). 2 perguntas foram **corretamente recusadas**:
`itau-guidance` (faixa ausente no contexto recuperado) e `bradesco-share` (número numa **célula de
tabela** — ver §5) → defesa em profundidade, não alucinação. Ressalva: `n=6` é sanidade forte, não
estatística de população; produção pede `n` maior e mais períodos.

---

## 3b. Calibração do gate de evidência (Estágio 2)

O limiar do gate deixou de ser placeholder. Pontuando um **mini-gold** (`eval/gate_gold.yaml`:
6 respondíveis × 6 fora-da-base) com o retrieval real e varrendo o limiar. Comando:

```
python scripts/calibrar_gate.py
```

```
  itau-consignado            answer  melhor_nota=0.728      fora-receita-bolo   refuse  melhor_nota=0.500
  itau-basileia              answer  melhor_nota=0.723      fora-copa-2022      refuse  melhor_nota=0.502
  itau-margem-clientes       answer  melhor_nota=0.715      fora-petrobras      refuse  melhor_nota=0.586
  itau-inadimplencia         answer  melhor_nota=0.726      fora-tempo          refuse  melhor_nota=0.502
  itau-resultado-recorrente  answer  melhor_nota=0.730      fora-bitcoin        refuse  melhor_nota=0.504
  bradesco-share-consignado  answer  melhor_nota=0.725      fora-populacao      refuse  melhor_nota=0.513

  limiar  over-recusa   vazamento    custo
   0.30    0/6 (  0%)   6/6 (100%)   1.00      <- antigo placeholder: deixava 100% vazar!
   0.55    0/6 (  0%)   1/6 ( 17%)   0.17
   0.60    0/6 (  0%)   0/6 (  0%)   0.00      <- joelho (escolhido)
  Recomendado (joelho): limiar = 0.60
```

**Leitura honesta:** respondíveis pontuam **~0,72**, fora-da-base **~0,50** — há uma **lacuna clara**.
O **0,30 antigo deixava 100% das fora-da-base passarem** (a "receita de bolo" só era barrada depois,
pelo LLM); o **0,60** separa perfeitamente (0% over-recusa, 0% vazamento) e barra fora-de-escopo **no
gate**. `LIMIAR_EVIDENCIA_PADRAO` foi ajustado para 0,60. Ressalva: `n=12` é pequeno; produção pede um
gold maior e por-modalidade (banda segura medida ~[0,60; 0,71]).

**3c. Fallback do reranker (`LIMIAR_DISCRIMINA_RERANK = 0,05`)** — quando o desvio-padrão das notas
do cross-encoder fica abaixo de 0,05, o pipeline mantém a ordem do RRF (o reranker "não discriminou").
Medido por `scripts/calibrar_discrimina_rerank.py` sobre as 22 sondagens (re-rodado em 10/06/2026):

```
  dificeis (giria/parafrase, n=2)   pstdev 0,004 e 0,042          -> fallback dispara nas DUAS (o caso-alvo)
  faceis/medias (n=20)              pstdev 0,004–0,088 (média 0,055) -> 8 de 20 TAMBÉM disparam
```

**Leitura honesta:** diferente do gate (§3b), aqui **não há vão limpo entre duas populações** — os
valores formam um contínuo (uma versão anterior deste parágrafo afirmava separação ≤0,048 vs ≥0,072,
que a re-medição não sustenta: o "vão" local é só 0,048–0,052). O 0,05 fica acima das duas difíceis
(o caso que motivou o mecanismo), mas 8 fáceis/médias disparam junto. Por que isso não compromete:
o fallback **não recusa nem descarta nada** — só decide qual ordenação confiar; nas fáceis que
disparam, a melhor nota segue ~0,73 (o gate decide igual) e a ordem do RRF já acerta — e o **hit@3
de 81,8% (§2) foi medido com o fallback ativo**, então o efeito já está dentro da métrica-manchete.
É um **ponto de operação com falha benigna**, não um joelho calibrado como o 0,60; produção pediria
um critério por distribuição (ex.: razão top1/top2) em vez de desvio-padrão global.

---

## 4. Resolução do Caso B — ponta a ponta (**modelos reais: BGE-M3 + reranker + Groq/Llama 3.3 70B**)

Roda as 3 categorias do eval no orquestrador completo. Comando:

```
python scripts/resolver_caso.py
```

```
>>> Redator: GroqClient

========================================================================
[documento unico (texto)]  Qual foi o Resultado Recorrente Gerencial do Itau no 4T25?
------------------------------------------------------------------------
R$ 12,3 bi, com um aumento de 3,7% em relação ao 3T25.

Fontes:
  - Itau, 4T25, release, pág. 8
  - Itau, 4T25, release, pág. 26
  - Itau, 4T25, release, pág. 5

========================================================================
[documento unico (texto)]  Qual o saldo da carteira de credito consignado do Itau no 4T25?
------------------------------------------------------------------------
R$ 75,3 bi.

Fontes:
  - Itau, 4T25, release, pág. 21
  - Itau, 4T25, release, pág. 15
  - Itau, 4T25, release, pág. 22
  - Itau, 4T25, release, pág. 13
  - Itau, 4T25, release, pág. 8

========================================================================
[computada (numeros / Bacen)]  Como evoluiu o market share do Banco do Brasil em consignado nos ultimos trimestres?
------------------------------------------------------------------------
Market share de BB em consignado: 2023-09: 19.9%, 2023-12: 20.2%, 2024-03: 20.3%, 2024-06: 20.3%, 2024-09: 20.5%, 2024-12: 20.1%, 2025-03: 19.8%, 2025-06: 19.8%, 2025-09: 19.5%, 2025-12: 19.2%. Variação (2023-09 a 2025-12): 19.9% -> 19.2% (queda).

Fontes:
  - Bacen IF.data, modalidade=consignado (Empréstimo com Consignação em Folha), market share = carteira / Σ sistema (calc. em SQL)

========================================================================
[nao-respondivel (futuro)]  Qual sera o custo de credito do Bradesco no 2o trimestre de 2027?
------------------------------------------------------------------------
[RECUSA] Não disponível na base. (R1: valor de 'custo_credito' em 2027 está além da cobertura da base (realizado até 4T25, guidance até 2026).)

========================================================================
[nao-respondivel (cruza base contabil)]  Compare o guidance de custo de credito do Nubank com o do Itau.
------------------------------------------------------------------------
[RECUSA] Não disponível na base. (R2: comparação entre bases contábeis incompatíveis (IFRS ['Nubank'] x Cosif ['Itau']) numa métrica de release/Cosif ('custo_credito'). Sem base comum -> incomparável.)
```

**Leitura honesta:** as duas respostas de texto (lucro pág. 8, consignado pág. 21) são **redigidas
pelo LLM a partir do contexto recuperado**, com **citação anexada por código** (estrutural, não
depende do LLM lembrar de citar). A série de market share é **computada em SQL** (determinística,
auditável por re-execução) — o LLM nem entra nesse caminho. As recusas saem do **Estágio 1**
(roteador), com o motivo explícito.

> **Nota (10/06/2026):** as partes **determinísticas** deste bloco (série SQL e as duas recusas)
> foram re-registradas com o código atual — as 4ª/5ª baterias melhoraram as mensagens (R1 passou a
> nomear a métrica; R2 nomeia os dois lados; a variação nomeia a janela). O comportamento é o mesmo.
> O script ganhou ainda 2 perguntas nas baterias (share do Nubank em cartão — determinística — e a
> B3 multi-fonte, mostrada no §5): quem rodar verá 7 blocos, não 5. As respostas **de texto** acima
> são o registro de 07/06 — na re-execução de hoje o Groq (free tier) caiu e o sistema degradou
> honestamente para evidências citadas, o cenário discutido no §6.

---

## 5. Caso B3 ao vivo — DECLARADO × COMPUTADO (caminho `multi_fonte`)

A assinatura do Caso B: cruzar o que o banco **declara** (texto) com o que **computamos** de forma
independente (Bacen IF.data). Comando: `python scripts/resolver_b3.py`

```
[multi_fonte]  O market share de crédito consignado do Bradesco (INSS, setor privado e público)
               que ele reporta no balanço bate com o que computamos a partir do Bacen IF.data?
------------------------------------------------------------------------
Evidências para comparação (declarado x computado):

[T2] (Bradesco, 3T25, transcricao, pág. 2)  "...o crédito consignado no Bradesco fechou agora o
     trimestre com quase R$ 102 bilhões... Temos um market share de aproximadamente 14,2%, dentre os
     bancos privados somos o maior... Nossa carteira de INSS tem 15,4%. No público, 14,3%. No
     privado, 7,5%..."   <- FALA DO CEO (declaração em linguagem natural)
[T6] (Bradesco, 4T25, release, pág. 14)  "...INSS 14,8%  Privado 6,6%  Público 15,2%  Total 14,1%"
[N1] (Bacen IF.data, calc. em SQL)  Bradesco em consignado: 2024-12: 14.0% ... 2025-09: 13.8%,
     2025-12: 13.8%   (série 3T23 -> 4T25)

Fontes: Bradesco 3T25 transcricao p.2/3/13 ; Bradesco 4T25 release p.14/p.41 ; Bacen IF.data (SQL)
```
*(saída resumida — o sistema recupera 10 trechos citados de 3 documentos do Bradesco + a série SQL;
aqui destacamos os que carregam o número.)*

**Resultado:** DECLARADO ≈ **14,2%** (CEO na teleconferência do 3T25) / **14,1%** (tabela do release
4T25) ≈ COMPUTADO **13,8%** (Bacen, 4T25) → **confirma** (~0,3-0,4 p.p. de diferença metodológica).
Com a transcrição na base, o sistema agora traz a **fala do CEO** — a declaração mais limpa, exatamente
como o Exemplo B3 do enunciado pede ("o que o CEO declarou").

**Leitura honesta (ADR-0005):** o sistema **roteou** para `multi_fonte`, recuperou o declarado (release
**e** transcrição) e **computou** a série independente em SQL. Mesmo com a fala do CEO ("14,2%") no
contexto, o LLM **não narrou** a frase "confere" e devolveu o sentinela: diante de 3 cifras próximas
(14,2% fala / 14,1% tabela / 13,8% computado) num contexto longo e cheio de **tabelas cruas**, ele —
corretamente instruído a **não inventar** — hesitou. Em vez de **recusar**, o orquestrador **cai para
as evidências citadas lado a lado** (honesto: não fabrica; útil: não vira recusa). Reforça a fraqueza de
**RAG sobre tabelas** que motiva o **caminho dos NÚMEROS** (SQL), onde o share sai exato e auditável.
