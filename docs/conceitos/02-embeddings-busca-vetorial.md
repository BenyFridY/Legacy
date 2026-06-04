# Aula 2 — Embeddings e busca vetorial

> Como a máquina mede que "esse trecho combina com a pergunta".

## Por que "procurar a palavra igual" não basta

Buscar pelos termos exatos da pergunta quebra o tempo todo em finanças:

| Você pergunta… | …mas o documento escreveu… |
|---|---|
| "inadimplência" | "calote", "PDD", "perdas com crédito" |
| "lucro subiu" | "resultado da instituição melhorou" |
| "consignado" (PT) | "payroll loan" (EN — Nubank) |

Precisamos buscar por **significado**, não por letra.

## A grande ideia: significado vira números

Um **embedding** é uma **lista de números (vetor)** que representa o **significado** de um texto.

> **Analogia:** uma **coordenada de GPS pro sentido**. Cada frase ganha uma "localização" num mapa
> de significados. Sentidos parecidos ficam **perto**; diferentes ficam **longe**.

Quem faz texto → vetor é o **modelo de embedding** (o nosso é o **BGE-M3**). Ele **aprendeu sozinho**,
treinando em bilhões de textos, a colocar significados parecidos próximos — inclusive entre idiomas.
Ninguém programou "calote = inadimplência" na mão.

## Exemplo concreto (números de mentira, 3 dimensões)

Eixos imaginários: `[fala de crédito?, fala de animal?, fala de clima?]`

```
"o lucro com crédito do banco subiu"          → [0.95, 0.02, 0.05]
"o resultado da carteira de crédito melhorou" → [0.90, 0.04, 0.08]   ← PERTO
"o gato dormiu no sofá à tarde"               → [0.03, 0.92, 0.40]   ← LONGE
```

1º e 2º quase não compartilham palavras, mas os vetores estão pertinho → a busca acha um pelo outro.
**Esse é o superpoder.**

*(Embeddings reais: o BGE-M3 tem **1024 dimensões**, e os eixos não são rótulos bonitinhos — são
padrões abstratos que o modelo criou. A intuição é a mesma.)*

## Como a busca funciona

```
PREPARAÇÃO:  chunk → (BGE-M3) → vetor → guardado no índice (DuckDB)
CONSULTA:    pergunta → (BGE-M3) → vetor da pergunta
             → mede quais vetores de chunk estão MAIS PERTO → top-k = trechos recuperados
```

A régua de perto/longe é a **similaridade do cosseno** — um **"parecômetro" de 0 a 1** (1 = sentido
muito parecido; 0 = nada a ver). Tecnicamente, o ângulo entre os vetores.

## Dúvidas que esclarecemos

- **PCA não é o mecanismo da busca.** PCA é uma técnica de **reduzir dimensões** (1024 → 2 ou 3) só pra
  **visualizar** os vetores num gráfico (ver os agrupamentos: consignado × cartão × macro). A busca de
  verdade usa os **1024 números originais**. PCA = lente de visualização/apresentação.
- **Embedding ≠ "prever a próxima palavra".** São dois modelos com trabalhos diferentes:

| Ferramenta | Trabalho | Quando |
|---|---|---|
| Modelo de embedding (BGE-M3) | resume **significado** num vetor, pra **buscar** | recuperar trechos |
| LLM gerador (Claude etc.) | prevê a **próxima palavra**, pra **escrever** | gerar a resposta |

## O ponto cego (motiva a Aula 3)

A busca vetorial é forte em significado, mas **escorrega no exato**: "R$ 38,5 bi" ≈ "R$ 43,5 bi",
"4T25" ≈ "3T25", "ITUB4" ≈ "ITUB3", "consignado INSS" ≈ "consignado CLT". Pra ela são quase iguais;
pra você são coisas diferentes. → É o que o **BM25** (busca por palavra exata) conserta.
