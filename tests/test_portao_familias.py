from datetime import datetime, timezone

import pytest

from limencore.agente.encaminhamento import (
    ALVOS_PRONOMES,
    DETERMINANTES_DE_ALVO,
    INICIOS_DE_INTENCAO,
    INTENCOES_CONTRA_OUTROS,
    RELATOS_DE_RISCO_ALHEIO,
    VERBOS_CONTRA_OUTROS,
    Conferencia,
    DetectorComFamilia,
    DetectorComFamilias,
    DetectorPorExpressoes,
    Encaminhamento,
    Familia,
    Passagem,
    RegistroDaSessao,
)
from limencore.agente.quarto import Escrito, Quarto
from limencore.agente.recepcao import Recebido, Recepcao
from limencore.fio import EstadoFio

RISCO_ALHEIO = "ela disse que quer morrer"


def _avaliar(texto):
    return DetectorPorExpressoes().avaliar_com_familia(texto)


def _nada_salvo(armazenamento):
    assert armazenamento.listar() == []
    (n,) = armazenamento._conexao.execute("SELECT COUNT(*) FROM fios").fetchone()
    assert n == 0


@pytest.fixture
def fio(banco):
    (fio,) = Recepcao(banco).receber("o prazo do relatorio").fios
    return banco.atualizar_estado(fio, EstadoFio.ESCOLHIDO)


class DetectorSoAvaliar:  # detector antigo: so avaliar()
    def __init__(self, passagem):
        self.passagem = passagem

    def avaliar(self, texto):
        return self.passagem


class DetectorFixo:  # devolve sempre a mesma passagem e familia
    def __init__(self, passagem, familia):
        self.resposta = (passagem, familia)

    def avaliar(self, texto):
        return self.resposta[0]

    def avaliar_com_familia(self, texto):
        return self.resposta


# --- detector -------------------------------------------------------------


def test_detector_padrao_cumpre_a_costura_com_familia():
    assert isinstance(DetectorPorExpressoes(), DetectorComFamilia)


def test_familia_padrao_dos_objetos_e_si_mesma():
    agora = datetime.now(timezone.utc)
    assert Conferencia(texto="x", instante=agora).familia is Familia.SI_MESMA
    assert Encaminhamento(texto="x", instante=agora, oferece_retorno=True).familia is Familia.SI_MESMA


@pytest.mark.parametrize(
    "texto",
    ["meu chefe é um idiota", "odeio ela", "que vontade de esganar esse cara", "vou matar aula"],
)
def test_xingamento_e_raiva_nao_disparam(texto):
    assert _avaliar(texto) == (Passagem.SEGUIR, Familia.SI_MESMA)


def test_ameaca_de_raiva_no_maximo_confere():
    passagem, _ = _avaliar("vou matar meu chefe se ele mandar outro e-mail")
    assert passagem is not Passagem.ENCAMINHAR


