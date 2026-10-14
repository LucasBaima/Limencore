from datetime import datetime, timezone

from limencore.fio import Fio
from limencore.nota import Nota
from limencore.storage import Armazenamento

from .encaminhamento import (
    Conferencia,
    DetectorDeEncaminhamento,
    DetectorPorExpressoes,
    Encaminhamento,
    Passagem,
    RegistroDaSessao,
)


class Quarto:
    """Escrever dentro do quarto passando pelo mesmo portao da entrada."""

    def __init__(
        self,
        armazenamento: Armazenamento,
        detector: DetectorDeEncaminhamento | None = None,
        sessao: RegistroDaSessao | None = None,
    ):
        self._armazenamento = armazenamento
        self._detector = detector if detector is not None else DetectorPorExpressoes()
        self._sessao = sessao if sessao is not None else RegistroDaSessao()

    def escrever(self, fio: Fio, texto: str) -> Nota | Conferencia | Encaminhamento:
        instante = datetime.now(timezone.utc)
        try:
            passagem = self._detector.avaliar(texto)
        except Exception:
            passagem = Passagem.ENCAMINHAR  # na duvida, o lado seguro
        if passagem is not Passagem.SEGUIR and self._sessao.houve_recente(instante):
            return self._encaminhar(texto, instante, oferece_retorno=False)
        if passagem is Passagem.ENCAMINHAR:
            return self._encaminhar(texto, instante, oferece_retorno=True)
        if passagem is Passagem.CONFERIR:
            return Conferencia(texto=texto, instante=instante)
        return self._armazenamento.escrever(fio, texto)

    def confirmar(self, fio: Fio, conferencia: Conferencia, acontecendo_agora: bool) -> Nota | Encaminhamento:
        if acontecendo_agora:
            recente = self._sessao.houve_recente(conferencia.instante)
            return self._encaminhar(conferencia.texto, conferencia.instante, oferece_retorno=not recente)
        # a pessoa ja respondeu: nao passa pelo detector de novo
        return self._armazenamento.escrever(fio, conferencia.texto)

    def _encaminhar(self, texto: str, instante: datetime, oferece_retorno: bool) -> Encaminhamento:
        # so lembra em memoria: nada vai pro banco
        self._sessao.registrar(instante)
        return Encaminhamento(texto=texto, instante=instante, oferece_retorno=oferece_retorno)
