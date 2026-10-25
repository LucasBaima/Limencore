from dataclasses import dataclass
from datetime import datetime

from limencore.corte import Trecho

AUTORIAS = ("usuario", "agente")


@dataclass(frozen=True)
class Evento:  # uma nota (usuario) ou um turno (agente), com a autoria explicita
    autoria: str
    texto: str
    instante: datetime

    def __post_init__(self):
        if self.autoria not in AUTORIAS:
            raise ValueError(f"autoria invalida: esperado um de {AUTORIAS}, veio {self.autoria!r}")
        if not isinstance(self.texto, str) or not self.texto.strip():
            raise ValueError("evento vazio")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")


@dataclass(frozen=True)
class JanelaDoFio:  # so os dados de um fio (e dos juntados nele)
    conteudo_do_despejo: str
    trechos: tuple[Trecho, ...]  # vazio = o despejo inteiro
    eventos: tuple[Evento, ...]  # em ordem de instante
    fio_id: str | None = None
    criado_em: datetime | None = None
    assunto: str | None = None  # rotulo do assunto, se houver

    def __post_init__(self):
        if not isinstance(self.trechos, tuple) or any(not isinstance(t, Trecho) for t in self.trechos):
            raise ValueError(f"trechos invalidos: esperado tuple de Trecho, veio {self.trechos!r}")
        if not isinstance(self.eventos, tuple) or any(not isinstance(e, Evento) for e in self.eventos):
            raise ValueError(f"eventos invalidos: esperado tuple de Evento, veio {self.eventos!r}")
        if self.criado_em is not None and self.criado_em.tzinfo is None:
            raise ValueError("criado_em sem timezone: use datetime timezone-aware (UTC)")