@pytest.mark.parametrize("inicio", INICIOS_DE_INTENCAO)
@pytest.mark.parametrize("verbo", VERBOS_CONTRA_OUTROS)
@pytest.mark.parametrize("alvo", [*ALVOS_PRONOMES, *(f"{d} vizinho" for d in DETERMINANTES_DE_ALVO), "Carlos"])
def test_intencao_sem_plano_confere(inicio, verbo, alvo):
    texto = f"as vezes {inicio} {verbo} {alvo}, sabe"
    assert _avaliar(texto) == (Passagem.CONFERIR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize("expressao", INTENCOES_CONTRA_OUTROS)
def test_frases_em_ingles_conferem(expressao):
    assert _avaliar(f"sometimes {expressao}") == (Passagem.CONFERIR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize(
    "texto",
    ["vou matar meu chefe", "quero machucar minha mãe", "Tô pensando em bater em Joana", "vou matar o Pedro"],
)
def test_alvo_aberto_confere(texto):
    assert _avaliar(texto) == (Passagem.CONFERIR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize("texto", ["vou matar ele de rir", "vou matar meu chefe de rir", "vou matar joana"])
def test_figurado_ou_sem_alvo_segue(texto):
    assert _avaliar(texto) == (Passagem.SEGUIR, Familia.SI_MESMA)


def test_alvo_aberto_com_meio_encaminha():
    assert _avaliar("vou matar meu marido, tenho uma arma") == (Passagem.ENCAMINHAR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize(
    "texto",
    ["vou matar ele de raiva. amanha tenho reuniao", "quero matar ela!\nhoje à noite tem jogo", "vou matar ele; a faca"],
)
def test_plano_em_outra_frase_so_confere(texto):
    assert _avaliar(texto) == (Passagem.CONFERIR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize(
    "texto",
    [
        "vou matar ele hoje à noite", "quero matar ela, já planejei tudo",
        "vou machucar ele com uma faca", "quero matar alguem, tenho uma arma",
        "Vou ESFAQUEAR ele amanhã", "i want to kill him tonight",
    ],
)
def test_intencao_com_plano_ou_meio_encaminha(texto):
    assert _avaliar(texto) == (Passagem.ENCAMINHAR, Familia.MACHUCAR_ALGUEM)


@pytest.mark.parametrize("texto", ["hoje à noite eu vou ao cinema", "comprei uma faca nova"])
def test_plano_sem_intencao_segue(texto):
    assert _avaliar(texto) == (Passagem.SEGUIR, Familia.SI_MESMA)


@pytest.mark.parametrize("expressao", RELATOS_DE_RISCO_ALHEIO)
def test_cada_relato_de_risco_alheio_encaminha(expressao):
    assert _avaliar(f"hoje {expressao}, fiquei preocupado") == (Passagem.ENCAMINHAR, Familia.ALGUEM_EM_RISCO)


@pytest.mark.parametrize(
    "texto",
    ["Ela disse que quer MORRER", "meu amigo falou em se matar", "minha irmã tentou suicídio"],
)
def test_relato_de_terceiro_encaminha_como_alguem_em_risco(texto):
    assert _avaliar(texto) == (Passagem.ENCAMINHAR, Familia.ALGUEM_EM_RISCO)


def test_relato_figurado_de_terceiro_segue():
    assert _avaliar("ela disse que quer morrer de vergonha") == (Passagem.SEGUIR, Familia.SI_MESMA)


@pytest.mark.parametrize(
    "texto, passagem",
    [
        ("ela disse que quer morrer e eu quero me matar", Passagem.ENCAMINHAR),
        ("meu amigo falou em se matar e eu nao aguento mais", Passagem.ENCAMINHAR),
    ],
)
def test_prioridade_propria_pessoa_vence_terceiro(texto, passagem):
    assert _avaliar(texto) == (passagem, Familia.SI_MESMA)


def test_prioridade_machucar_alguem_vence_terceiro():
    assert _avaliar("ela disse que quer morrer e eu vou matar ele") == (
        Passagem.ENCAMINHAR, Familia.MACHUCAR_ALGUEM,
    )


def test_prioridade_propria_pessoa_vence_machucar_alguem():
    assert _avaliar("quero matar ele e depois me matar") == (Passagem.CONFERIR, Familia.SI_MESMA)


MISTO = "minha amiga disse que quer morrer, nao aguento mais"


def test_detector_padrao_cumpre_a_costura_com_familias():
    assert isinstance(DetectorPorExpressoes(), DetectorComFamilias)


def test_caso_misto_diz_as_outras_familias():
    detector = DetectorPorExpressoes()
    assert detector.avaliar_com_familias(MISTO) == (Passagem.ENCAMINHAR, Familia.SI_MESMA, (Familia.ALGUEM_EM_RISCO,))
    assert detector.avaliar_com_familia(MISTO) == (Passagem.ENCAMINHAR, Familia.SI_MESMA)


def test_outras_familias_em_ordem_de_prioridade():
    texto = "quero me matar, vou matar ele e ela disse que quer morrer"
    assert DetectorPorExpressoes().avaliar_com_familias(texto) == (
        Passagem.ENCAMINHAR, Familia.SI_MESMA, (Familia.MACHUCAR_ALGUEM, Familia.ALGUEM_EM_RISCO),
    )


def test_uma_familia_so_nao_tem_outras():
    assert DetectorPorExpressoes().avaliar_com_familias(RISCO_ALHEIO)[2] == ()
    assert DetectorPorExpressoes().avaliar_com_familias("o prazo") == (Passagem.SEGUIR, Familia.SI_MESMA, ())


def test_outras_familias_padrao_vazio():
    agora = datetime.now(timezone.utc)
    assert Conferencia(texto="x", instante=agora).outras_familias == ()
    assert Encaminhamento(texto="x", instante=agora, oferece_retorno=True).outras_familias == ()


def test_avaliar_continua_devolvendo_so_a_passagem():
    assert DetectorPorExpressoes().avaliar("vou matar ele hoje a noite") is Passagem.ENCAMINHAR
    assert DetectorPorExpressoes().avaliar("quero me matar") is Passagem.ENCAMINHAR


def test_listas_novas_vazias_desligam_as_familias():
    detector = DetectorPorExpressoes(inicios=(), contra_outros=(), planos=(), risco_alheio=())
    assert detector.avaliar_com_familia("vou matar ele hoje a noite") == (Passagem.SEGUIR, Familia.SI_MESMA)
    assert detector.avaliar_com_familia(RISCO_ALHEIO) == (Passagem.CONFERIR, Familia.SI_MESMA)


# --- recepcao (entrada) ---------------------------------------------------


def test_entrada_detector_so_com_avaliar_sai_si_mesma(banco):
    resultado = Recepcao(banco, detector=DetectorSoAvaliar(Passagem.ENCAMINHAR)).receber("x")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.SI_MESMA
    conferencia = Recepcao(banco, detector=DetectorSoAvaliar(Passagem.CONFERIR)).receber("x")
    assert isinstance(conferencia, Conferencia) and conferencia.familia is Familia.SI_MESMA


def test_entrada_machucar_alguem_encaminha_com_familia(banco):
    resultado = Recepcao(banco).receber("vou matar ele hoje à noite")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.MACHUCAR_ALGUEM
    assert resultado.oferece_retorno is True
    _nada_salvo(banco)


def test_entrada_machucar_alguem_marca_a_sessao(banco):
    recepcao = Recepcao(banco)
    recepcao.receber("vou matar ele hoje à noite", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    segundo = recepcao.receber("quero sumir", instante=datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    assert isinstance(segundo, Encaminhamento) and segundo.oferece_retorno is False


def test_entrada_conferencia_carrega_familia(banco):
    resultado = Recepcao(banco).receber("quero matar ele")
    assert isinstance(resultado, Conferencia)
    assert resultado.familia is Familia.MACHUCAR_ALGUEM
    encaminhado = Recepcao(banco).confirmar(resultado, True)
    assert encaminhado.familia is Familia.MACHUCAR_ALGUEM


def test_entrada_alguem_em_risco_encaminha_com_retorno_e_nada_salvo(banco):
    resultado = Recepcao(banco).receber(RISCO_ALHEIO)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.ALGUEM_EM_RISCO
    assert resultado.oferece_retorno is True
    _nada_salvo(banco)


def test_entrada_alguem_em_risco_tem_retorno_mesmo_com_sessao_recente(banco):
    recepcao = Recepcao(banco)
    recepcao.receber("quero me matar", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    resultado = recepcao.receber(RISCO_ALHEIO, instante=datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    assert resultado.familia is Familia.ALGUEM_EM_RISCO
    assert resultado.oferece_retorno is True


def test_entrada_alguem_em_risco_nao_marca_a_sessao(banco):
    sessao = RegistroDaSessao()
    recepcao = Recepcao(banco, sessao=sessao)
    recepcao.receber(RISCO_ALHEIO, instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    assert not sessao.houve_recente(datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    seguinte = recepcao.receber("quero sumir", instante=datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    assert isinstance(seguinte, Conferencia)


def test_entrada_voltar_de_alguem_em_risco_segue_o_fluxo_normal(banco):
    recepcao = Recepcao(banco, detector=DetectorFixo(Passagem.ENCAMINHAR, Familia.ALGUEM_EM_RISCO))
    encaminhamento = recepcao.receber(RISCO_ALHEIO)
    recebido = recepcao.voltar(encaminhamento)
    assert isinstance(recebido, Recebido)
    (despejo,) = banco.listar()
    assert despejo.conteudo == RISCO_ALHEIO
    assert despejo.instante == encaminhamento.instante


@pytest.mark.parametrize("familia", [Familia.SI_MESMA, Familia.MACHUCAR_ALGUEM])
def test_entrada_sem_volta_para_as_outras_familias(banco, familia):
    encaminhamento = Encaminhamento(
        texto="x", instante=datetime.now(timezone.utc), oferece_retorno=True, familia=familia
    )
    with pytest.raises(ValueError):
        Recepcao(banco).voltar(encaminhamento)
    _nada_salvo(banco)


def test_entrada_repassa_outras_familias(banco):
    resultado = Recepcao(banco).receber(MISTO)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.SI_MESMA
    assert resultado.outras_familias == (Familia.ALGUEM_EM_RISCO,)


def test_entrada_conferencia_repassa_outras_familias_ate_o_encaminhamento(banco):
    recepcao = Recepcao(banco)
    conferencia = recepcao.receber("quero matar ele e depois me matar")
    assert isinstance(conferencia, Conferencia)
    assert (conferencia.familia, conferencia.outras_familias) == (Familia.SI_MESMA, (Familia.MACHUCAR_ALGUEM,))
    encaminhado = recepcao.confirmar(conferencia, True)
    assert encaminhado.outras_familias == (Familia.MACHUCAR_ALGUEM,)


def test_entrada_detector_so_com_familia_sai_sem_outras(banco):
    resultado = Recepcao(banco, detector=DetectorFixo(Passagem.ENCAMINHAR, Familia.MACHUCAR_ALGUEM)).receber("x")
    assert (resultado.familia, resultado.outras_familias) == (Familia.MACHUCAR_ALGUEM, ())


def test_entrada_outras_familias_invalidas_encaminham(banco):
    class DetectorOutrasInvalidas(DetectorFixo):
        def avaliar_com_familias(self, texto):
            return Passagem.SEGUIR, Familia.SI_MESMA, ("outra",)

    resultado = Recepcao(banco, detector=DetectorOutrasInvalidas(Passagem.SEGUIR, Familia.SI_MESMA)).receber("o prazo")
    assert isinstance(resultado, Encaminhamento)
    assert (resultado.familia, resultado.outras_familias) == (Familia.SI_MESMA, ())


def test_entrada_detector_com_familia_invalida_encaminha(banco):
    resultado = Recepcao(banco, detector=DetectorFixo(Passagem.SEGUIR, "outra")).receber("o prazo")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.SI_MESMA


# --- quarto ---------------------------------------------------------------


def test_quarto_detector_so_com_avaliar_sai_si_mesma(banco, fio):
    resultado = Quarto(banco, DetectorSoAvaliar(Passagem.ENCAMINHAR)).escrever(fio, "x")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.SI_MESMA
    assert Quarto(banco, DetectorSoAvaliar(Passagem.SEGUIR)).escrever(fio, "falta a parte dos numeros")


def test_quarto_machucar_alguem_encaminha_com_familia(banco, fio):
    resultado = Quarto(banco).escrever(fio, "quero matar ela, já planejei tudo")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.MACHUCAR_ALGUEM
    assert banco.notas(fio.id) == []


def test_quarto_conferencia_carrega_familia(banco, fio):
    quarto = Quarto(banco)
    conferencia = quarto.escrever(fio, "quero machucar ele")
    assert isinstance(conferencia, Conferencia) and conferencia.familia is Familia.MACHUCAR_ALGUEM
    assert quarto.confirmar(fio, conferencia, True).familia is Familia.MACHUCAR_ALGUEM


def test_quarto_repassa_outras_familias(banco, fio):
    resultado = Quarto(banco).escrever(fio, MISTO)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.outras_familias == (Familia.ALGUEM_EM_RISCO,)
    conferencia = Quarto(banco).pousar(fio, "quero matar ele e depois me matar")
    assert isinstance(conferencia, Conferencia)
    assert conferencia.outras_familias == (Familia.MACHUCAR_ALGUEM,)


def test_quarto_alguem_em_risco_encaminha_com_retorno(banco, fio):
    sessao = RegistroDaSessao()
    Recepcao(banco, sessao=sessao).receber("quero me matar", instante=banco.agora())
    resultado = Quarto(banco, sessao=sessao).escrever(fio, "meu amigo falou em se matar")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.familia is Familia.ALGUEM_EM_RISCO
    assert resultado.oferece_retorno is True
    assert resultado.origem == "escrever"
    assert banco.notas(fio.id) == []


def test_quarto_voltar_de_alguem_em_risco_grava_a_nota(banco, fio):
    quarto = Quarto(banco)
    encaminhamento = quarto.escrever(fio, "meu amigo falou em se matar")
    resultado = quarto.voltar(fio, encaminhamento)
    assert isinstance(resultado, Escrito)
    assert [n.texto for n in banco.notas(fio.id)] == ["meu amigo falou em se matar"]


def test_quarto_voltar_de_alguem_em_risco_pousa(banco, fio):
    quarto = Quarto(banco)
    encaminhamento = quarto.pousar(fio, RISCO_ALHEIO)
    assert isinstance(encaminhamento, Encaminhamento) and encaminhamento.origem == "pousar"
    pousado = quarto.voltar(fio, encaminhamento)
    assert pousado.estado is EstadoFio.RESOLVIDO


def test_quarto_sem_volta_para_si_mesma(banco, fio):
    encaminhamento = Quarto(banco).escrever(fio, "quero me matar")
    with pytest.raises(ValueError):
        Quarto(banco).voltar(fio, encaminhamento)
    assert banco.notas(fio.id) == []
