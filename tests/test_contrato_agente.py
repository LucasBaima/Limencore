import limencore.agente
import limencore.agente.movimento

from limencore.agente import (
    CamadaContencao,
    Forma,
    Movimento,
    Pergunta,
    SeletorDeMovimento,
    SeletorDePergunta,
    SeletorGenerico,
)
from limencore.despejo import Despejo


class TestContratoAgente:
    def test_all_exato(self):
        assert set(limencore.agente.__all__) == {
            "CamadaContencao",
            "Forma",
            "Movimento",
            "Pergunta",
            "SeletorDeMovimento",
            "SeletorDePergunta",
            "SeletorGenerico",
        }

    def test_tudo_em_all_e_importavel(self):
        for nome in limencore.agente.__all__:
            assert hasattr(limencore.agente, nome) #hasattr verifica se o objeto tem o atributo nome

    def test_porta_da_frente_e_o_mesmo_objeto(self):
        assert limencore.agente.Movimento is limencore.agente.movimento.Movimento
        assert limencore.agente.Forma is limencore.agente.movimento.Forma

    def test_alias_temporario_aponta_pro_novo(self):
        assert SeletorDePergunta is SeletorDeMovimento

    def test_generico_via_contrato_devolve_movimento(self):
        entry = Despejo(conteudo="x")
        seletor = SeletorGenerico()
        assert isinstance(seletor, SeletorDeMovimento)
        mov = seletor.selecionar(entry)
        assert isinstance(mov, Movimento)
        assert mov.forma is Forma.UM_SO
