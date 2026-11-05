from dataclasses import dataclass

from limencore.forma import Forma


@dataclass(frozen=True)
class Trecho:  # pedaco exato do texto do despejo, marcado por posicao [inicio, fim); nunca copia
    # posicoes em code points (indices de str do Python), nao em unidades UTF-16;
    # quem fatiar em outra linguagem precisa converter.
    inicio: int
    fim: int

    def __post_init__(self):
        for nome, valor in (("inicio", self.inicio), ("fim", self.fim)):
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise ValueError(f"{nome} invalido: esperado int, veio {valor!r}")
        if not 0 <= self.inicio < self.fim:
            raise ValueError(f"trecho invalido: exige 0 <= inicio < fim, veio ({self.inicio}, {self.fim})")


@dataclass(frozen=True)
class FioPlanejado:  # o fio antes de nascer: uma unidade (um quarto) feita de um ou mais trechos
    trechos: tuple[Trecho, ...]

    def __post_init__(self):
        if not isinstance(self.trechos, tuple) or not self.trechos:
            raise ValueError("fio planejado vazio: precisa de ao menos um trecho")
        for t in self.trechos:
            if not isinstance(t, Trecho):
                raise ValueError(f"trecho invalido: esperado Trecho, veio {t!r}")
        inicios = [t.inicio for t in self.trechos]
        if inicios != sorted(inicios):
            raise ValueError("fio planejado fora de ordem: trechos devem vir ordenados por inicio")


@dataclass(frozen=True)
class Corte:  # onde a faca passou no despejo: um fio por FioPlanejado
    fios: tuple[FioPlanejado, ...]

    def __post_init__(self):
        if not isinstance(self.fios, tuple) or not self.fios:
            raise ValueError("corte vazio: precisa de ao menos um fio")
        for g in self.fios:
            if not isinstance(g, FioPlanejado):
                raise ValueError(f"fio planejado invalido: esperado FioPlanejado, veio {g!r}")
        todos = sorted((t for g in self.fios for t in g.trechos), key=lambda t: t.inicio)
        for anterior, seguinte in zip(todos, todos[1:]):
            if seguinte.inicio < anterior.fim:
                raise ValueError(f"trechos sobrepostos: {anterior} e {seguinte}")

    @property
    def forma(self):
        if len(self.fios) >= 2:
            return Forma.DIVIDIR
        if len(self.fios[0].trechos) >= 2:
            return Forma.LIGAR
        return Forma.UM_SO

    def validar_para(self, texto: str) -> None:
        for g in self.fios:
            for t in g.trechos:
                if t.fim > len(texto):
                    raise ValueError(f"trecho fora do texto: {t} (len={len(texto)})")
                if not recortar(texto, t).strip():
                    raise ValueError(f"trecho so de espacos: {t}")

    @classmethod
    def inteiro(cls, texto: str) -> "Corte":
        return cls(fios=(FioPlanejado(trechos=(Trecho(0, len(texto)),)),))


def recortar(texto: str, trecho: Trecho) -> str:
    return texto[trecho.inicio:trecho.fim]
