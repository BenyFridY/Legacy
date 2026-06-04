"""Roteador (Aula 4) — decide o caminho de cada pergunta, de forma DETERMINÍSTICA.

Módulo planejado:
- router.py → classifica a pergunta por regras explícitas (não chute de caixa-preta):
    • número / market share / variação / "quanto" + período  → caminho ESTRUTURADO (SQL)
    • discurso / estratégia / tom                            → caminho de TEXTO (retrieval)
    • B3 ("disse X" e "aconteceu?")                          → OS DOIS caminhos

Determinístico = previsível e explicável (o case premia "como você pensa").
"""
