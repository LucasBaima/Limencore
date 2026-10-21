import dataclasses

import pytest

from limencore.agente.movimento import Forma, Movimento
from limencore.corte import Corte, FioPlanejado, Trecho, recortar

ALVO = "6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b"


def _corte(*fios):
    return Corte(fios=tuple(FioPlanejado(trechos=tuple(Trecho(i, f) for i, f in g)) for g in fios))


class TestTrecho:
    def test_valido(self):
        t = Trecho(0, 3)
        assert (t.inicio, t.fim) == (0, 3)

    def test_imutavel(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            Trecho(0, 3).inicio = 1

    @pytest.mark.parametrize("inicio,fim", [(-1, 2), (3, 3), (4, 2)])
    def test_limites_invalidos(self, inicio, fim):
        with pytest.raises(ValueError):
            Trecho(inicio, fim)

    @pytest.mark.parametrize("inicio,fim", [(0.0, 2), (0, "2"), (True, 2)])
    def test_nao_int(self, inicio, fim):
        with pytest.raises(ValueError):
            Trecho(inicio, fim)


class TestFioPlanejado:
    def test_vazio(self):
        with pytest.raises(ValueError):
            FioPlanejado(trechos=())

    def test_fora_de_ordem(self):
        with pytest.raises(ValueError, match="ordem"):
            FioPlanejado(trechos=(Trecho(5, 8), Trecho(0, 3)))

    def test_item_nao_trecho(self):
        with pytest.raises(ValueError):
            FioPlanejado(trechos=((0, 3),))


class TestCorte:
    def test_vazio(self):
        with pytest.raises(ValueError):
            Corte(fios=())

    def test_sobreposicao_no_mesmo_fio(self):
        with pytest.raises(ValueError, match="sobrepostos"):
            _corte([(0, 5), (4, 8)])

    def test_sobreposicao_entre_fios(self):
        with pytest.raises(ValueError, match="sobrepostos"):
            _corte([(0, 5)], [(3, 8)])

    def test_trechos_encostados_valem(self):
        _corte([(0, 5)], [(5, 8)])

    def test_fios_intercalados_valem(self):
        assert _corte([(0, 2), (6, 8)], [(3, 5)]).forma is Forma.DIVIDIR

    def test_forma_um_so(self):
        assert _corte([(0, 3)]).forma is Forma.UM_SO

    def test_forma_ligar(self):
        assert _corte([(0, 3), (5, 8)]).forma is Forma.LIGAR

    def test_forma_dividir(self):
        assert _corte([(0, 3)], [(5, 8)], [(9, 10)]).forma is Forma.DIVIDIR

    def test_inteiro(self):
        corte = Corte.inteiro("abc def")
        assert corte == _corte([(0, 7)])
        assert corte.forma is Forma.UM_SO
        corte.validar_para("abc def")

    def test_validar_para_aceita(self):
        _corte([(0, 3)], [(4, 7)]).validar_para("abc def")

    def test_validar_para_fora_do_texto(self):
        with pytest.raises(ValueError, match="fora do texto"):
            _corte([(0, 3)], [(4, 9)]).validar_para("abc def")

    def test_validar_para_trecho_so_de_espacos(self):
        with pytest.raises(ValueError, match="espacos"):
            _corte([(0, 3)], [(3, 5)]).validar_para("abc  def")


class TestRecortar:
    def test_fatia_exata_sem_tratar(self):
        texto = "  um, dois \n tres "
        assert recortar(texto, Trecho(0, 6)) == "  um, "
        assert recortar(texto, Trecho(6, 13)) == texto[6:13]


class TestMovimentoComCorte:
    def test_sem_corte_continua_valido(self):
        m = Movimento(forma=Forma.DIVIDIR, alvos=(ALVO,))
        assert m.corte is None

    def test_forma_igual_ao_corte(self):
        corte = _corte([(0, 3)], [(4, 7)])
        assert Movimento(forma=Forma.DIVIDIR, alvos=(ALVO,), corte=corte).corte == corte

    @pytest.mark.parametrize("forma", [Forma.UM_SO, Forma.LIGAR])
    def test_forma_divergente_levanta(self, forma):
        with pytest.raises(ValueError, match="diverge"):
            Movimento(forma=forma, alvos=(ALVO,), corte=_corte([(0, 3)], [(4, 7)]))

    def test_corte_nao_corte_levanta(self):
        with pytest.raises(ValueError):
            Movimento(forma=Forma.UM_SO, alvos=(ALVO,), corte=((0, 3),))
