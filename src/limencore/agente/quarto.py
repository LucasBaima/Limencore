from limencore.despejo import Despejo
from limencore.fio import Fio
from limencore.nota import Nota
from limencore.storage import Armazenamento

from .encaminhamento import DetectorDeEncaminhamento, DetectorPorExpressoes, Encaminhamento


class Quarto:
    """Escrever dentro do quarto passando pelo mesmo portao da entrada."""

    def __init__(self, armazenamento: Armazenamento, detector: DetectorDeEncaminhamento | None = None):
        self._armazenamento = armazenamento
        self._detector = detector if detector is not None else DetectorPorExpressoes()

    def escrever(self, fio: Fio, texto: str) -> Nota | Encaminhamento:
        try:
            encaminhar = self._detector.deve_encaminhar(texto)
        except Exception:
            encaminhar = True  # na duvida, o lado seguro
        if encaminhar:
            despejo = Despejo(conteudo=texto)
            self._armazenamento.salvar(despejo)  # mesma saida da entrada: sem fio
            return Encaminhamento(despejo=despejo)
        return self._armazenamento.escrever(fio, texto)
