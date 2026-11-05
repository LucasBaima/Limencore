import logging
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from limencore.agente.encaminhamento import (
    Conferencia,
    Encaminhamento,
    Familia,
    Passagem,
    RegistroDaSessao,
)
from limencore.agente.quarto import Escrito, Quarto, RespostaDoQuarto
from limencore.agente.recepcao import Recepcao
from limencore.fio import EstadoFio
from limencore.nota import Nota, TipoNota
from limencore.storage import Armazenamento


class DetectorQueFalha:
    def avaliar(self, texto):
        raise RuntimeError("detector quebrou")


@pytest.fixture
def armazenamento():
    a = Armazenamento(":memory:")
    yield a
    a.fechar()


@pytest.fixture
def fio(armazenamento):
    (fio,) = Recepcao(armazenamento).receber("o prazo do relatorio").fios
    return armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)


def test_escrever_normal_devolve_nota(armazenamento, fio):
    resultado = Quarto(armazenamento).escrever(fio, "falta a parte dos numeros")
    assert isinstance(resultado, Escrito)
    assert isinstance(resultado.nota, Nota)
    notas = armazenamento.notas(fio.id)
    assert len(notas) == 1
    assert notas[0].tipo is TipoNota.NOTA


def test_explicito_encaminha_sem_gravar_nada(armazenamento, fio):
    antes = armazenamento.listar()
    resultado = Quarto(armazenamento).escrever(fio, "acho que quero me matar")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    assert armazenamento.notas(fio.id) == []
    assert armazenamento.listar() == antes
    assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.ESCOLHIDO


def test_ambiguo_confere_sem_gravar(armazenamento, fio):
    resultado = Quarto(armazenamento).escrever(fio, "nao aguento mais esse relatorio")
    assert isinstance(resultado, Conferencia)
    assert resultado.texto == "nao aguento mais esse relatorio"
    assert armazenamento.notas(fio.id) == []


def test_confirmar_falso_grava_a_nota(armazenamento, fio):
    quarto = Quarto(armazenamento)
    conferencia = quarto.escrever(fio, "nao aguento mais esse relatorio")
    resultado = quarto.confirmar(fio, conferencia, False)
    assert isinstance(resultado, Escrito)
    assert isinstance(resultado.nota, Nota)
    assert [n.texto for n in armazenamento.notas(fio.id)] == ["nao aguento mais esse relatorio"]


def test_confirmar_verdadeiro_encaminha_sem_gravar(armazenamento, fio):
    antes = armazenamento.listar()
    quarto = Quarto(armazenamento)
    conferencia = quarto.escrever(fio, "nao aguento mais esse relatorio")
    resultado = quarto.confirmar(fio, conferencia, True)
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []
    assert armazenamento.listar() == antes


def test_sessao_compartilhada_com_a_recepcao(armazenamento, fio):
    sessao = RegistroDaSessao()
    entrada = Recepcao(armazenamento, sessao=sessao).receber(
        "quero me matar", instante=datetime.now(timezone.utc)
    )
    assert isinstance(entrada, Encaminhamento)
    resultado = Quarto(armazenamento, sessao=sessao).escrever(fio, "nao aguento mais")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is False
    assert armazenamento.notas(fio.id) == []


def test_detector_que_falha_encaminha(armazenamento, fio):
    resultado = Quarto(armazenamento, DetectorQueFalha()).escrever(fio, "falta a parte dos numeros")
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []


# --- depois do commit da nota, nada derruba o escrever ---

NOTA_COMUM = "falta a parte dos numeros"
NOTA_AMBIGUA = "nao aguento mais esse relatorio"
SILENCIO = RespostaDoQuarto(texto=None, destacar_pouso=True)


class AgenteQueFala:
    def __init__(self):
        self.chamadas = 0

    def responder(self, janela):
        self.chamadas += 1
        return RespostaDoQuarto(texto="e o resto?", destacar_pouso=False)


class AgenteQueFalha:
    def responder(self, janela):
        raise RuntimeError("agente quebrou")


class DetectorDeTerceiro:  # o unico encaminhamento que tem volta
    def avaliar_com_familia(self, texto):
        return Passagem.ENCAMINHAR, Familia.ALGUEM_EM_RISCO


class ConexaoEspia:  # sqlite3.Connection nao aceita monkeypatch: embrulha e conta os commits
    def __init__(self, conexao, falhar_no_commit=False):
        self._conexao = conexao
        self._falhar_no_commit = falhar_no_commit
        self.commits = 0

    def commit(self):
        self.commits += 1
        if self._falhar_no_commit:
            raise sqlite3.OperationalError("database is locked")
        self._conexao.commit()

    def __getattr__(self, nome):
        return getattr(self._conexao, nome)


