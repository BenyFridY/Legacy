"""Etapa 1 — Ingestão: coletar dado CRU das fontes públicas (não calcula nada).

Módulos planejados:
- bacen.py    → cliente da API Olinda (IF.data trimestral / SCR.data mensal): devolve
                linhas estruturadas (banco, período, modalidade, saldo).
- releases.py → baixa releases e transcrições via CDN mziq (não pelas páginas de RI, que
                dão 403) e extrai texto (pypdf/pdfplumber).

Alimenta os dois caminhos: `structured/` (números) e `index/` (texto).
"""
