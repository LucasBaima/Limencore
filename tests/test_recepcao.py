from datetime import datetime, timezone

import pytest

from limencore.agente.encaminhamento import Conferencia, Encaminhamento, Familia, Passagem, RegistroDaSessao
from limencore.agente.movimento import Forma, Movimento
from limencore.agente.recepcao import Recebido, Recepcao
from limencore.corte import Corte, FioPlanejado, Trecho, recortar
from limencore.fio import EstadoFio
from limencore.storage import Armazenamento


class SeletorEspiao:
    def __init__(self):
        self.recebidos = []

    def selecionar(self, entry):
        self.recebidos.append(entry)
        return Movimento(forma=Forma.UM_SO, alvos=(entry.id,))


class SeletorQueFalha:
    def selecionar(self, entry):
        raise RuntimeError("seletor quebrou")


class SeletorDividir:
    def selecionar(self, entry):
        return Movimento(forma=Forma.DIVIDIR, alvos=(entry.id,))


@pytest.fixture
def armazenamento():
    a = Armazenamento(":memory:")
    yield a
    a.fechar()


def test_receber_grava_despejo_fio_e_nascimento(armazenamento):
    recebido = Recepcao(armazenamento).receber("um pensamento")
    despejos = armazenamento.listar()
    assert len(despejos) == 1
    assert despejos[0].conteudo == "um pensamento"
    fios = armazenamento.buscar_fios(despejos[0].id)
    assert len(fios) == 1
    assert fios[0].estado is EstadoFio.JOGADO
    assert fios[0].id == recebido.fios[0].id
    historico = armazenamento.historico(fios[0].id)
    assert len(historico) == 1
    assert historico[0].de is None
    assert historico[0].para is EstadoFio.JOGADO


def test_devolve_recebido_com_movimento_um_so(armazenamento):
    recebido = Recepcao(armazenamento).receber("um pensamento")
    assert isinstance(recebido, Recebido)
    assert recebido.movimento.forma is Forma.UM_SO
    assert recebido.movimento.alvos == (recebido.despejo.id,)


def test_seletor_recebe_o_mesmo_despejo_salvo(armazenamento):
    espiao = SeletorEspiao()
    recebido = Recepcao(armazenamento, espiao).receber("espiado")
    assert espiao.recebidos == [recebido.despejo]
    assert espiao.recebidos[0] is recebido.despejo
    assert armazenamento.listar()[0].id == espiao.recebidos[0].id


def test_seletor_que_falha_nao_perde_o_despejo(armazenamento):
    recebido = Recepcao(armazenamento, SeletorQueFalha()).receber("salvo mesmo assim")
    assert recebido.movimento.forma is Forma.UM_SO
    assert recebido.movimento.alvos == (recebido.despejo.id,)
    assert [d.id for d in armazenamento.listar()] == [recebido.despejo.id]
    assert len(armazenamento.buscar_fios(recebido.despejo.id)) == 1
    assert len(recebido.fios) == 1


def test_seletor_dividir_ainda_cria_um_fio(armazenamento):
    recebido = Recepcao(armazenamento, SeletorDividir()).receber("varios misturados")
    assert recebido.movimento.forma is Forma.DIVIDIR
    assert len(recebido.fios) == 1
    assert len(armazenamento.buscar_fios(recebido.despejo.id)) == 1


def test_texto_vazio_levanta_e_nao_grava(armazenamento):
    with pytest.raises(ValueError):
        Recepcao(armazenamento).receber("   ")
    assert armazenamento.listar() == []


def test_instante_explicito_e_respeitado(armazenamento):
    instante = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    recebido = Recepcao(armazenamento).receber("com hora", instante=instante)
    assert recebido.despejo.instante == instante
    assert armazenamento.listar()[0].instante == instante


class DetectorQueFalha:
    def avaliar(self, texto):
        raise RuntimeError("detector quebrou")


class DetectorNunca:
    def avaliar(self, texto):
        return Passagem.SEGUIR


def _nada_salvo(armazenamento):
    assert armazenamento.listar() == []
    assert armazenamento.mesa() == []
    (n,) = armazenamento._conexao.execute("SELECT COUNT(*) FROM fios").fetchone()
    assert n == 0


def test_explicito_encaminha_sem_salvar(armazenamento):
    espiao = SeletorEspiao()
    resultado = Recepcao(armazenamento, espiao).receber("quero me matar")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    assert resultado.texto == "quero me matar"
    _nada_salvo(armazenamento)
    assert espiao.recebidos == []