def _falha_do_banco(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


def _por_escrever(armazenamento, fio, agente):
    return Quarto(armazenamento, agente=agente).escrever(fio, NOTA_COMUM)


def _por_confirmar(armazenamento, fio, agente):
    quarto = Quarto(armazenamento, agente=agente)
    conferencia = quarto.escrever(fio, NOTA_AMBIGUA)
    assert isinstance(conferencia, Conferencia)
    assert conferencia.origem == "escrever"
    return quarto.confirmar(fio, conferencia, False)


def _por_voltar(armazenamento, fio, agente):
    quarto = Quarto(armazenamento, DetectorDeTerceiro(), agente=agente)
    encaminhamento = quarto.escrever(fio, NOTA_COMUM)
    assert isinstance(encaminhamento, Encaminhamento)
    assert encaminhamento.origem == "escrever"
    return quarto.voltar(fio, encaminhamento)


CAMINHOS = [_por_escrever, _por_confirmar, _por_voltar]
CAMINHOS_COM_AGENTE = [_por_escrever, _por_confirmar]  # voltar nao chama o agente: nao ha o que falhar


def _nota_gravada_em_silencio(armazenamento, fio, resultado):
    assert isinstance(resultado, Escrito)
    assert resultado.resposta == SILENCIO
    assert len(armazenamento.notas(fio.id)) == 1
    assert armazenamento.notas(fio.id)[0].texto == resultado.nota.texto
    assert armazenamento.turnos(fio.id) == []


@pytest.mark.parametrize("caminho", CAMINHOS_COM_AGENTE)
def test_janela_que_falha_nao_derruba(armazenamento, fio, monkeypatch, caminho):
    monkeypatch.setattr(armazenamento, "janela", _falha_do_banco)
    agente = AgenteQueFala()
    resultado = caminho(armazenamento, fio, agente)
    _nota_gravada_em_silencio(armazenamento, fio, resultado)
    assert agente.chamadas == 0


@pytest.mark.parametrize("caminho", CAMINHOS_COM_AGENTE)
def test_registrar_turno_que_falha_nao_derruba(armazenamento, fio, monkeypatch, caminho):
    monkeypatch.setattr(armazenamento, "registrar_turno", _falha_do_banco)
    resultado = caminho(armazenamento, fio, AgenteQueFala())
    _nota_gravada_em_silencio(armazenamento, fio, resultado)


@pytest.mark.parametrize("caminho", CAMINHOS_COM_AGENTE)
def test_commit_do_turno_que_falha_nao_deixa_turno_parcial(armazenamento, fio, monkeypatch, caminho):
    # falha de verdade dentro do storage: o INSERT ja rodou quando o commit quebra
    registrar_de_verdade = armazenamento.registrar_turno
    conexao_real = armazenamento._conexao

    def registrar_com_commit_quebrado(*args):
        armazenamento._conexao = ConexaoEspia(conexao_real, falhar_no_commit=True)
        try:
            return registrar_de_verdade(*args)
        finally:
            armazenamento._conexao = conexao_real

    monkeypatch.setattr(armazenamento, "registrar_turno", registrar_com_commit_quebrado)
    resultado = caminho(armazenamento, fio, AgenteQueFala())
    _nota_gravada_em_silencio(armazenamento, fio, resultado)
    assert not conexao_real.in_transaction


@pytest.mark.parametrize("caminho", CAMINHOS_COM_AGENTE)
def test_agente_que_falha_nao_derruba(armazenamento, fio, caminho):
    resultado = caminho(armazenamento, fio, AgenteQueFalha())
    _nota_gravada_em_silencio(armazenamento, fio, resultado)


def test_agente_que_devolve_lixo_nao_derruba(armazenamento, fio):
    class AgenteDeLixo:
        def responder(self, janela):
            return None

    resultado = _por_escrever(armazenamento, fio, AgenteDeLixo())
    _nota_gravada_em_silencio(armazenamento, fio, resultado)


def test_sem_falha_o_turno_continua_sendo_gravado(armazenamento, fio):
    resultado = _por_escrever(armazenamento, fio, AgenteQueFala())
    assert resultado.resposta == RespostaDoQuarto(texto="e o resto?", destacar_pouso=False)
    assert [t.texto for t in armazenamento.turnos(fio.id)] == ["e o resto?"]


def test_falha_na_janela_nao_duplica_a_nota(armazenamento, fio, monkeypatch):
    monkeypatch.setattr(armazenamento, "janela", _falha_do_banco)
    assert isinstance(Quarto(armazenamento).escrever(fio, NOTA_COMUM), Escrito)
    monkeypatch.undo()
    assert [n.texto for n in armazenamento.notas(fio.id)] == [NOTA_COMUM]


# --- antes do commit, a recusa continua sendo recusa ---


@pytest.mark.parametrize("caminho", CAMINHOS)
def test_fio_jogado_continua_recusado(armazenamento, caminho):
    (jogado,) = Recepcao(armazenamento).receber("o prazo do relatorio").fios
    agente = AgenteQueFala()
    with pytest.raises(ValueError, match="fio fora do quarto"):
        caminho(armazenamento, jogado, agente)
    assert armazenamento.notas(jogado.id) == []
    assert agente.chamadas == 0


def test_texto_vazio_continua_recusado(armazenamento, fio):
    agente = AgenteQueFala()
    with pytest.raises(ValueError, match="nota vazia"):
        Quarto(armazenamento, agente=agente).escrever(fio, "   ")
    assert armazenamento.notas(fio.id) == []
    assert agente.chamadas == 0


def test_commit_da_nota_que_falha_continua_lancando(armazenamento, fio, monkeypatch):
    # a fronteira: se o commit da nota quebra, a nota nao existe e a pessoa precisa saber
    conexao_real = armazenamento._conexao
    agente = AgenteQueFala()
    monkeypatch.setattr(armazenamento, "_conexao", ConexaoEspia(conexao_real, falhar_no_commit=True))
    with pytest.raises(sqlite3.OperationalError):
        Quarto(armazenamento, agente=agente).escrever(fio, NOTA_COMUM)
    monkeypatch.undo()
    assert armazenamento.notas(fio.id) == []
    assert not conexao_real.in_transaction
    assert agente.chamadas == 0


# --- pousar: uma transacao so, sem agente ---


def test_pousar_grava_tudo_num_commit_so_e_nao_chama_o_agente(armazenamento, fio, monkeypatch):
    espia = ConexaoEspia(armazenamento._conexao)
    monkeypatch.setattr(armazenamento, "_conexao", espia)
    agente = AgenteQueFala()
    pousado = Quarto(armazenamento, agente=agente).pousar(fio, "combinei o prazo com a equipe")
    assert pousado.estado is EstadoFio.RESOLVIDO
    assert armazenamento.buscar_fio(fio.id).estado is EstadoFio.RESOLVIDO
    assert [(n.tipo, n.texto) for n in armazenamento.notas(fio.id)] == [
        (TipoNota.POUSO, "combinei o prazo com a equipe")
    ]
    assert espia.commits == 1
    assert agente.chamadas == 0
    assert armazenamento.turnos(fio.id) == []


def test_pousar_desfaz_o_estado_se_a_nota_falhar(armazenamento, fio, monkeypatch):
    monkeypatch.setattr(armazenamento, "_inserir_nota", _falha_do_banco)
    with pytest.raises(sqlite3.OperationalError):
        Quarto(armazenamento).pousar(fio, "combinei o prazo com a equipe")
    monkeypatch.undo()
    assert armazenamento.buscar_fio(fio.id).estado is EstadoFio.ESCOLHIDO
    assert armazenamento.notas(fio.id) == []
    assert EstadoFio.RESOLVIDO not in [t.para for t in armazenamento.historico(fio.id)]


# --- voltar: silencio deliberado, que nao e a sombra de falha ---

SILENCIO_DELIBERADO = RespostaDoQuarto(texto=None, destacar_pouso=False)
LOGGER = "limencore.agente"
MARCADOR = "marcadorsecreto"


def _registros(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == LOGGER]


def test_voltar_grava_a_nota_em_silencio_sem_chamar_o_agente(armazenamento, fio):
    agente = AgenteQueFala()
    resultado = _por_voltar(armazenamento, fio, agente)
    assert isinstance(resultado, Escrito)
    assert resultado.resposta == SILENCIO_DELIBERADO
    assert agente.chamadas == 0
    assert armazenamento.turnos(fio.id) == []
    assert [n.texto for n in armazenamento.notas(fio.id)] == [NOTA_COMUM]


def test_voltar_nao_monta_a_janela(armazenamento, fio, monkeypatch, caplog):
    # se montasse, a falha cairia na sombra: destacaria o pouso e iria pro log
    monkeypatch.setattr(armazenamento, "janela", _falha_do_banco)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        resultado = _por_voltar(armazenamento, fio, AgenteQueFalha())
    assert resultado.resposta == SILENCIO_DELIBERADO
    assert _registros(caplog) == []


@pytest.mark.parametrize("caminho", CAMINHOS_COM_AGENTE)
def test_escrever_e_confirmar_seguem_chamando_o_agente(armazenamento, fio, caminho):
    agente = AgenteQueFala()
    resultado = caminho(armazenamento, fio, agente)
    assert resultado.resposta == RespostaDoQuarto(texto="e o resto?", destacar_pouso=False)
    assert agente.chamadas == 1
    assert [t.texto for t in armazenamento.turnos(fio.id)] == ["e o resto?"]
    assert len(armazenamento.notas(fio.id)) == 1


def test_voltar_com_origem_pousar_nao_chama_o_agente(armazenamento, fio, caplog):
    agente = AgenteQueFala()
    quarto = Quarto(armazenamento, DetectorDeTerceiro(), agente=agente)
    encaminhamento = quarto.pousar(fio, NOTA_COMUM)
    assert isinstance(encaminhamento, Encaminhamento)
    assert encaminhamento.origem == "pousar"
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        pousado = quarto.voltar(fio, encaminhamento)
    assert pousado.estado is EstadoFio.RESOLVIDO
    assert agente.chamadas == 0
    assert armazenamento.turnos(fio.id) == []
    assert [(n.tipo, n.texto) for n in armazenamento.notas(fio.id)] == [(TipoNota.POUSO, NOTA_COMUM)]
    assert _registros(caplog) == []


# --- logger: so o tipo da falha, nunca texto de ninguem ---


def test_sombra_registra_o_tipo_da_falha(armazenamento, fio, monkeypatch, caplog):
    monkeypatch.setattr(armazenamento, "janela", _falha_do_banco)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        _por_escrever(armazenamento, fio, AgenteQueFala())
    assert _registros(caplog) == [(logging.WARNING, "quarto: sombra por OperationalError")]


def test_log_nunca_leva_a_mensagem_da_excecao_nem_a_nota(armazenamento, fio, caplog):
    class AgenteComSegredo:
        def responder(self, janela):
            raise RuntimeError(f"quebrou em: {MARCADOR}")

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        Quarto(armazenamento, agente=AgenteComSegredo()).escrever(fio, f"anotei {MARCADOR} aqui")
    assert _registros(caplog) == [(logging.WARNING, "quarto: sombra por RuntimeError")]
    assert MARCADOR not in caplog.text
    assert all(r.exc_info is None and r.exc_text is None for r in caplog.records)


def test_voltar_nao_gera_log(armazenamento, fio, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        _por_voltar(armazenamento, fio, AgenteQueFala())
    assert _registros(caplog) == []


def test_sem_configuracao_nada_vai_pro_stderr(capfd):
    # processo a parte: dentro do pytest o caplog fica na raiz e o lastResort nunca dispararia
    roteiro = """
import sqlite3
from limencore.agente import Quarto, Recepcao
from limencore.fio import EstadoFio
from limencore.storage import Armazenamento

a = Armazenamento(":memory:")
(fio,) = Recepcao(a).receber("o prazo do relatorio").fios
fio = a.atualizar_estado(fio, EstadoFio.ESCOLHIDO)

def falha(*args):
    raise sqlite3.OperationalError("database is locked")

a.janela = falha
assert Quarto(a).escrever(fio, "falta a parte dos numeros").resposta.destacar_pouso is True
"""
    fonte = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run([sys.executable, "-c", roteiro], check=True, env={**os.environ, "PYTHONPATH": fonte})
    assert capfd.readouterr().err == ""


# --- origem "avaliar": o quarto nao aceita ---


@pytest.mark.parametrize("acontecendo_agora", [True, False])
def test_quarto_confirmar_recusa_origem_avaliar(armazenamento, fio, acontecendo_agora):
    sessao = RegistroDaSessao()
    agente = AgenteQueFala()
    instante = datetime.now(timezone.utc)
    conferencia = Conferencia(texto=NOTA_AMBIGUA, instante=instante, origem="avaliar")
    with pytest.raises(ValueError):
        Quarto(armazenamento, sessao=sessao, agente=agente).confirmar(fio, conferencia, acontecendo_agora)
    assert armazenamento.notas(fio.id) == []
    assert agente.chamadas == 0
    assert sessao.houve_recente(instante) is False


@pytest.mark.parametrize("familia", [Familia.ALGUEM_EM_RISCO, Familia.SI_MESMA])
def test_quarto_voltar_recusa_origem_avaliar(armazenamento, fio, familia):
    agente = AgenteQueFala()
    encaminhamento = Encaminhamento(
        texto=NOTA_COMUM, instante=datetime.now(timezone.utc), oferece_retorno=True,
        familia=familia, origem="avaliar",
    )
    with pytest.raises(ValueError):
        Quarto(armazenamento, agente=agente).voltar(fio, encaminhamento)
    assert armazenamento.notas(fio.id) == []
    assert agente.chamadas == 0


def test_quarto_recusa_o_que_veio_da_porta_da_recepcao(armazenamento, fio):
    recepcao = Recepcao(armazenamento)
    quarto = Quarto(armazenamento)
    with pytest.raises(ValueError):
        quarto.confirmar(fio, recepcao.passar_pelo_portao("nao aguento mais esse relatorio"), False)
    with pytest.raises(ValueError):
        quarto.voltar(fio, recepcao.passar_pelo_portao("ela disse que quer morrer"))
    assert armazenamento.notas(fio.id) == []
