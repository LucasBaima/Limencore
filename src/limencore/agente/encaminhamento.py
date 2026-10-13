import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from limencore.despejo import Despejo


@runtime_checkable
class DetectorDeEncaminhamento(Protocol):
    """Costura do portao: decide se um texto sai do fluxo normal.
    O publico entrega um detector simples; o privado pluga o calibrado."""

    def deve_encaminhar(self, texto: str) -> bool: ...


# PROVISORIA: nao validada. Nenhuma exposicao a usuario real antes de
# a lista e o texto do encaminhamento serem validados por profissionais.
# So frases de intencao em primeira pessoa e pouca ambiguidade.
# Expressoes de uso figurado comum ficam de fora: o sentido e trabalho de outra camada.
EXPRESSOES_PROVISORIAS: tuple[str, ...] = (
    "quero me matar", "penso em me matar", "pensando em me matar",
    "vontade de me matar", "nao quero mais viver",
    "tirar minha vida", "tirar a minha vida",
    "acabar com minha vida", "acabar com a minha vida",
    "suicidio", "suicida", "suicidar",
    "quero me machucar", "vontade de me machucar",
    "quero me cortar", "vontade de me cortar",
    "kill myself", "end my life", "suicide", "want to hurt myself",
)


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.casefold().split())


class DetectorPorExpressoes:
    """Detector publico: grosseiro de proposito. Erra pro lado do excesso."""

    def __init__(self, expressoes: tuple[str, ...] = EXPRESSOES_PROVISORIAS):
        normalizadas = [_normalizar(e) for e in expressoes if e.strip()]
        if not normalizadas:
            raise ValueError("lista de expressoes vazia")
        self._padrao = re.compile(
            r"\b(?:" + "|".join(re.escape(e) for e in normalizadas) + r")\b"
        )

    def deve_encaminhar(self, texto: str) -> bool:
        return bool(self._padrao.search(_normalizar(texto)))


@dataclass(frozen=True)
class Encaminhamento:  # a saida do sistema: sem fio, sem movimento, sem quarto
    despejo: Despejo
