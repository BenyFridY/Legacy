# Aula 4 — O caminho dos números (SQL e o roteador)

> Por que pergunta de número não vai pra busca, e sim pra cálculo em código.

## O problema: tem resposta que é CALCULADA, não escrita

*"Market share do BB em consignado no 4T25"* não existe escrito em documento nenhum:

```
share = carteira do BB em consignado ÷ carteira de TODOS os bancos em consignado
```

Outras do tipo: "qual banco teve a maior queda de share?", "variação YoY do consignado",
"some o capex das 4 empresas". São **conta / agregação / comparação** sobre muitas linhas.

## Por que a busca de texto é a ferramenta errada

A busca acha **texto parecido**; aqui a resposta é uma **conta sobre uma tabela**.

**Ponto honesto (desmonta um mito):** o problema **não** é "LLM não sabe somar" — sabe, com os números
certos na frente. O problema é **confiabilidade**. Calcular em **código (SQL)** ganha por 4 motivos:

1. **Determinístico** — mesmo resultado toda vez.
2. **Auditável** — re-roda o SQL e confere (é daqui que nasce o "gold" do eval).
3. **Escala** — 10 ou 100.000 linhas, tanto faz.
4. **Sem dígito alucinado** — zero risco de inventar número.

**Princípio:** número → cálculo em código; texto → busca. Cada ferramenta no seu trabalho.

## Guardamos número diferente de texto

| | Texto | Número |
|---|---|---|
| Vira | chunks → vetores + BM25 | uma **tabela** `(banco, modalidade, período, saldo)` |
| Responde | acha trecho + cita | **roda query SQL** que calcula |

## O roteador (quem decide texto vs. número)

```
                      ┌─► o que disseram / estratégia / tom?  → CAMINHO TEXTO (busca)
   pergunta → ROTEADOR┤
                      └─► número / share / variação / "quanto"? → CAMINHO SQL (cálculo)
```

Nosso roteador é **determinístico** (regras claras, não chute de caixa-preta) → **previsível e
explicável**. Perguntas como o **B3** usam **os dois caminhos**: cita a fala (texto) **e** mostra o
share calculado (SQL), lado a lado = "promete × entrega".

## Por que é o nosso diferencial

A maioria fará "RAG ingênuo" (tudo pela busca) e **quebra** nas perguntas de número — as que o case
adora. Nosso **caminho duplo** + **market share calculado e auditável** é a história que ganha.

## No código
- `legacy_rag/structured/` → tabela DuckDB + função `market_share` + cliente do Bacen.
- `legacy_rag/router/` → classifica a pergunta.
- O eval já cobre os dois tipos (B1/B3 número, B2 texto, não-respondíveis).
