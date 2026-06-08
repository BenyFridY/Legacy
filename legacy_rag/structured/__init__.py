"""Caminho dos NÚMEROS (ADR-0001) — store estruturado + cálculo em código.

Módulos:
- bacen.py        → baixa/parseia a carteira PF por modalidade do Bacen IF.data (Olinda, OData).
- store.py        → tabela `carteira_pf` no DuckDB + `market_share_conglomerado_serie()` em SQL
                    (soma os CNPJs do conglomerado ÷ total do sistema) — é o que o PIPELINE usa.
- market_share.py → funções PURAS de razão (market_share/ranking sobre um dict), usadas em teste/inspeção.

Respostas numéricas são CALCULADAS aqui — determinístico e auditável por re-execução do SQL,
nunca recuperadas como texto. É a fonte do 'gold' numérico do eval (Aula 4).
"""