def test_ambiguo_confere_sem_salvar(armazenamento):
    espiao = SeletorEspiao()
    instante = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    resultado = Recepcao(armazenamento, espiao).receber("quero sumir", instante=instante)
    assert resultado == Conferencia(texto="quero sumir", instante=instante)
    _nada_salvo(armazenamento)
    assert espiao.recebidos == []


def test_confirmar_falso_segue_com_texto_e_instante_originais(armazenamento):
    recepcao = Recepcao(armazenamento)
    instante = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    conferencia = recepcao.receber("esse prazo vai me matar", instante=instante)
    resultado = recepcao.confirmar(conferencia, False)
    assert isinstance(resultado, Recebido)
    (despejo,) = armazenamento.listar()
    assert despejo.conteudo == "esse prazo vai me matar"
    assert despejo.instante == instante
    assert len(armazenamento.buscar_fios(despejo.id)) == 1


def test_confirmar_falso_nao_roda_o_detector_de_novo(armazenamento):
    recepcao = Recepcao(armazenamento, detector=DetectorQueFalha())
    conferencia = Conferencia(texto="quero sumir", instante=datetime.now(timezone.utc))
    assert isinstance(recepcao.confirmar(conferencia, False), Recebido)


def test_confirmar_verdadeiro_encaminha_sem_salvar(armazenamento):
    recepcao = Recepcao(armazenamento)
    conferencia = recepcao.receber("quero sumir")
    resultado = recepcao.confirmar(conferencia, True)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    _nada_salvo(armazenamento)


