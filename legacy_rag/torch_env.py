"""Workaround do conflito de OpenMP em ambiente conda — chamar ANTES de importar torch.

O problema (diagnosticado no ambiente): o torch traz a sua libomp.dll e o numpy/MKL do conda
traz a libiomp5md.dll. As duas são runtimes de OpenMP; carregar as duas no mesmo processo faz
o torch abortar com "OMP: Error #15". A flag KMP_DUPLICATE_LIB_OK=TRUE permite seguir.

É seguro para o NOSSO uso? Sim: o aviso do OMP é sobre paralelismo/threading, não sobre a
matemática. Verificamos empiricamente (matmul e softmax batem com o resultado conhecido). Para
inferência de embeddings/rerank isto é o workaround padrão e amplamente usado. A alternativa
"limpa" (um único runtime OpenMP no ambiente) é invasiva e fora de escopo do case.

Por que `setdefault`: respeita uma escolha do usuário se ele já tiver setado a variável.
"""
import os


def permitir_omp_duplicado() -> None:
    """Permite os dois runtimes de OpenMP (torch + MKL) coexistirem. Chamar antes de `import torch`."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
