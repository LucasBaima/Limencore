import dataclasses

import pytest

from limencore.agente.pergunta import CamadaContencao, Pergunta
from limencore.agente.seletor import SeletorDePergunta, SeletorGenerico
from limencore.entry import ThoughtEntry


class TestCamadaContencao:
    def test_quatro_camadas(self):
        assert {c.name for c in CamadaContencao} == {
            "SITUACAO",
            "PENSAMENTO",
            "EMOCAO",
            "PREOCUPACAO",
        }


class TestPergunta:
    def test_criacao(self):
        p = Pergunta(texto="Como isso te afeta?", camada=CamadaContencao.EMOCAO)
        assert p.texto == "Como isso te afeta?"
        assert p.camada is CamadaContencao.EMOCAO

    def test_frozen(self):
        p = Pergunta(texto="x", camada=CamadaContencao.SITUACAO)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.texto = "y"


class TestSeletorGenerico:
    def test_implementa_a_costura(self):
        seletor: SeletorDePergunta = SeletorGenerico()
        assert isinstance(seletor, SeletorDePergunta)

    def test_devolve_uma_pergunta(self):
        entry = ThoughtEntry(conteudo="hoje foi um dia dificil")
        pergunta = SeletorGenerico().selecionar(entry)
        assert isinstance(pergunta, Pergunta)
        assert pergunta.texto
        assert pergunta.camada is None

    def test_zero_inteligencia_de_escolha(self):
        seletor = SeletorGenerico()
        e1 = ThoughtEntry(conteudo="a")
        e2 = ThoughtEntry(conteudo="pensamento completamente diferente")
        assert seletor.selecionar(e1) == seletor.selecionar(e2)
