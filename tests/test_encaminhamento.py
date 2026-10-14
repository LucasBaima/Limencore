from datetime import datetime, timezone

import pytest

from limencore.agente.encaminhamento import (
    EXPRESSOES_EXPLICITAS,
    DetectorDeEncaminhamento,
    DetectorPorExpressoes,
    Passagem,
    RegistroDaSessao,
)


def test_detector_padrao_cumpre_a_costura():
    assert isinstance(DetectorPorExpressoes(), DetectorDeEncaminhamento)


@pytest.mark.parametrize("expressao", EXPRESSOES_EXPLICITAS)
def test_cada_expressao_explicita_encaminha(expressao):
    assert DetectorPorExpressoes().avaliar(f"hoje eu pensei: {expressao}, de novo") is Passagem.ENCAMINHAR


@pytest.mark.parametrize("texto", ["Penso em SUICÍDIO", "NÃO QUERO MAIS VIVER"])
def test_acento_e_maiusculas_encaminham(texto):
    assert DetectorPorExpressoes().avaliar(texto) is Passagem.ENCAMINHAR


@pytest.mark.parametrize(
    "texto",
    [
        "esse prazo vai me matar", "nao aguento mais", "quero morrer", "Quero SUMIR", "não aguento mais",
        "vou me matar com essa situação", "seria melhor se eu não existisse", "não vejo futuro para mim",
    ],
)
def test_ambiguos_conferem(texto):
    assert DetectorPorExpressoes().avaliar(texto) is Passagem.CONFERIR


@pytest.mark.parametrize(
    "texto",
    [
        "vou me matar de estudar", "morri de rir", "estou morrendo de sono", "o prazo do relatorio",
        "quero largar tudo", "estou farto de tudo", "morri de tanto rir", "quero sumir por uns dias",
    ],
)
def test_figurados_e_neutros_seguem(texto):
    assert DetectorPorExpressoes().avaliar(texto) is Passagem.SEGUIR


def test_explicita_vence_ambiguo():
    assert DetectorPorExpressoes().avaliar("quero me matar") is Passagem.ENCAMINHAR


@pytest.mark.parametrize("texto", ["suicidios", "me matarem"])
def test_so_palavra_inteira_conta(texto):
    assert DetectorPorExpressoes().avaliar(texto) is Passagem.SEGUIR


def test_explicitas_vazias_levantam():
    with pytest.raises(ValueError):
        DetectorPorExpressoes(())


def test_explicitas_so_com_espacos_levantam():
    with pytest.raises(ValueError):
        DetectorPorExpressoes(("   ",))


def test_ambiguos_vazios_so_explicitas_e_seguir():
    detector = DetectorPorExpressoes(ambiguos=())
    assert detector.avaliar("quero me matar") is Passagem.ENCAMINHAR
    assert detector.avaliar("quero morrer") is Passagem.SEGUIR
    assert detector.avaliar("o prazo do relatorio") is Passagem.SEGUIR


def _as(hora, minuto):
    return datetime(2026, 1, 2, hora, minuto, tzinfo=timezone.utc)


def test_sessao_sem_registro_nao_tem_recente():
    assert not RegistroDaSessao().houve_recente(_as(10, 0))


def test_sessao_lembra_dentro_da_janela():
    sessao = RegistroDaSessao()
    sessao.registrar(_as(10, 0))
    assert sessao.houve_recente(_as(10, 20))


def test_sessao_esquece_fora_da_janela():
    sessao = RegistroDaSessao()
    sessao.registrar(_as(10, 0))
    assert not sessao.houve_recente(_as(10, 31))
