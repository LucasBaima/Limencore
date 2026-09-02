import pytest

from limencore.ambient import ContextoAmbiente, AreaEnergia


class TestValido:
    def test_vazio_tudo_none(self):
        c = ContextoAmbiente()
        assert c.sono_horas is None
        assert c.sono_interrupcoes is None
        assert c.cafeina_mg is None
        assert c.energia == {}

    def test_energia_valida(self):
        c = ContextoAmbiente(energia={AreaEnergia.TRABALHO: 60, AreaEnergia.CASA: 30})
        assert c.energia[AreaEnergia.TRABALHO] == 60

    def test_ambiente_completo(self):
        c = ContextoAmbiente(
            sono_horas=7.5,
            sono_interrupcoes=2,
            cafeina_mg=200,
            energia={AreaEnergia.TRABALHO: 50},
        )
        assert c.cafeina_mg == 200


class TestOpcional:
    # ausencia != invalido (DECISIONS §9): campo None passa, nunca bloqueia.
    def test_so_sono(self):
        c = ContextoAmbiente(sono_horas=8)
        assert c.sono_horas == 8
        assert c.sono_interrupcoes is None

    def test_so_cafeina(self):
        assert ContextoAmbiente(cafeina_mg=100).cafeina_mg == 100

    def test_energia_ausente_vira_dict_vazio(self):
        assert ContextoAmbiente().energia == {}


class TestInvalido:
    def test_energia_chave_nao_enum(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": 20})

    def test_energia_valor_fracionario(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={AreaEnergia.TRABALHO: 22.5})

    def test_energia_valor_bool(self):
        # True vale 1 em Python; o guard barra bool de proposito.
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={AreaEnergia.TRABALHO: True})

    def test_sono_interrupcoes_fracionario(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_interrupcoes=2.5)


class TestBorda:
    # --- energia: soma total ---
    def test_soma_exatamente_100_ok(self):
        ContextoAmbiente(energia={AreaEnergia.TRABALHO: 70, AreaEnergia.CASA: 30})

    def test_soma_101_falha(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={AreaEnergia.TRABALHO: 70, AreaEnergia.CASA: 31})

    # --- energia: valor individual ---
    @pytest.mark.parametrize("valor", [0, 100])
    def test_energia_valor_no_limite_ok(self, valor):
        ContextoAmbiente(energia={AreaEnergia.TRABALHO: valor})

    @pytest.mark.parametrize("valor", [-1, 101])
    def test_energia_valor_fora_falha(self, valor):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={AreaEnergia.TRABALHO: valor})

    # --- sono_horas: 0 a 24 ---
    @pytest.mark.parametrize("h", [0, 24])
    def test_sono_no_limite_ok(self, h):
        ContextoAmbiente(sono_horas=h)

    @pytest.mark.parametrize("h", [-0.1, 24.1])
    def test_sono_fora_falha(self, h):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_horas=h)

    # --- sono_interrupcoes: 0 a 10 ---
    @pytest.mark.parametrize("n", [0, 10])
    def test_interrupcoes_no_limite_ok(self, n):
        ContextoAmbiente(sono_interrupcoes=n)

    def test_interrupcoes_acima_falha(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_interrupcoes=11)

    # --- cafeina_mg: 0 a 500 ---
    @pytest.mark.parametrize("mg", [0, 500])
    def test_cafeina_no_limite_ok(self, mg):
        ContextoAmbiente(cafeina_mg=mg)

    @pytest.mark.parametrize("mg", [-1, 501])
    def test_cafeina_fora_falha(self, mg):
        with pytest.raises(ValueError):
            ContextoAmbiente(cafeina_mg=mg)