from dataclasses import dataclass

from limencore.corte import Corte
from limencore.forma import Forma


@dataclass(frozen=True)
class Movimento:
    forma: Forma
    alvos: tuple[str, ...]  # ids dos Despejo que este movimento trata
    corte: Corte | None = None  # None = o despejo inteiro

    def __post_init__(self):
        if not isinstance(self.forma, Forma):
            raise ValueError(f"forma invalida: esperado Forma, veio {self.forma!r}")
        if not self.alvos:
            raise ValueError("alvos vazio: um movimento precisa de ao menos um id-alvo")
        for a in self.alvos:
            if not isinstance(a, str) or not a.strip():
                raise ValueError(f"alvo invalido (id vazio ou nao-str): {a!r}")
        if self.corte is not None:
            if not isinstance(self.corte, Corte):
                raise ValueError(f"corte invalido: esperado Corte, veio {self.corte!r}")
            if self.corte.forma is not self.forma:
                raise ValueError(f"forma {self.forma.name} diverge do corte ({self.corte.forma.name})")
