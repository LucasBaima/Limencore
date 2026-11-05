import dataclasses

import pytest

from conftest import despejo_com_fios
from limencore.agente.encaminhamento import Conferencia, Encaminhamento
from limencore.agente.quarto import (
    AgenteDoQuarto,
    AgenteSilencioso,
    Escrito,
    Quarto,
    RespostaDoQuarto,
)
from limencore.corte import Trecho
from limencore.fio import EstadoFio, Fio
from limencore.janela import Evento, JanelaDoFio
from limencore.nota import TipoNota

TEXTO = "o prazo do relatorio. a viagem de sabado"


class AgenteFixo:
    def __init__(self, texto, destacar_pouso=False):
        self.texto = texto
        self.destacar_pouso = destacar_pouso
        self.janelas = []

    def responder(self, janela):
        self.janelas.append(janela)
        return RespostaDoQuarto(texto=self.texto, destacar_pouso=self.destacar_pouso)


class AgenteQueFalha:
    def responder(self, janela):
        raise RuntimeError("agente quebrou")


@pytest.fixture
def dois_fios(banco):
    _, (a, b) = despejo_com_fios(banco, TEXTO, [(0, 20)], [(22, 40)], estado=EstadoFio.ESCOLHIDO)
    return a, b


class TestTipos:
    def test_frozen(self):
        r = RespostaDoQuarto(texto=None, destacar_pouso=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.texto = "x"
        j = JanelaDoFio(conteudo_do_despejo="x", trechos=(), eventos=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            j.trechos = ()

    def test_autoria_so_usuario_ou_agente(self, relogio):
        with pytest.raises(ValueError):
            Evento(autoria="outro", texto="x", instante=relogio.agora)

    def test_silencioso_cumpre_o_protocolo(self):
        assert isinstance(AgenteSilencioso(), AgenteDoQuarto)


class TestJanela:
    def test_so_do_fio(self, banco, dois_fios):
        a, b = dois_fios
        banco.escrever(a, "nota de a")
        banco.registrar_turno(a, "turno de a")
        banco.escrever(b, "nota do irmao")
        banco.registrar_turno(b, "turno do irmao")
        janela = banco.janela(a.id)
        assert janela.conteudo_do_despejo == TEXTO
        assert janela.trechos == (Trecho(0, 20),)
        assert [e.texto for e in janela.eventos] == ["nota de a", "turno de a"]

    def test_fio_inteiro_tem_trechos_vazios(self, banco):
        _, (fio,) = despejo_com_fios(banco, TEXTO)
        assert banco.janela(fio.id).trechos == ()

    def test_eventos_em_ordem_com_autoria(self, banco, relogio, dois_fios):
        a, _ = dois_fios
        banco.escrever(a, "um")
        relogio.andar(1)
        banco.registrar_turno(a, "dois")
        relogio.andar(1)
        banco.escrever(a, "tres")
        relogio.andar(1)
        banco.registrar_turno(a, "quatro")
        eventos = banco.janela(a.id).eventos
        assert [(e.autoria, e.texto) for e in eventos] == [
            ("usuario", "um"), ("agente", "dois"), ("usuario", "tres"), ("agente", "quatro"),
        ]
        assert [e.instante for e in eventos] == sorted(e.instante for e in eventos)

    def test_fio_inexistente(self, banco):
        with pytest.raises(ValueError):
            banco.janela(Fio(despejo_id="00000000-0000-4000-8000-000000000000").id)

    def test_sabe_de_qual_fio_e(self, banco, dois_fios):
        a, _ = dois_fios
        banco.marcar_assunto(a, "  Trabalho   do Mes ")
        janela = banco.janela(a.id)
        assert janela.fio_id == a.id
        assert janela.criado_em == a.criado_em
        assert janela.assunto == "Trabalho do Mes"

    def test_fio_sem_assunto(self, banco, dois_fios):
        a, _ = dois_fios
        assert banco.janela(a.id).assunto is None

    def test_so_os_tres_campos_antigos_continua_valido(self):
        j = JanelaDoFio("x", (), ())
        assert (j.fio_id, j.criado_em, j.assunto) == (None, None, None)

    def test_criado_em_sem_timezone(self):
        from datetime import datetime

        with pytest.raises(ValueError):
            JanelaDoFio("x", (), (), criado_em=datetime(2026, 1, 1))


class TestSombraSilenciosa:
    def test_sem_nota_nao_destaca(self, banco, dois_fios):
        a, _ = dois_fios
        assert AgenteSilencioso().responder(banco.janela(a.id)) == RespostaDoQuarto(None, False)

    def test_com_nota_destaca(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco).escrever(a, "falta a parte dos numeros")
        assert isinstance(resultado, Escrito)
        assert resultado.resposta == RespostaDoQuarto(texto=None, destacar_pouso=True)
        assert banco.turnos(a.id) == []

    def test_so_turno_nao_destaca(self, banco, dois_fios):
        a, _ = dois_fios
        banco.registrar_turno(a, "um turno")
        assert AgenteSilencioso().responder(banco.janela(a.id)).destacar_pouso is False


class TestAgentePlugado:
    def test_resposta_vira_turno(self, banco, dois_fios):
        a, _ = dois_fios
        agente = AgenteFixo("e o resto?", destacar_pouso=True)
        resultado = Quarto(banco, agente=agente).escrever(a, "falta a parte dos numeros")
        assert resultado.nota.texto == "falta a parte dos numeros"
        assert resultado.resposta == RespostaDoQuarto(texto="e o resto?", destacar_pouso=True)
        assert [t.texto for t in banco.turnos(a.id)] == ["e o resto?"]
        # o agente recebe a janela ja com a nota nova
        assert [e.texto for e in agente.janelas[0].eventos] == ["falta a parte dos numeros"]

    def test_confirmar_tambem_chama_o_agente(self, banco, dois_fios):
        a, _ = dois_fios
        quarto = Quarto(banco, agente=AgenteFixo("e o resto?"))
        conferencia = quarto.escrever(a, "nao aguento mais esse relatorio")
        assert isinstance(conferencia, Conferencia)
        resultado = quarto.confirmar(a, conferencia, False)
        assert isinstance(resultado, Escrito)
        assert [t.texto for t in banco.turnos(a.id)] == ["e o resto?"]

    def test_portao_antes_do_agente(self, banco, dois_fios):
        a, _ = dois_fios
        agente = AgenteFixo("e o resto?")
        resultado = Quarto(banco, agente=agente).escrever(a, "quero me matar")
        assert isinstance(resultado, Encaminhamento)
        assert agente.janelas == []
        assert banco.turnos(a.id) == []

    def test_agente_que_falha_nao_perde_a_nota(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco, agente=AgenteQueFalha()).escrever(a, "falta a parte dos numeros")
        # cai na sombra silenciosa: ha nota do usuario, entao destaca
        assert resultado.resposta == RespostaDoQuarto(texto=None, destacar_pouso=True)
        assert [n.texto for n in banco.notas(a.id)] == ["falta a parte dos numeros"]
        assert banco.turnos(a.id) == []


class TestGuardaDaCostura:
    @pytest.mark.parametrize(
        "resposta",
        [
            "voce disse: o prazo do relatorio.",
            "O   PRAZO do\nrelatorio. ok",
            "sobre 'falta a parte dos numeros', e ai?",
            "FALTA a parte   dos numeros",
        ],
    )
    def test_repete_trecho_ou_nota_e_recusado(self, banco, dois_fios, resposta):
        a, _ = dois_fios
        resultado = Quarto(banco, agente=AgenteFixo(resposta, True)).escrever(a, "falta a parte dos numeros")
        assert resultado.resposta == RespostaDoQuarto(texto=None, destacar_pouso=True)
        assert banco.turnos(a.id) == []

    def test_palavra_dentro_de_outra_nao_bloqueia(self, banco, relogio):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        resultado = Quarto(banco, agente=AgenteFixo("isso e normal")).escrever(fio, "mal")
        assert resultado.resposta.texto == "isso e normal"

    def test_nota_curta_nao_bloqueia_nada(self, banco):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        quarto = Quarto(banco, agente=AgenteFixo("não, não sei"))
        resultado = quarto.escrever(fio, "não")
        assert resultado.resposta.texto == "não, não sei"
        assert [t.texto for t in banco.turnos(fio.id)] == ["não, não sei"]

    def test_duas_palavras_repetidas_nao_bloqueiam(self, banco):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        resultado = Quarto(banco, agente=AgenteFixo("sobre o prazo, e ai?")).escrever(fio, "o prazo")
        assert resultado.resposta.texto == "sobre o prazo, e ai?"

    def test_nota_de_tres_palavras_nunca_barra_sozinha(self, banco):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        resultado = Quarto(banco, agente=AgenteFixo("hm: Falta, a PARTE!")).escrever(fio, "falta a parte")
        assert resultado.resposta.texto == "hm: Falta, a PARTE!"

    def test_quatro_palavras_seguidas_de_nota_longa_bloqueiam(self, banco):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        nota = "hoje de manha falta a parte dos numeros e eu nem comecei"
        resultado = Quarto(banco, agente=AgenteFixo("entao, FALTA a parte   dos?")).escrever(fio, nota)
        assert resultado.resposta.texto is None
        assert banco.turnos(fio.id) == []

    def test_tres_palavras_seguidas_de_nota_longa_passam(self, banco):
        _, (fio,) = despejo_com_fios(banco, "um despejo qualquer aqui", [(0, 2)], estado=EstadoFio.ESCOLHIDO)
        nota = "hoje de manha falta a parte dos numeros e eu nem comecei"
        resultado = Quarto(banco, agente=AgenteFixo("falta a parte: qual?")).escrever(fio, nota)
        assert resultado.resposta.texto == "falta a parte: qual?"

    def test_quatro_palavras_seguidas_de_trecho_longo_bloqueiam(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco, agente=AgenteFixo("e o prazo do relatorio?")).escrever(a, "uma nota")
        assert resultado.resposta.texto is None

    def test_palavras_fora_de_sequencia_nao_bloqueiam(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco, agente=AgenteFixo("a parte que falta")).escrever(a, "falta a parte")
        assert resultado.resposta.texto == "a parte que falta"

    def test_pedaco_do_irmao_nao_e_recusado(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco, agente=AgenteFixo("a viagem de sabado")).escrever(a, "uma nota")
        assert resultado.resposta.texto == "a viagem de sabado"

    def test_fio_inteiro_conta_o_despejo_todo(self, banco):
        _, (fio,) = despejo_com_fios(banco, TEXTO, estado=EstadoFio.ESCOLHIDO)
        resultado = Quarto(banco, agente=AgenteFixo("eco: " + TEXTO)).escrever(fio, "uma nota")
        assert resultado.resposta.texto is None
        assert banco.turnos(fio.id) == []


class TestPousoPeloPortao:
    def test_frase_que_segue_pousa(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco).pousar(a, "entrego a primeira parte hoje")
        assert isinstance(resultado, Fio)
        assert resultado.estado is EstadoFio.RESOLVIDO
        assert [(n.tipo, n.texto) for n in banco.notas(a.id)] == [(TipoNota.POUSO, "entrego a primeira parte hoje")]

    def test_frase_que_encaminha_nao_pousa(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco).pousar(a, "quero me matar")
        assert isinstance(resultado, Encaminhamento)
        assert banco.notas(a.id) == []
        assert banco.buscar_fios(a.despejo_id)[0].estado is EstadoFio.ESCOLHIDO

    def test_frase_ambigua_confere(self, banco, dois_fios):
        a, _ = dois_fios
        resultado = Quarto(banco).pousar(a, "nao aguento mais esse relatorio")
        assert isinstance(resultado, Conferencia)
        assert banco.notas(a.id) == []
        assert banco.buscar_fios(a.despejo_id)[0].estado is EstadoFio.ESCOLHIDO

    @pytest.mark.parametrize("frase", [None, "", "   "])
    def test_sem_frase_pousa_sem_nota(self, banco, dois_fios, frase):
        a, _ = dois_fios
        resultado = Quarto(banco).pousar(a, frase)
        assert resultado.estado is EstadoFio.RESOLVIDO
        assert banco.notas(a.id) == []


class TestConferenciaDoPouso:
    def test_carrega_a_origem(self, banco, dois_fios):
        a, _ = dois_fios
        quarto = Quarto(banco)
        assert quarto.escrever(a, "nao aguento mais esse relatorio").origem == "escrever"
        assert quarto.pousar(a, "nao aguento mais esse relatorio").origem == "pousar"

    def test_origem_invalida(self, relogio):
        with pytest.raises(ValueError):
            Conferencia(texto="x", instante=relogio.agora, origem="outra")

    def test_nao_e_agora_resolve_com_nota_de_pouso(self, banco, dois_fios):
        a, _ = dois_fios
        quarto = Quarto(banco, agente=AgenteFixo("e o resto?"))
        conferencia = quarto.pousar(a, "nao aguento mais esse relatorio")
        resultado = quarto.confirmar(a, conferencia, False)
        assert isinstance(resultado, Fio)
        assert resultado.estado is EstadoFio.RESOLVIDO
        assert [(n.tipo, n.texto) for n in banco.notas(a.id)] == [
            (TipoNota.POUSO, "nao aguento mais esse relatorio"),
        ]
        assert banco.turnos(a.id) == []

    def test_acontecendo_agora_encaminha_e_fio_segue_escolhido(self, banco, dois_fios):
        a, _ = dois_fios
        quarto = Quarto(banco)
        conferencia = quarto.pousar(a, "nao aguento mais esse relatorio")
        resultado = quarto.confirmar(a, conferencia, True)
        assert isinstance(resultado, Encaminhamento)
        assert banco.notas(a.id) == []
        assert banco.buscar_fios(a.despejo_id)[0].estado is EstadoFio.ESCOLHIDO

    def test_conferencia_da_entrada_e_recusada(self, banco, relogio, dois_fios):
        a, _ = dois_fios
        with pytest.raises(ValueError):
            Quarto(banco).confirmar(a, Conferencia(texto="x", instante=relogio.agora), False)
        assert banco.notas(a.id) == []


class TestRelogioDoPortao:
    def test_portao_usa_o_relogio_do_armazenamento(self, banco, relogio, dois_fios):
        a, _ = dois_fios
        quarto = Quarto(banco)
        assert quarto.escrever(a, "nao aguento mais esse relatorio").instante == relogio.agora
        relogio.andar(5)
        assert quarto.pousar(a, "quero me matar").instante == relogio.agora

    def test_agora_publico(self, banco, relogio):
        assert banco.agora() == relogio.agora
