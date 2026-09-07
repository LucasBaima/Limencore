from typing import Protocol, runtime_checkable

from limencore.entry import ThoughtEntry

from .pergunta import CamadaContencao, Pergunta


@runtime_checkable
class SeletorDePergunta(Protocol):
    """A costura: ponto de extensão para escolha de pergunta.

    O público entrega o SeletorGenerico como default; implementações
    privadas plugam aqui, sem alterar esta interface.
    """

    def selecionar(self, entry: ThoughtEntry) -> Pergunta: ...


class SeletorGenerico:
    """Implementação pública default. Zero inteligência de escolha."""

    def selecionar(self, entry: ThoughtEntry) -> Pergunta:
        return Pergunta(
            texto="O que está ocupando o espaço da minha mente neste momento?", 
            camada=None,
        )
