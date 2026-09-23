from typing import Protocol, runtime_checkable

from limencore.entry import ThoughtEntry

from .movimento import Forma, Movimento


@runtime_checkable
class SeletorDeMovimento(Protocol):
    """A costura: ponto de extensão para escolha de movimento.

    O público entrega o SeletorGenerico como default; implementações
    privadas plugam aqui, sem alterar esta interface.
    """

    def selecionar(self, entry: ThoughtEntry) -> Movimento: ...


# Alias temporario: o repo privado ainda importa este nome.
# Remover quando o privado migrar para SeletorDeMovimento.
SeletorDePergunta = SeletorDeMovimento


class SeletorGenerico:
    """Implementação pública default. Zero inteligência de escolha."""

    def selecionar(self, entry: ThoughtEntry) -> Movimento:
        return Movimento(forma=Forma.UM_SO, alvos=(entry.id,))
