import pytest

from limencore.agente.encaminhamento import (
    EXPRESSOES_PROVISORIAS,
    DetectorDeEncaminhamento,
    DetectorPorExpressoes,
)


def test_detector_padrao_cumpre_a_costura():
    assert isinstance(DetectorPorExpressoes(), DetectorDeEncaminhamento)


@pytest.mark.parametrize("expressao", EXPRESSOES_PROVISORIAS)
def test_cada_expressao_dentro_de_uma_frase_dispara(expressao):
    assert DetectorPorExpressoes().deve_encaminhar(f"hoje eu pensei: {expressao}, de novo")


@pytest.mark.parametrize("texto", ["Penso em SUICÍDIO", "NÃO QUERO MAIS VIVER"])
def test_acento_e_maiusculas_disparam(texto):
    assert DetectorPorExpressoes().deve_encaminhar(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "esse prazo vai me matar",
        "esse calor vai me matar",
        "tenho medo de me machucar na academia",
        "morrendo de rir",
    ],
)
def test_usos_figurados_nao_disparam(texto):
    assert not DetectorPorExpressoes().deve_encaminhar(texto)


@pytest.mark.parametrize("texto", ["quero me matar", "Penso em me matar todo dia"])
def test_intencao_em_primeira_pessoa_dispara(texto):
    assert DetectorPorExpressoes().deve_encaminhar(texto)


@pytest.mark.parametrize("texto", ["suicidios", "me matarem"])
def test_so_palavra_inteira_dispara(texto):
    assert not DetectorPorExpressoes().deve_encaminhar(texto)


@pytest.mark.parametrize("texto", ["o prazo do relatorio", "hoje foi um dia dificil"])
def test_textos_neutros_nao_disparam(texto):
    assert not DetectorPorExpressoes().deve_encaminhar(texto)


def test_expressoes_customizadas():
    detector = DetectorPorExpressoes(("palavra teste",))
    assert detector.deve_encaminhar("aqui tem a PALAVRA teste no meio")
    assert not detector.deve_encaminhar("quero me matar")
    assert not detector.deve_encaminhar("o prazo do relatorio")


def test_lista_vazia_levanta():
    with pytest.raises(ValueError):
        DetectorPorExpressoes(())


def test_lista_so_com_espacos_levanta():
    with pytest.raises(ValueError):
        DetectorPorExpressoes(("   ",))
