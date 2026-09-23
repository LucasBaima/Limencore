import dataclasses

import pytest

from limencore.agente.movimento import Forma, Movimento
from limencore.agente.pergunta import CamadaContencao, Pergunta
from limencore.agente.seletor import SeletorDeMovimento, SeletorGenerico
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
        seletor: SeletorDeMovimento = SeletorGenerico()
        assert isinstance(seletor, SeletorDeMovimento)

    def test_devolve_um_movimento(self):
        entry = ThoughtEntry(conteudo="hoje foi um dia dificil")
        mov = SeletorGenerico().selecionar(entry)
        assert isinstance(mov, Movimento)
        assert mov.forma is Forma.UM_SO
        assert mov.alvos == (entry.id,)

    def test_zero_inteligencia_de_escolha(self):
        seletor = SeletorGenerico()
        e1 = ThoughtEntry(conteudo="a")
        e2 = ThoughtEntry(conteudo="pensamento completamente diferente")
        m1 = seletor.selecionar(e1)
        m2 = seletor.selecionar(e2)
        # a forma e sempre UM_SO (prova a ausencia de escolha);
        # os alvos diferem porque apontam para ids diferentes
        assert m1.forma is m2.forma is Forma.UM_SO
        assert m1.alvos != m2.alvos


class TestForma:
    def test_tres_formas(self):
        assert {f.name for f in Forma} == {"DIVIDIR", "UM_SO", "LIGAR"}


class TestMovimento:
    def test_criacao(self):
        m = Movimento(Forma.UM_SO, ("id-a",))
        assert m.forma is Forma.UM_SO
        assert m.alvos == ("id-a",)

    def test_frozen(self):
        m = Movimento(Forma.UM_SO, ("id-a",))
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.forma = Forma.LIGAR

    def test_igualdade_por_valor(self):
        assert Movimento(Forma.UM_SO, ("id-a",)) == Movimento(Forma.UM_SO, ("id-a",))

    def test_multiplos_alvos(self):
        m = Movimento(Forma.LIGAR, ("id-a", "id-b"))
        assert m.alvos == ("id-a", "id-b")

    def test_alvos_vazio_falha(self):
        with pytest.raises(ValueError):
            Movimento(Forma.DIVIDIR, ())

    def test_alvo_em_branco_falha(self):
        with pytest.raises(ValueError):
            Movimento(Forma.UM_SO, ("  ",))

    def test_forma_invalida_falha(self):
        with pytest.raises(ValueError):
            Movimento("dividir", ("id-a",))
