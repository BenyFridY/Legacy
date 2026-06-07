# Resultados do eval — saídas reproduzíveis

> Este arquivo guarda a **saída real** dos avaliadores, para os números citados no
> [README](../README.md) terem **lastro reproduzível** — não "confie em mim".
> Reproduza com os comandos indicados em cada bloco (corpus de texto = Itaú 4T25;
> números = Bacen IF.data já ingeridos em `data/legacy.duckdb`).
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
  respostas corretas (respondeu certo) ......... 8
  recusas indevidas (recusou demais) ........... 0

  Taxa de recusa correta ... 100%   (dos que DEVIAM recusar)
  Taxa de over-recusa ...... 0%   (dos respondiveis, recusou por engano)
  Acuracia de comportamento  11/11

Distribuicao de rotas: {'doc_unico': 3, 'multi_fonte': 3, 'computada': 2, 'nao_respondivel': 3}
```

**Leitura honesta:** isto mede **só o Estágio 1** (escopo). O distrator
`nubank-share-cartao-respondivel` é proposital — Nubank em **cartão** É respondível no Cosif
(IF.data), então a recusa NÃO é por nome; é por cruzar bases contábeis incompatíveis. `n=11`
é **sanidade forte, não estatística de população**.

---

## 2. Qualidade de retrieval (hit@k / MRR — **BGE-M3 + reranker reais**)

Mede se o trecho certo sobe ao topo. Gold ancorado por **página** (estável entre reingestões),
curado por busca **lexical + leitura** — **independente do embedding**, para não ser circular.
Inclui **de propósito** 2 sondagens-limite (gíria "calote", paráfrase de consignado) que **devem
falhar** — eval honesto, sem cherry-picking. Comando (corpus = Itaú 4T25):

```
python scripts/prova_retrieval_real.py    # ingere o Itaú 4T25 (idempotente) se ainda não estiver
python scripts/eval_retrieval_real.py     # roda hit@k/MRR com os modelos reais
```

```
================================================================
EVAL DE RETRIEVAL (hit@k / MRR) — gold por pagina
================================================================
sondagens: 8
  id                          dif      h@1  h@3  h@5   RR
  itau-consignado-saldo       facil     ok  ok  ok   1.00
  itau-lucro-recorrente       media     ok  ok  ok   1.00
  itau-inadimplencia-90d      facil     ok  ok  ok   1.00
  itau-guidance-2026          media     ok  ok  ok   1.00
  itau-basileia-capital       media      .  ok  ok   0.50
  itau-margem-clientes        facil     ok  ok  ok   1.00
  itau-calote-giria           dificil    .   .   .   0.00
  itau-consignado-parafrase   dificil    .   .   .   0.00
----------------------------------------------------------------
  hit@1:  62.5%
  hit@3:  75.0%
  hit@5:  75.0%
  MRR  : 0.688
================================================================
```

**Leitura honesta:** nas **6 sondagens realistas**, **hit@3 = 100%** (5 em 1º lugar, Basileia em
2º). As 2 "difíceis" puxam o agregado para baixo **de propósito** e viram narrativa de engenharia:
a gíria "calote" o BGE-M3 (denso) liga a inadimplência, mas o cross-encoder (registro formal) não
discrimina; a paráfrase perifrástica ("descontado direto da folha") nenhum dos dois liga — e é
exatamente o sinal que o **gate de evidência (Estágio 2)** usa para recusar honestamente.
Corpus do **eval de retrieval** = Itaú 4T25 (as 8 sondagens-gold são todas dele); o Bradesco 4T25
também já está ingerido (para o B3), mas ainda sem sondagens-gold próprias.

---

## 3. Fidelidade da resposta — faithfulness (**LLM-juiz: Groq/Llama 3.3 70B, temperatura 0**)

A terceira perna: quando o sistema **responde**, cada afirmação está **sustentada pelo contexto
citado**? Um juiz (LLM) vê só `(pergunta, resposta, contexto)` e audita, listando o que não tem
suporte. Roda no pipeline **real** sobre o Itaú 4T25. Comando:

```
python scripts/eval_fidelidade_real.py
```

```
  [respondeu] itau-lucro: 'O lucro líquido recorrente do Itaú no 4T25 foi de R$ 12,3 bi'
  [respondeu] itau-consignado: 'R$ 75,3 bi.'
  [respondeu] itau-inadimplencia: '1,9%'
  [respondeu] itau-margem: 'A margem financeira com clientes do Itaú cresceu 1,5% no 4T2'
  [pulado: recusou] itau-guidance: O LLM não encontrou a resposta no contexto fornecido.

================================================================
EVAL - Fidelidade (faithfulness): a resposta e sustentada pelo contexto?
================================================================
casos: 4
  id                               fiel?  alegacoes_sem_suporte
----------------------------------------------------------------
  itau-lucro                       ok
  itau-consignado                  ok
  itau-inadimplencia               ok
  itau-margem                      X      a margem financeira com clientes subiu 8,6% no 4T25 em compa
----------------------------------------------------------------
  Taxa de fidelidade: 75%  (3/4)
