import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from limencore.corte import Trecho, recortar
from limencore.fio import Fio
from limencore.janela import JanelaDoFio
from limencore.nota import Nota
from limencore.storage import Armazenamento

from .encaminhamento import (
    ORIGENS_DA_CONFERENCIA,
    Conferencia,
    DetectorDeEncaminhamento,
    DetectorPorExpressoes,
    Encaminhamento,
    Familia,
    Passagem,
    RegistroDaSessao,
)


@dataclass(frozen=True)
class RespostaDoQuarto:  # o que o agente devolve; texto=None = nada a dizer
    texto: str | None
    destacar_pouso: bool


@runtime_checkable
class AgenteDoQuarto(Protocol):
    """Costura do quarto. O publico entrega o AgenteSilencioso;
    o privado pluga o seu."""

    def responder(self, janela: JanelaDoFio) -> RespostaDoQuarto: ...


class AgenteSilencioso:
    """Sombra publica: nunca fala."""

    def responder(self, janela: JanelaDoFio) -> RespostaDoQuarto:
        tem_nota = any(e.autoria == "usuario" for e in janela.eventos)
        return RespostaDoQuarto(texto=None, destacar_pouso=tem_nota)


@dataclass(frozen=True)
class Escrito:  # a nota gravada + a resposta do agente
    nota: Nota
    resposta: RespostaDoQuarto


MINIMO_DE_PALAVRAS = 4


def _palavras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.casefold())


def _sequencias(palavras: list[str]) -> set[tuple[str, ...]]:
    n = MINIMO_DE_PALAVRAS
    return {tuple(palavras[i:i + n]) for i in range(len(palavras) - n + 1)}


def _repete_o_fio(janela: JanelaDoFio, texto: str) -> bool:
    # a resposta tem 4+ palavras seguidas de algum trecho do fio ou nota do usuario
    trechos = janela.trechos or (Trecho(0, len(janela.conteudo_do_despejo)),)
    pedacos = [recortar(janela.conteudo_do_despejo, t) for t in trechos]
    pedacos += [e.texto for e in janela.eventos if e.autoria == "usuario"]
    resposta = _sequencias(_palavras(texto))
    return any(not resposta.isdisjoint(_sequencias(_palavras(p))) for p in pedacos)


def avaliar_no_portao(
    detector: DetectorDeEncaminhamento, texto: str
) -> tuple[Passagem, Familia, tuple[Familia, ...]]:
    # adaptador: detector que so tem avaliar() fala da propria pessoa
    try:
        avaliar_com_familias = getattr(detector, "avaliar_com_familias", None)
        if avaliar_com_familias is not None:
            passagem, familia, outras = avaliar_com_familias(texto)
            outras = tuple(outras)
        else:
            avaliar_com_familia = getattr(detector, "avaliar_com_familia", None)
            if avaliar_com_familia is None:
                return detector.avaliar(texto), Familia.SI_MESMA, ()
            (passagem, familia), outras = avaliar_com_familia(texto), ()
        if not all(isinstance(f, Familia) for f in (familia, *outras)):
            raise TypeError(f"familia invalida: {familia!r}, {outras!r}")
        return passagem, familia, outras
    except Exception:
        return Passagem.ENCAMINHAR, Familia.SI_MESMA, ()  # na duvida, o lado seguro


def marca_a_sessao(familia: Familia) -> bool:
    # risco de terceiro nao marca a sessao nem perde o retorno
    return familia is not Familia.ALGUEM_EM_RISCO


