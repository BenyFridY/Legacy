# Aula 3 — BM25 e busca híbrida

> Juntar "significado" (vetorial) com "palavra exata" (BM25).

## BM25 = busca pela palavra/termo exato

É um **"Ctrl+F com esteroides"** (como o Google clássico). Dá nota a um chunk com duas ideias:

1. **Frequência (TF):** quanto mais o termo buscado aparece, mais relevante (com saturação — 10× não é 10× melhor).
2. **Raridade (IDF):** **palavra rara vale mais que comum.** Em "consignado INSS", "de/o/a" não ajudam
   (aparecem em tudo); "consignado" e "INSS" são raras → **discriminam** → pesam muito.

Acerta em cheio **token exato, termo técnico raro, código, número, nome próprio**.
**Ponto cego:** é **literal** — "calote" não casa com "inadimplência". Não entende significado.

## Os dois são complementares (forças espelhadas)

| | Vetorial | BM25 |
|---|---|---|
| Significado / sinônimo / idioma | ✅ | ❌ |
| Termo exato / número / código / raro | ❌ | ✅ |

Fraquezas opostas → **usar as duas juntas** (busca **híbrida**).

## Fusão: por que NÃO somar as notas

As notas vivem em **escalas diferentes** (vetorial 0–1; BM25 solto: 2, 15, 40…). Somar = maçã com laranja.

Solução: **RRF (Reciprocal Rank Fusion)** — combina pela **posição** no ranking (1º, 2º, 3º…), não pela
nota bruta. Cada método **"vota"** nos seus melhores; quem aparece bem colocado **nos dois** sobe.
Posição é comparável; nota bruta não.

## Re-ranker (o passo final)

Depois da híbrida trazer ~20 candidatos, o **reranker** (`bge-reranker-v2-m3`) lê **pergunta + candidato
juntos** e dá uma nota de relevância mais fina, reordenando pro **top-5**.

> **Analogia:** híbrida = **triagem** (pega 20); reranker = **entrevista final** (escolhe 5). Mais caro,
> por isso só nos finalistas.

## O stack de retrieval completo

```
pergunta ─┬─► BM25 (palavra exata)        ─┐
          └─► vetorial / BGE-M3 (sentido) ─┴─► FUNDE (RRF) ─► RERANK (20→5) ─► trechos + citação
```

## No nosso caso

*"Qual o guidance de custo de crédito do Itaú para 2026?"*
- **BM25** crava "2026", "guidance", "custo de crédito" (exatos).
- **Vetorial** acha a seção que fala disso (mesmo com sinônimo: "projeção", "expectativa de perdas").
- **Fusão + rerank** entregam o parágrafo certo do MD&A → o gerador responde citando.

## Limite das DUAS buscas de texto

Pergunta como *"market share do BB em consignado no 4T25"* **não está escrita** em lugar nenhum —
é **calculada** (carteira do banco ÷ carteira do sistema). Nenhuma busca de texto resolve isso.
→ Por isso existe um **segundo caminho** (SQL/cálculo). É a Aula 4.
