"""Etapas 5-6 — Geração da resposta (com citação e recusa).

Módulos:
- llm.py    → interface `LLMClient` trocável (ADR-0003). HOJE plugados: groq_free (Llama 3.3 70B) e
              None (fallback determinístico que mostra a evidência citada, sem redigir). Os demais
              (gemini_free / ollama / anthropic / claude_code) são a interface prevista, não implementados.
- answer.py → gate de evidência → (recusa) OU (LLM redige usando SÓ o contexto) + citação ESTRUTURAL.
- gate.py   → Estágio 2 da recusa: melhor nota do reranker < limiar → "não disponível na base".

A recusa é estrutural (caminho vazio / score abaixo do limiar), não "bom senso" do LLM (Aula 1).
"""
