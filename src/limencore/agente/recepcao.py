from dataclasses import dataclass
from datetime import datetime

from limencore.despejo import Despejo
from limencore.fio import Fio
from limencore.storage import Armazenamento

from .encaminhamento import DetectorDeEncaminhamento, DetectorPorExpressoes, Encaminhamento
from .movimento import Forma, Movimento
from .seletor import SeletorDeMovimento, SeletorGenerico


@dataclass(frozen=True)
class Recebido:  # o que a recepcao devolve: o despejo salvo, a jogada e o fio
    despejo: Despejo
    movimento: Movimento
    fios: tuple[Fio, ...]


class Recepcao:
    """Recebe um despejo, salva na hora e devolve a jogada.
    Nao decide nada: a jogada vem do seletor plugado na costura."""

    def __init__(
        self,
        armazenamento: Armazenamento,
        seletor: SeletorDeMovimento | None = None,
        detector: DetectorDeEncaminhamento | None = None,
    ):
        self._armazenamento = armazenamento
        self._seletor = seletor if seletor is not None else SeletorGenerico()
        self._detector = detector if detector is not None else DetectorPorExpressoes()

    def receber(self, texto: str, instante: datetime | None = None) -> Recebido | Encaminhamento:
        despejo = Despejo(conteudo=texto) if instante is None else Despejo(conteudo=texto, instante=instante)
        try:
            encaminhar = self._detector.deve_encaminhar(despejo.conteudo)
        except Exception:
            encaminhar = True  # na duvida, o lado seguro
        if encaminhar:
            self._armazenamento.salvar(despejo)  # guardado, sem fio: fora do loop
            return Encaminhamento(despejo=despejo)
        try:
            movimento = self._seletor.selecionar(despejo)
        except Exception:
            # fallback: nunca perder o despejo por falha do seletor
            movimento = Movimento(forma=Forma.UM_SO, alvos=(despejo.id,))
        # caso simples: sempre um fio com o despejo inteiro, qualquer que seja a forma
        fio = Fio(despejo_id=despejo.id)
        self._armazenamento.salvar_despejo_com_fios(despejo, [fio])
        return Recebido(despejo=despejo, movimento=movimento, fios=(fio,))
