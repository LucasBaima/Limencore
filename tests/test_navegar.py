import uuid

import pytest

from conftest import despejo_com_fios
from limencore.fio import EstadoFio, TransicaoInvalida

TEXTO = "o prazo do relatorio. a viagem de sabado"


@pytest.fixture
def dois(banco):
    return despejo_com_fios(banco, TEXTO, [(0, 21)], [(22, 40)])


class TestEntrar:
    def test_jogado_vira_escolhido(self, banco, relogio, dois):
        _, (a, _) = dois
        a = banco.entrar(a)
        assert a.estado is EstadoFio.ESCOLHIDO
        assert a.ultimo_toque == relogio.agora
        assert [(t.de, t.para) for t in banco.historico(a.id)] == [
            (None, EstadoFio.JOGADO), (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
        ]

    def test_entrar_duas_vezes_nao_duplica_transicao(self, banco, relogio, dois):
        _, (a, _) = dois
        banco.entrar(a)
        historico = banco.historico(a.id)
        relogio.andar(5)
        a = banco.entrar(a)
        assert a.estado is EstadoFio.ESCOLHIDO
        assert banco.historico(a.id) == historico

    def test_ultimo_toque_muda_sem_tocar_no_historico(self, banco, relogio, dois):
        _, (a, _) = dois
        a = banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        assert banco.buscar_fios(a.despejo_id)[0].ultimo_toque is None
        historico = banco.historico(a.id)
        banco.entrar(a)
        primeiro = banco.buscar_fios(a.despejo_id)[0].ultimo_toque
        relogio.andar(30)
        banco.entrar(a)
        segundo = banco.buscar_fios(a.despejo_id)[0].ultimo_toque
        assert primeiro < segundo == relogio.agora
        assert banco.historico(a.id) == historico

    def test_entrar_em_b_nao_muda_a(self, banco, relogio, dois):
        _, (a, b) = dois
        a = banco.entrar(a)
        historico_a = banco.historico(a.id)
        relogio.andar(5)
        banco.entrar(b)
        a_depois = {f.id: f for f in banco.buscar_fios(a.despejo_id)}[a.id]
        assert a_depois == a
        assert banco.historico(a.id) == historico_a

    def test_dois_escolhidos_ao_mesmo_tempo(self, banco, dois):
        _, (a, b) = dois
        banco.entrar(a)
        banco.entrar(b)
        assert [f.estado for f in banco.buscar_fios(a.despejo_id)] == [EstadoFio.ESCOLHIDO] * 2
        assert {f.id for f in banco.mesa()} == {a.id, b.id}

    @pytest.mark.parametrize("estado", [EstadoFio.GUARDADO, EstadoFio.DESCARTADO])
    def test_outros_estados_recusados(self, banco, dois, estado):
        _, (a, _) = dois
        a = banco.atualizar_estado(a, estado)
        with pytest.raises(TransicaoInvalida):
            banco.entrar(a)
        assert banco.buscar_fios(a.despejo_id)[0].ultimo_toque is None

    def test_resolvido_e_juntado_recusados(self, banco, dois):
        _, (a, b) = dois
        banco.juntar(a, b)
        with pytest.raises(TransicaoInvalida):
            banco.entrar(b)
        a = banco.pousar(banco.entrar(a))
        with pytest.raises(TransicaoInvalida):
            banco.entrar(a)

    def test_ultimo_toque_sobrevive_a_reabrir(self, tmp_path, relogio):
        from limencore.storage import Armazenamento
        caminho = str(tmp_path / "n.db")
        x = Armazenamento(caminho, relogio=relogio)
        _, (a,) = despejo_com_fios(x, TEXTO)
        x.entrar(a)
        x.fechar()
        y = Armazenamento(caminho)
        assert y.buscar_fios(a.despejo_id)[0].ultimo_toque == relogio.agora
        y.fechar()


class TestBuscarDespejo:
    def test_acha(self, banco, dois):
        despejo, _ = dois
        assert banco.buscar_despejo(despejo.id) == despejo

    def test_nao_acha(self, banco):
        assert banco.buscar_despejo(str(uuid.uuid4())) is None
