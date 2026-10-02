from dataclasses import dataclass


def normalizar_assunto(texto: str) -> str:
    """Chave para casar o mesmo assunto escrito de formas diferentes.
    So pega diferenca de ESCRITA (espacos, maiusculas). Acentos sao mantidos."""
    if not isinstance(texto, str):
        raise ValueError(f"assunto invalido: esperado str, veio {texto!r}")
    chave = " ".join(texto.split()).casefold()
    if not chave:
        raise ValueError("assunto vazio")
    return chave


def limpar_rotulo(texto: str) -> str:
    """Rotulo legivel: mesma grafia do usuario, so sem espacos sobrando."""
    normalizar_assunto(texto)  # valida
    return " ".join(texto.split())


@dataclass(frozen=True)
class Assunto:  # chave = para casar; rotulo = a primeira grafia, a oficial
    chave: str
    rotulo: str

    def __post_init__(self):
        if normalizar_assunto(self.chave) != self.chave:
            raise ValueError(f"chave nao normalizada: {self.chave!r}")
        if limpar_rotulo(self.rotulo) != self.rotulo:
            raise ValueError(f"rotulo com espacos sobrando: {self.rotulo!r}")
