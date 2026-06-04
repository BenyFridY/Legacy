"""Caminho dos NÚMEROS (ADR-0001) — store estruturado + cálculo em código.

Módulos planejados:
- store.py        → carrega as linhas do Bacen numa tabela DuckDB (banco, modalidade, período, saldo).
- market_share.py → market_share() = carteira_banco / SUM(carteira_sistema) na modalidade e período.

Respostas numéricas são CALCULADAS aqui — determinístico e auditável por re-execução do SQL,
nunca recuperadas como texto. É a fonte do 'gold' numérico do eval (Aula 4).
"""