def test_reincidencia_encaminha_sem_retorno(armazenamento):
    sessao = RegistroDaSessao()
    recepcao = Recepcao(armazenamento, sessao=sessao)
    primeiro = recepcao.receber("quero me matar", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    segundo = recepcao.receber("quero sumir", instante=datetime(2026, 1, 2, 10, 10, tzinfo=timezone.utc))
    assert isinstance(primeiro, Encaminhamento) and primeiro.oferece_retorno is True
    assert isinstance(segundo, Encaminhamento)
    assert segundo.oferece_retorno is False
    _nada_salvo(armazenamento)


def test_reincidencia_nao_afeta_texto_neutro(armazenamento):
    recepcao = Recepcao(armazenamento)
    recepcao.receber("quero me matar", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    resultado = recepcao.receber("o prazo", instante=datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    assert isinstance(resultado, Recebido)


def test_detector_que_falha_encaminha(armazenamento):
    resultado = Recepcao(armazenamento, detector=DetectorQueFalha()).receber("um pensamento")
    assert isinstance(resultado, Encaminhamento)
    _nada_salvo(armazenamento)


def test_detector_injetado_substitui_o_padrao(armazenamento):
    resultado = Recepcao(armazenamento, detector=DetectorNunca()).receber("quero me matar")
    assert isinstance(resultado, Recebido)
    assert len(resultado.fios) == 1
    assert len(armazenamento.buscar_fios(resultado.despejo.id)) == 1


class SeletorComCorte:
    def __init__(self, forma, fios):
        self.forma = forma
        self.fios = fios

    def selecionar(self, entry):
        corte = Corte(fios=tuple(FioPlanejado(trechos=tuple(Trecho(i, f) for i, f in g)) for g in self.fios))
        return Movimento(forma=self.forma, alvos=(entry.id,), corte=corte)


def test_corte_de_tres_fios_planejados_cria_tres_fios(armazenamento):
    texto = "primeiro. segundo. terceiro."
    seletor = SeletorComCorte(Forma.DIVIDIR, [[(0, 9)], [(10, 18)], [(19, 28)]])
    recebido = Recepcao(armazenamento, seletor).receber(texto)
    assert [f.trechos for f in recebido.fios] == [
        (Trecho(0, 9),),
        (Trecho(10, 18),),
        (Trecho(19, 28),),
    ]
    assert [recortar(texto, f.trechos[0]) for f in recebido.fios] == ["primeiro.", "segundo.", "terceiro."]
    salvos = {f.id: f.trechos for f in armazenamento.buscar_fios(recebido.despejo.id)}
    assert salvos == {f.id: f.trechos for f in recebido.fios}


def test_corte_de_um_fio_planejado_com_dois_trechos_cria_um_fio(armazenamento):
    texto = "isto, aquilo, e isto de novo"
    seletor = SeletorComCorte(Forma.LIGAR, [[(0, 4), (16, 28)]])
    recebido = Recepcao(armazenamento, seletor).receber(texto)
    (fio,) = recebido.fios
    assert fio.trechos == (Trecho(0, 4), Trecho(16, 28))
    (salvo,) = armazenamento.buscar_fios(recebido.despejo.id)
    assert salvo.trechos == fio.trechos


@pytest.mark.parametrize("fios", [[[(0, 3)], [(4, 99)]], [[(0, 3)], [(3, 6)]]])
def test_corte_invalido_cai_em_um_fio_e_salva(armazenamento, fios):
    recebido = Recepcao(armazenamento, SeletorComCorte(Forma.DIVIDIR, fios)).receber("abc   def")
    (fio,) = recebido.fios
    assert fio.trechos == ()
    assert [d.id for d in armazenamento.listar()] == [recebido.despejo.id]
    (salvo,) = armazenamento.buscar_fios(recebido.despejo.id)
    assert salvo.id == fio.id and salvo.trechos == ()


def test_seletor_sem_corte_continua_um_fio_inteiro(armazenamento):
    recebido = Recepcao(armazenamento, SeletorDividir()).receber("varios misturados")
    (fio,) = recebido.fios
    assert fio.trechos == ()
    assert armazenamento.buscar_fios(recebido.despejo.id)[0].trechos == ()


# --- passar_pelo_portao: as regras do receber, sem gravar nada ---

AS_10 = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
AS_10_10 = datetime(2026, 1, 2, 10, 10, tzinfo=timezone.utc)
NEUTRO = "o prazo do relatorio"
AMBIGUO = "quero sumir"
SI_MESMA = "quero me matar"
RISCO_ALHEIO = "ela disse que quer morrer"


def test_porta_texto_que_segue_devolve_none(armazenamento):
    espiao = SeletorEspiao()
    assert Recepcao(armazenamento, espiao).passar_pelo_portao(NEUTRO) is None
    assert espiao.recebidos == []
    _nada_salvo(armazenamento)


def test_porta_texto_ambiguo_confere(armazenamento):
    resultado = Recepcao(armazenamento).passar_pelo_portao(AMBIGUO, instante=AS_10)
    assert resultado == Conferencia(texto=AMBIGUO, instante=AS_10, origem="avaliar")
    _nada_salvo(armazenamento)


@pytest.mark.parametrize(
    "texto,familia", [(SI_MESMA, Familia.SI_MESMA), (RISCO_ALHEIO, Familia.ALGUEM_EM_RISCO)]
)
def test_porta_encaminha_com_a_familia_certa(armazenamento, texto, familia):
    resultado = Recepcao(armazenamento).passar_pelo_portao(texto, instante=AS_10)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.origem == "avaliar"
    assert resultado.familia is familia
    assert resultado.oferece_retorno is True
    assert (resultado.texto, resultado.instante) == (texto, AS_10)
    _nada_salvo(armazenamento)


def test_porta_detector_que_falha_encaminha(armazenamento):
    resultado = Recepcao(armazenamento, detector=DetectorQueFalha()).passar_pelo_portao(NEUTRO)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.origem == "avaliar"
    _nada_salvo(armazenamento)


def test_porta_recusa_texto_vazio_como_o_receber(armazenamento):
    with pytest.raises(ValueError):
        Recepcao(armazenamento).passar_pelo_portao("   ")
    _nada_salvo(armazenamento)


def test_porta_sem_instante_usa_o_agora_com_timezone(armazenamento):
    resultado = Recepcao(armazenamento).passar_pelo_portao(AMBIGUO)
    assert resultado.instante.tzinfo is not None


def test_encaminhamento_pela_porta_marca_a_sessao_do_receber(armazenamento):
    recepcao = Recepcao(armazenamento)
    assert recepcao.passar_pelo_portao(SI_MESMA, instante=AS_10).oferece_retorno is True
    resultado = recepcao.receber(AMBIGUO, instante=AS_10_10)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is False
    assert resultado.origem is None
    _nada_salvo(armazenamento)


def test_encaminhamento_pelo_receber_marca_a_sessao_da_porta(armazenamento):
    recepcao = Recepcao(armazenamento)
    recepcao.receber(SI_MESMA, instante=AS_10)
    resultado = recepcao.passar_pelo_portao(AMBIGUO, instante=AS_10_10)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is False
    assert resultado.origem == "avaliar"
    _nada_salvo(armazenamento)


def test_risco_de_terceiro_pela_porta_nao_marca_a_sessao(armazenamento):
    sessao = RegistroDaSessao()
    recepcao = Recepcao(armazenamento, sessao=sessao)
    recepcao.passar_pelo_portao(RISCO_ALHEIO, instante=AS_10)
    assert sessao.houve_recente(AS_10_10) is False
    assert isinstance(recepcao.receber(AMBIGUO, instante=AS_10_10), Conferencia)


def test_sessao_marcada_nao_afeta_texto_neutro_na_porta(armazenamento):
    recepcao = Recepcao(armazenamento)
    recepcao.passar_pelo_portao(SI_MESMA, instante=AS_10)
    assert recepcao.passar_pelo_portao(NEUTRO, instante=AS_10_10) is None


# --- origem "avaliar": incapaz de gravar ---


def test_confirmar_avaliar_falso_devolve_none_sem_gravar(armazenamento):
    espiao = SeletorEspiao()
    sessao = RegistroDaSessao()
    recepcao = Recepcao(armazenamento, espiao, sessao=sessao)
    conferencia = recepcao.passar_pelo_portao(AMBIGUO, instante=AS_10)
    assert recepcao.confirmar(conferencia, False) is None
    assert espiao.recebidos == []
    assert sessao.houve_recente(AS_10) is False
    _nada_salvo(armazenamento)


def test_confirmar_avaliar_verdadeiro_encaminha_e_marca_a_sessao(armazenamento):
    sessao = RegistroDaSessao()
    recepcao = Recepcao(armazenamento, sessao=sessao)
    conferencia = recepcao.passar_pelo_portao(AMBIGUO, instante=AS_10)
    resultado = recepcao.confirmar(conferencia, True)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.origem == "avaliar"
    assert resultado.oferece_retorno is True
    assert sessao.houve_recente(AS_10) is True
    _nada_salvo(armazenamento)


def test_confirmar_avaliar_verdadeiro_com_sessao_marcada_nao_oferece_retorno(armazenamento):
    recepcao = Recepcao(armazenamento)
    conferencia = Conferencia(texto=AMBIGUO, instante=AS_10_10, origem="avaliar")
    recepcao.receber(SI_MESMA, instante=AS_10)
    resultado = recepcao.confirmar(conferencia, True)
    assert resultado.oferece_retorno is False
    assert resultado.origem == "avaliar"


def test_confirmar_avaliar_de_risco_de_terceiro_nao_marca_a_sessao(armazenamento):
    sessao = RegistroDaSessao()
    conferencia = Conferencia(texto=AMBIGUO, instante=AS_10, origem="avaliar", familia=Familia.ALGUEM_EM_RISCO)
    resultado = Recepcao(armazenamento, sessao=sessao).confirmar(conferencia, True)
    assert resultado.origem == "avaliar"
    assert sessao.houve_recente(AS_10) is False


@pytest.mark.parametrize("familia", [Familia.ALGUEM_EM_RISCO, Familia.SI_MESMA])
def test_voltar_avaliar_recusa_sem_gravar(armazenamento, familia):
    encaminhamento = Encaminhamento(
        texto=RISCO_ALHEIO, instante=AS_10, oferece_retorno=True, familia=familia, origem="avaliar"
    )
    with pytest.raises(ValueError):
        Recepcao(armazenamento).voltar(encaminhamento)
    _nada_salvo(armazenamento)


def test_voltar_avaliar_vindo_da_porta_recusa_sem_gravar(armazenamento):
    recepcao = Recepcao(armazenamento)
    encaminhamento = recepcao.passar_pelo_portao(RISCO_ALHEIO)
    with pytest.raises(ValueError):
        recepcao.voltar(encaminhamento)
    _nada_salvo(armazenamento)


def test_confirmar_de_outra_origem_nao_muda(armazenamento):
    # so "avaliar" muda o confirmar: as demais continuam gravando e encaminhando sem origem
    recepcao = Recepcao(armazenamento)
    conferencia = Conferencia(texto=AMBIGUO, instante=AS_10, origem="escrever")
    assert recepcao.confirmar(conferencia, True).origem is None
    assert isinstance(recepcao.confirmar(conferencia, False), Recebido)
