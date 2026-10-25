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


MINIMO_DE_PALAVRAS = 3


def _palavras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.casefold())


def _contem(maior: list[str], menor: list[str]) -> bool:
    n = len(menor)
    return any(maior[i:i + n] == menor for i in range(len(maior) - n + 1))


def _repete_o_fio(janela: JanelaDoFio, texto: str) -> bool:
    # algum trecho do fio ou nota do usuario (3+ palavras) aparece inteiro, palavra por palavra, na resposta
    trechos = janela.trechos or (Trecho(0, len(janela.conteudo_do_despejo)),)
    pedacos = [recortar(janela.conteudo_do_despejo, t) for t in trechos]
    pedacos += [e.texto for e in janela.eventos if e.autoria == "usuario"]
    resposta = _palavras(texto)
    return any(
        len(p) >= MINIMO_DE_PALAVRAS and _contem(resposta, p) for p in map(_palavras, pedacos)
    )


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
            return self._encaminhar(conferencia.texto, conferencia.instante, oferece_retorno=not recente)
        # a pessoa ja respondeu: nao passa pelo detector de novo
        if conferencia.origem == "pousar":
            return self._armazenamento.pousar(fio, conferencia.texto)
        return self._gravar(fio, conferencia.texto)

    def pousar(self, fio: Fio, frase: str | None = None) -> Fio | Conferencia | Encaminhamento:
        if frase is not None and frase.strip():
            saida = self._portao(frase, "pousar")
            if saida is not None:
                return saida
        return self._armazenamento.pousar(fio, frase)

    def _portao(self, texto: str, origem: str) -> Conferencia | Encaminhamento | None:
        # None = segue
        instante = self._armazenamento.agora()
        try:
            passagem = self._detector.avaliar(texto)
        except Exception:
            passagem = Passagem.ENCAMINHAR  # na duvida, o lado seguro
        if passagem is not Passagem.SEGUIR and self._sessao.houve_recente(instante):
            return self._encaminhar(texto, instante, oferece_retorno=False)
        if passagem is Passagem.ENCAMINHAR:
            return self._encaminhar(texto, instante, oferece_retorno=True)
        if passagem is Passagem.CONFERIR:
            return Conferencia(texto=texto, instante=instante, origem=origem)
        return None

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

    def _encaminhar(self, texto: str, instante: datetime, oferece_retorno: bool) -> Encaminhamento:
        # so lembra em memoria: nada vai pro banco
        self._sessao.registrar(instante)
        return Encaminhamento(texto=texto, instante=instante, oferece_retorno=oferece_retorno)
