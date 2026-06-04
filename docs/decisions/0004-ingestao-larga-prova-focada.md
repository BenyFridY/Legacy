# ADR-0004 — Ingestão larga, prova focada (correção após reler o enunciado)

- **Status:** Aceita
- **Data:** 2026-06-04
- **Relacionada:** [ADR-0002](0002-fio-condutor-caso-b-consignado.md) (escopo da prova)

## Contexto

Releitura cuidadosa do PDF do case revelou que o escopo estreito (consignado × 3 bancos)
estava vazando para a **ingestão**, o que conflita com três exigências explícitas:

1. **"Base ligada" é o critério nº 1** ("o ponto mais importante e o que mais nos interessa avaliar"):
   a ingestão deve ir à fonte **sozinha e reproduzível** — para texto (RI/CVM) **e** estruturado (Bacen) —
   nada de upload manual. **O case não fornece nenhum documento; nós buscamos e fazemos o chunking.**
2. **Volume:** o sistema deve aguentar **500+ documentos**, e a rubrica pergunta "acha o trecho certo
   dentro de **centenas**?". Com poucos docs, o eval de retrieval não prova nada.
3. **Generalista:** "vamos testar outras perguntas que você não vê de antemão". Os **exemplos literais**
   do próprio enunciado usam **Santander + cartão (2023)**, **Bradesco + PDD (2023)** e
   **Itaú + macro (2022-2024)** — recortes diferentes do nosso foco.

## Decisão

Separar **escopo de ingestão** (largo) do **escopo de prova** (focado):

- **Ingestão (LARGA):** puxa, de forma automática e reproduzível, das fontes:
  - **Texto:** releases/MD&A e transcrições (quando públicas) dos grandes bancos — **incluindo os 5
    nomeados** (Itaú, Bradesco, Santander, BB, Nubank) — cobrindo **histórico de vários anos (~2022→2026)**.
  - **Estruturado:** Bacen IF.data/SCR.data — **todos os bancos e todas as modalidades** de um período
    (não filtrar para consignado na ingestão; o filtro é só no cálculo).
- **Prova (FOCADA):** eval harness + resolução continuam em **consignado × BB/Bradesco/Itaú**
  (o "problema provado a fundo"). Acrescentar **≥1 pergunta de B2 (tom)** ao eval (estava sub-coberto).

## Justificativa

- **Volume + generalidade + perguntas literais/não-vistas** exigem base ampla; só assim o retrieval
  "dentro de centenas" é crível e o sistema não quebra fora do consignado.
- **Custo quase zero no Bacen:** a mesma chamada já devolve todos os bancos/modalidades de um período —
  ingerir largo é praticamente de graça do lado estruturado.
- A **profundidade** (gold auditável, narrativa promete×entrega) fica onde dá pra provar bem: consignado.

## Consequências

- A ingestão de texto vira um **loop parametrizado** (banco × período × tipo de doc) — mais robusto e
  escalável (alinha com a pergunta "como escalaria para dezenas de milhares?").
- **Nubank** é ingerido como texto (20-F, EN) e aparece no Bacen (Cosif), mas o sistema trata sua
  **incomparabilidade** (USD/IFRS) na hora de comparar guidance/PDD — continua sendo o não-respondível
  orgânico para perguntas que cruzam base contábil/moeda.
- O `market_share()` e o roteador devem ser **genéricos** (qualquer modalidade/banco), não amarrados a
  consignado.