================================================================
```

**Leitura honesta:** 3/4 das respostas geradas são **inteiramente sustentadas** pelo contexto. O
caso reprovado (margem) trouxe uma 2ª cifra (8,6%) que o juiz **não encontrou no contexto citado**
— exatamente o tipo de alegação sutil que a métrica existe para pegar; por isso reportamos a
**alegação**, não só a taxa, e ela vai para **revisão humana**. A `itau-guidance` foi corretamente
**pulada** (o LLM não achou a resposta no contexto → recusou: defesa em profundidade). Ressalvas
declaradas: `n=4` (corpus = só Itaú 4T25) e **juiz = gerador** (mesmo modelo Groq) → risco de viés
de auto-avaliação; um juiz independente + `n` maior é o próximo passo (ADR-0005).

---

## 4. Resolução do Caso B — ponta a ponta (**modelos reais: BGE-M3 + reranker + Groq/Llama 3.3 70B**)

Roda as 3 categorias do eval no orquestrador completo. Comando:

```
python scripts/resolver_caso.py
```

```
>>> Redator: GroqClient

========================================================================
[documento unico (texto)]  Qual foi o lucro liquido recorrente do Itau no 4T25?
------------------------------------------------------------------------
R$ 12,3 bi +3,7% 4T25 x 3T25

Fontes:
  - Itau, 4T25, release, pág. 8
  - Itau, 4T25, release, pág. 5
  - Itau, 4T25, release, pág. 39

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
Market share de BB em consignado: 2023-09: 19.9%, 2023-12: 20.2%, 2024-03: 20.3%, 2024-06: 20.3%, 2024-09: 20.5%, 2024-12: 20.1%, 2025-03: 19.8%, 2025-06: 19.8%, 2025-09: 19.5%, 2025-12: 19.2%. Variação no período: 19.9% -> 19.2% (queda).

Fontes:
  - Bacen IF.data, modalidade=consignado (Empréstimo com Consignação em Folha), market share = carteira / Σ sistema (calc. em SQL)

========================================================================
[nao-respondivel (futuro)]  Qual sera o custo de credito do Bradesco no 2o trimestre de 2027?
------------------------------------------------------------------------
[RECUSA] Não disponível na base. (R1: período 2027 está além da cobertura da base (realizado até 4T25, guidance até 2026).)

========================================================================
[nao-respondivel (cruza base contabil)]  Compare o guidance de custo de credito do Nubank com o do Itau.
------------------------------------------------------------------------
[RECUSA] Não disponível na base. (R2: comparação entre bases contábeis incompatíveis (IFRS ['Nubank'] x Cosif) numa métrica de release/Cosif ('custo_credito'). Sem base comum -> incomparável.)
```

**Leitura honesta:** as duas respostas de texto (lucro pág. 8, consignado pág. 21) são **redigidas
pelo LLM a partir do contexto recuperado**, com **citação anexada por código** (estrutural, não
depende do LLM lembrar de citar). A série de market share é **computada em SQL** (determinística,
auditável por re-execução) — o LLM nem entra nesse caminho. As recusas saem do **Estágio 1**
(roteador), com o motivo explícito.

---

## 5. Caso B3 ao vivo — DECLARADO × COMPUTADO (caminho `multi_fonte`)

A assinatura do Caso B: cruzar o que o banco **declara** (texto do release) com o que **computamos**
de forma independente (Bacen IF.data). Comando: `python scripts/resolver_b3.py`

```
[multi_fonte]  O market share de crédito consignado do Bradesco (INSS, setor privado e público)
               que ele reporta no balanço bate com o que computamos a partir do Bacen IF.data?
------------------------------------------------------------------------
Evidências para comparação (declarado x computado):

[T] (Bradesco, 4T25, release, pág. 14)  ...INSS Privado Público ... 14,1% Total
[T] (Bradesco, 4T25, release, pág. 41)  ...Crédito Consignado 14,1 14,2 14,3  (cols Dez25/Set25/Dez24)
[N] (Bacen IF.data, calc. em SQL)        Bradesco em consignado: ... 2024-12: 14.0%, 2025-06: 13.8%,
                                         2025-12: 13.8%.  (série 3T23->4T25)

Fontes: Bradesco 4T25 release pág.14 e pág.41 ; Bacen IF.data (SQL)
```
*(saída resumida — o sistema devolve todos os trechos recuperados, cada um citado; aqui mostramos os
que carregam o número.)*

**Resultado:** DECLARADO **14,1%** (4T25, do próprio relatório do Bradesco, p.14/p.41) ≈ COMPUTADO
**13,8%** (Bacen, 4T25) → **confirma** (diferença ~0,3 p.p., metodológica: o "Total" do Bradesco
inclui sublinhas próprias vs. nosso agregado por conglomerado).

**Leitura honesta (vira ADR-0005):** o sistema **roteou** para `multi_fonte`, **recuperou** o número
declarado e **computou** a série independente em SQL. Mas o LLM **não narrou** a frase "confere":
o valor declarado está numa **célula de tabela cujo chunk perdeu o cabeçalho/unidade** (`Crédito
Consignado 14,1 14,2 14,3`, sem `%` nem a coluna), então o LLM — corretamente instruído a **não
inventar** — devolveu o sentinela. Em vez de **recusar**, o orquestrador **cai para as duas
evidências citadas lado a lado** (honesto: não fabrica a leitura; útil: não vira recusa). Esta é
justamente a fraqueza de **RAG sobre tabelas** que motiva o **caminho dos NÚMEROS** (SQL), onde o
share sai exato e auditável — e não dependente de o LLM ler uma tabela crua.