class Quarto:
    """Escrever dentro do quarto passando pelo mesmo portao da entrada."""

    def __init__(
        self,
        armazenamento: Armazenamento,
        detector: DetectorDeEncaminhamento | None = None,
        sessao: RegistroDaSessao | None = None,
        agente: AgenteDoQuarto | None = None,
    ):
        self._armazenamento = armazenamento
        self._detector = detector if detector is not None else DetectorPorExpressoes()
        self._sessao = sessao if sessao is not None else RegistroDaSessao()
        self._agente = agente if agente is not None else AgenteSilencioso()

    def escrever(self, fio: Fio, texto: str) -> Escrito | Conferencia | Encaminhamento:
        saida = self._portao(texto, "escrever")
        if saida is not None:
            return saida
        return self._gravar(fio, texto)

    def confirmar(
        self, fio: Fio, conferencia: Conferencia, acontecendo_agora: bool
    ) -> Escrito | Fio | Encaminhamento:
        if conferencia.origem not in ORIGENS_DA_CONFERENCIA:
            raise ValueError(f"conferencia sem origem do quarto: {conferencia.origem!r}")
        if acontecendo_agora:
            recente = self._sessao.houve_recente(conferencia.instante)
            return self._encaminhar(
                conferencia.texto, conferencia.instante, not recente,
                conferencia.familia, conferencia.outras_familias, conferencia.origem,
            )
        # a pessoa ja respondeu: nao passa pelo detector de novo
        return self._seguir(fio, conferencia.texto, conferencia.origem)

    def voltar(self, fio: Fio, encaminhamento: Encaminhamento) -> Escrito | Fio:
        # so o risco de terceiro tem volta: o texto segue o fluxo normal, sem detector
        if encaminhamento.familia is not Familia.ALGUEM_EM_RISCO:
            raise ValueError(f"encaminhamento sem volta: {encaminhamento.familia!r}")
        if encaminhamento.origem not in ORIGENS_DA_CONFERENCIA:
            raise ValueError(f"encaminhamento sem origem do quarto: {encaminhamento.origem!r}")
        return self._seguir(fio, encaminhamento.texto, encaminhamento.origem)

    def pousar(self, fio: Fio, frase: str | None = None) -> Fio | Conferencia | Encaminhamento:
        if frase is not None and frase.strip():
            saida = self._portao(frase, "pousar")
            if saida is not None:
                return saida
        return self._armazenamento.pousar(fio, frase)

    def _portao(self, texto: str, origem: str) -> Conferencia | Encaminhamento | None:
        # None = segue
        instante = self._armazenamento.agora()
        passagem, familia, outras = avaliar_no_portao(self._detector, texto)
        if passagem is not Passagem.SEGUIR and marca_a_sessao(familia) and self._sessao.houve_recente(instante):
            return self._encaminhar(texto, instante, False, familia, outras, origem)
        if passagem is Passagem.ENCAMINHAR:
            return self._encaminhar(texto, instante, True, familia, outras, origem)
        if passagem is Passagem.CONFERIR:
            return Conferencia(
                texto=texto, instante=instante, origem=origem, familia=familia, outras_familias=outras
            )
        return None

    def _seguir(self, fio: Fio, texto: str, origem: str) -> Escrito | Fio:
        if origem == "pousar":
            return self._armazenamento.pousar(fio, texto)
        return self._gravar(fio, texto)

    def _gravar(self, fio: Fio, texto: str) -> Escrito:
        nota = self._armazenamento.escrever(fio, texto)
        janela = self._armazenamento.janela(fio.id)
        try:
            resposta = self._agente.responder(janela)
        except Exception:
            # a nota ja foi gravada: falha do agente cai na sombra silenciosa
            resposta = AgenteSilencioso().responder(janela)
        if resposta.texto is not None and (not resposta.texto.strip() or _repete_o_fio(janela, resposta.texto)):
            resposta = RespostaDoQuarto(texto=None, destacar_pouso=resposta.destacar_pouso)
        if resposta.texto is not None:
            self._armazenamento.registrar_turno(fio, resposta.texto)
        return Escrito(nota=nota, resposta=resposta)

    def _encaminhar(
        self,
        texto: str,
        instante: datetime,
        oferece_retorno: bool,
        familia: Familia,
        outras: tuple[Familia, ...],
        origem: str | None,
    ) -> Encaminhamento:
        # so lembra em memoria: nada vai pro banco
        if marca_a_sessao(familia):
            self._sessao.registrar(instante)
        else:
            oferece_retorno = True
        return Encaminhamento(
            texto=texto, instante=instante, oferece_retorno=oferece_retorno,
            familia=familia, outras_familias=outras, origem=origem,
        )
