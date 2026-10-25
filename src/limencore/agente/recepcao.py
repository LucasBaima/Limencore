from dataclasses import dataclass
from datetime import datetime

from limencore.despejo import Despejo
from limencore.fio import Fio
from limencore.storage import Armazenamento

from .encaminhamento import (
    Conferencia,
    DetectorDeEncaminhamento,
    DetectorPorExpressoes,
    Encaminhamento,
    Familia,
    Passagem,
    RegistroDaSessao,
)
from .movimento import Forma, Movimento
from .quarto import avaliar_no_portao, marca_a_sessao
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
        sessao: RegistroDaSessao | None = None,
    ):
        self._armazenamento = armazenamento
        self._seletor = seletor if seletor is not None else SeletorGenerico()
        self._detector = detector if detector is not None else DetectorPorExpressoes()
        self._sessao = sessao if sessao is not None else RegistroDaSessao()

    def receber(
        self, texto: str, instante: datetime | None = None
    ) -> Recebido | Conferencia | Encaminhamento:
        despejo = Despejo(conteudo=texto) if instante is None else Despejo(conteudo=texto, instante=instante)
        passagem, familia, outras = avaliar_no_portao(self._detector, despejo.conteudo)
        if passagem is not Passagem.SEGUIR and marca_a_sessao(familia) and self._sessao.houve_recente(despejo.instante):
            return self._encaminhar(despejo.conteudo, despejo.instante, False, familia, outras)
        if passagem is Passagem.ENCAMINHAR:
            return self._encaminhar(despejo.conteudo, despejo.instante, True, familia, outras)
        if passagem is Passagem.CONFERIR:
            return Conferencia(
                texto=despejo.conteudo, instante=despejo.instante, familia=familia, outras_familias=outras
            )
        return self._seguir(despejo)

    def confirmar(self, conferencia: Conferencia, acontecendo_agora: bool) -> Recebido | Encaminhamento:
        if acontecendo_agora:
            recente = self._sessao.houve_recente(conferencia.instante)
            return self._encaminhar(
                conferencia.texto, conferencia.instante, not recente,
                conferencia.familia, conferencia.outras_familias,
            )
        # a pessoa ja respondeu: nao passa pelo detector de novo
        return self._seguir(Despejo(conteudo=conferencia.texto, instante=conferencia.instante))

    def voltar(self, encaminhamento: Encaminhamento) -> Recebido:
        # so o risco de terceiro tem volta: o texto segue o fluxo normal, sem detector
        if encaminhamento.familia is not Familia.ALGUEM_EM_RISCO:
            raise ValueError(f"encaminhamento sem volta: {encaminhamento.familia!r}")
        return self._seguir(Despejo(conteudo=encaminhamento.texto, instante=encaminhamento.instante))

    def _encaminhar(
        self, texto: str, instante: datetime, oferece_retorno: bool, familia: Familia, outras: tuple[Familia, ...]
    ) -> Encaminhamento:
        # so lembra em memoria: nada vai pro banco
        if marca_a_sessao(familia):
            self._sessao.registrar(instante)
        else:
            oferece_retorno = True
        return Encaminhamento(
            texto=texto, instante=instante, oferece_retorno=oferece_retorno,
            familia=familia, outras_familias=outras,
        )

    def _seguir(self, despejo: Despejo) -> Recebido:
        try:
            movimento = self._seletor.selecionar(despejo)
        except Exception:
            # fallback: nunca perder o despejo por falha do seletor
            movimento = Movimento(forma=Forma.UM_SO, alvos=(despejo.id,))
        fios = self._fios_do_corte(despejo, movimento)
        self._armazenamento.salvar_despejo_com_fios(despejo, list(fios))
        return Recebido(despejo=despejo, movimento=movimento, fios=fios)

    def _fios_do_corte(self, despejo: Despejo, movimento: Movimento) -> tuple[Fio, ...]:
        # sem corte, ou corte que nao cabe no texto: um fio com o despejo inteiro
        if movimento.corte is None:
            return (Fio(despejo_id=despejo.id),)
        try:
            movimento.corte.validar_para(despejo.conteudo)
        except ValueError:
            return (Fio(despejo_id=despejo.id),)
        return tuple(Fio(despejo_id=despejo.id, trechos=g.trechos) for g in movimento.corte.fios)
