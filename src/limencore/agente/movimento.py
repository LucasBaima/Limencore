from dataclasses import dataclass
from enum import Enum

#é o esqueleto das categorias do despejo

class Forma(Enum):
    DIVIDIR = "Dividir"   # vários pensamentos misturados -> separar
    UM_SO = "Um só"       # um pensamento -> tratar direto
    LIGAR = "Ligar"       # dois ou mais que se conectam -> juntar


@dataclass(frozen=True)
class Movimento:
    forma: Forma
    alvos: tuple[str, ...]  # ids dos Despejo que este movimento trata

    def __post_init__(self):
        if not isinstance(self.forma, Forma):
            raise ValueError(f"forma invalida: esperado Forma, veio {self.forma!r}")
        if not self.alvos:
            raise ValueError("alvos vazio: um movimento precisa de ao menos um id-alvo")
        for a in self.alvos:
            if not isinstance(a, str) or not a.strip():
                raise ValueError(f"alvo invalido (id vazio ou nao-str): {a!r}")
