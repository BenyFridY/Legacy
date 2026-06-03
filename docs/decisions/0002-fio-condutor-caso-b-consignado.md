# ADR-0002 — Fio condutor: Caso B (bancos), modalidade consignado, núcleo Bradesco + BB + Itaú

- **Status:** Aceita
- **Data:** 2026-06-03
- **Relacionada:** [ADR-0001](0001-arquitetura-dual-path.md) (arquitetura)

## Contexto

O case pede "um problema provado a fundo" e oferece três exemplos (A capex/NVIDIA, B bancos, C backtest RPO), explicitando que "os exemplos são o sarrafo, não a especificação". Era preciso escolher **um** fio condutor e, dentro dele, **escopo** (quais bancos, qual modalidade), com base em viabilidade real de dados — não em qual soa mais impressionante.

## Decisão

**Fio condutor = Caso B (bancos brasileiros).** Dentro dele:

- **Modalidade:** **consignado** (uma só, provada a fundo).
- **Núcleo (3 bancos, todos BRL/Cosif):** **Banco do Brasil (BBAS3)**, **Bradesco (BBDC4)**, **Itaú (ITUB4)**.
- **Não-respondível orgânico:** **Nubank / Nu Holdings** (USD/IFRS via Form 20-F).
- **Opcional (4º, se sobrar tempo):** Banrisul (BRSR6).
- **Excluídos do núcleo:** Santander BR (SANB11) — sem guidance numérico de PDD; Banco Inter — atrito de entidade Cayman/IFRS.

Sub-casos cobertos: **B1** (guidance de custo de crédito/PDD vs. realizado — multi-hop temporal+numérico), **B3** (estratégia declarada vs. market share **computado** do Bacen), **B2** (tom macro — apenas como "cor", não avaliado com gabarito duro).

## Justificativa

**Por que Caso B** (detalhe em [ADR-0001](0001-arquitetura-dual-path.md) e no fact-check): vence os dois eixos de maior peso da rubrica (retrieval 25% + eval 25% = 50%) porque o entregável central (market share) é **computado e auditável por re-execução de SQL**, a heterogeneidade é nativa (texto PT + estruturado + temporal) e as 3 categorias de eval caem sem forçar. Caso A tem ground-truth difuso (capex projetado: US$600-760B conforme a fonte) que corrói o eval; Caso C é quase mono-modal (numérico) e deixa o caminho de texto ocioso.

**Por que consignado:** é o hotspot estratégico declarado de 2025-26 (Crédito do Trabalhador / consignado privado CLT) em todos os bancos do núcleo; o Bradesco **declara o share na transcrição verbatim oficial** (CEO: consignado ≈14,2%; INSS 15,4%, público 14,3%, privado 7,5%) → confronto direto fala-citável vs. share-computado. Cartão forçaria o Nubank (líder, ~14%) para dentro do núcleo — mas Nubank é o não-respondível pretendido (USD/IFRS).

**Por que esses 3 bancos** (verificado ao vivo):

| Banco | Texto | Transcrição | IF.data | Consignado | Guidance PDD (B1) |
|---|---|---|---|---|---|
| **BB** (BBAS3) | PDF texto limpo (mziq) | só vídeo/áudio | COMPE 001, conglom. prudencial | líder (INSS+servidores+CLT) | **faixa numérica + revisões + realizado** |
| **Bradesco** (BBDC4) | relatório texto nativo (escaneado é só a *apresentação*) | **verbatim oficial PT; CEO declara o share** | conglom. prudencial CNPJ base 60746948 | share ~14,2% declarado | parcial (proxy margem-líq.-após-PDD) |
| **Itaú** (ITUB4) | MD&A texto limpo via CDN mziq | descontinuada (3º = paywall) | conglom. 60.872.504 | "Novo Consignado CLT" +35,9%/25 | **range fechado R$38,5-43,5 bi/26** |

BB e Itaú dão o B1 "duro" (guidance numérico); Bradesco dá o B3 ideal (share declarado na fala).

## Decisões técnicas / armadilhas já mapeadas

1. **Ingestão de releases:** baixar **bytes crus do CDN mziq** (`filemanager-cdn.mziq.com` / `api.mziq.com`) e extrair com `pdftotext`/`pypdf`. **Não** ingerir pelas páginas HTML de RI (403 anti-bot no Itaú e no domínio `itau.com.br`). O helper do WebFetch classifica FlateDecode erroneamente como "escaneado/OCR" — falso para Bradesco/BMG/Inter.
2. **Nível de consolidação no IF.data:** fixar **conglomerado prudencial** (não instituição individual), senão subconta-se o share. Bradesco origina cartão parcialmente via "Banco Bradesco Cartões S.A." (entra no consolidado). Validar a chave da API Olinda (CodInst numérico vs CNPJ) e **versionar** o crosswalk.
3. **Quebra metodológica Res. CMN 4.966/21 (IFRS 9), a partir de 2025:** muda "PDD → custo de crédito" no release **e** no IF.data (alinhado ao novo Cosif desde mar/2025). Todo B1 que cruzar a fronteira 2024→2025 deve tratar a descontinuidade; dentro de 2025+ a comparação banco-vs-sistema fica consistente.
4. **Regra de recusa (Nubank):** checar se a pergunta **cruza base contábil/moeda** (IFRS↔Cosif), não apenas o nome do banco. Um B3 de share por modalidade do Nubank É respondível em Cosif (IF.data C0084693: cartão R$170,4 bi, consignado R$4,87 bi em 202503); o que se recusa é comparar guidance/custo de crédito IFRS-USD com peers Cosif-BRL.
5. **CDN mziq compartilhado:** filtrar pelo tenant correto (BB = `5760dff3...`; não confundir com CAIXA `fb86b0b8...` / BB Seguridade) e validar a capa do emissor antes de ingerir.

## Consequências

**Ganhos:** escopo enxuto e provável a fundo em 7 dias; B1 e B3 cobertos por fonte oficial citável; não-respondível orgânico (Nubank); base estruturada já validada ao vivo (Olinda).
**Sacrifícios/limitações honestas:** transcrição verbatim oficial só existe para Bradesco no núcleo — para Itaú/BB, B2/B1 citam a seção "Management commentary" do MD&A/release (texto oficial), não a fala literal da call. B1 do Bradesco depende de proxy (não há linha isolada de guidance de PDD). B2 (tom) fica como camada de cor.

## Próximos passos

- **Começar pelo eval** (ADR/artefato): montar o harness com ~10 perguntas nas 3 categorias (doc-único, multi-fonte/multi-período, não-respondível), com gold auditável.
- Cliente Olinda IF.data parametrizado + função `market_share` testável.
- ADR de chunking (transcrição por turno de fala / release por seção; tabela como unidade atômica; header de metadados por chunk).
