from enum import Enum
from dataclasses import dataclass, field #@dataclass é um decorador que cria automaticamente os métodos __init__, __repr__, __eq__ e __hash__ para a classe



class AreaEnergia(Enum):
    TRABALHO = "Trabalho"
    DESLOCAMENTO = "Deslocamento"
    ESTUDO = "Estudo/Desenvolvimento"
    CASA = "Casa & Responsabilidades"
    FAMILIA = "Família & Relacionamentos"
    TEMPO_PESSOAL = "Tempo pessoal"
    OUTRO = "Outro"



@dataclass
class ContextoAmbiente:
    sono_horas: float | None = None
    sono_interrupcoes: int | None = None
    cafeina_mg: float | None = None
    energia: dict[AreaEnergia, int] = field(default_factory=dict)


    def __post_init__(self):  #Validações

        if self.sono_horas is not None:
            if isinstance(self.sono_horas, bool) or not isinstance(self.sono_horas, (int, float)):
                raise ValueError(f"sono_horas: use numero, nao {self.sono_horas!r}")
            if not 0 <= self.sono_horas <= 24:
                raise ValueError(f"sono_horas={self.sono_horas}: fora do intervalo 0-24")

        if self.sono_interrupcoes is not None:
            if isinstance(self.sono_interrupcoes, bool) or not isinstance(self.sono_interrupcoes, int):
                raise ValueError(f"sono_interrupcoes: use inteiro, nao {self.sono_interrupcoes!r}")
            if not 0 <= self.sono_interrupcoes <= 10:
                raise ValueError(f"sono_interrupcoes={self.sono_interrupcoes}: fora do intervalo 0-10")

        if self.cafeina_mg is not None:
            if isinstance(self.cafeina_mg, bool) or not isinstance(self.cafeina_mg, (int, float)):
                raise ValueError(f"cafeina_mg: use numero, nao {self.cafeina_mg!r}")
            if not 0 <= self.cafeina_mg <= 500:  # >400mg possivel mas nao recomendado; 500 = teto de sanidade
                raise ValueError(f"cafeina_mg={self.cafeina_mg}: fora do intervalo 0-500")

        total = 0
        for area, valor in self.energia.items():
            if not isinstance(area, AreaEnergia):
                raise ValueError(f"chave de energia invalida: {area!r} nao e AreaEnergia")
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise ValueError(f"energia de {area.value}: use inteiro (ex: 25), nao {valor!r}")
            if not 0 <= valor <= 100:
                raise ValueError(f"energia de {area.value}={valor}: fora do intervalo 0-100")
            total += valor
        if total > 100:
            raise ValueError(f"soma da energia={total}: excede 100%")







#S2-H2-T1

# --- Testes rápidos de sanidade (rode com: python ambient.py) ---
#if __name__ == "__main__":
    # 1. Contexto totalmente vazio funciona (tudo opcional)
   # vazio = ContextoAmbiente()
    #print("OK vazio:", vazio)

    # 2. Contexto preenchido
   # cheio = ContextoAmbiente(
    #    sono_horas=6.5,
     #   sono_interrupcoes=2,
      #  cafeina_mg=180,
       # energia={
        #    AreaEnergia.TRABALHO: 40,
         #   AreaEnergia.FAMILIA: 30,
          #  AreaEnergia.TEMPO_PESSOAL: 0,
        #},
    #)
    #print("OK cheio:", cheio)

    # 3. Dois contextos diferentes têm dicionários de energia independentes
    #    (prova que o default_factory funcionou — sem dict compartilhado)   <-- Cada dia tem seu próprio bolde
    #a = ContextoAmbiente()
    #b = ContextoAmbiente()
    #a.energia[AreaEnergia.TRABALHO] = 100
    #print("OK independência:", a.energia != b.energia, "| b vazio:", b.energia)



#Testes S2-H2-T2

#casos = [
#    ("ok",        {AreaEnergia.TRABALHO: 60, AreaEnergia.CASA: 30}),
#    ("22.5",      {AreaEnergia.TRABALHO: 22.5}),
#    ("soma 110",  {AreaEnergia.TRABALHO: 70, AreaEnergia.CASA: 40}),
#    ("chave str", {"Trabalho": 20}),
#]
#for nome, e in casos:
#    try:
#        ContextoAmbiente(energia=e)
#        print(f"[{nome}] construiu")
#    except ValueError as erro:
#        print(f"[{nome}] barrou: {erro}")




#Testes S2-H2-T3


#casos_sono = [
   # ("ok 7.5h/2int", dict(sono_horas=7.5, sono_interrupcoes=2)),
   #         ("nada (None)",  dict()),
   # ("sono 25h",     dict(sono_horas=25)),
   # ("sono -1",      dict(sono_horas=-1)),
   # ("int 2.5",      dict(sono_interrupcoes=2.5)),
   # ("int 15",       dict(sono_interrupcoes=15)),
#]
#for nome, kw in casos_sono:
#    try:
#        ContextoAmbiente(**kw)
#        print(f"[{nome}] construiu")
#    except ValueError as erro:
#        print(f"[{nome}] barrou: {erro}")


#casos_cafeina = [
   #("ok 200mg",   dict(cafeina_mg=200)),
   # ("limite 500", dict(cafeina_mg=500)),
   # ("nada (None)",dict()),
   #   ("600mg",      dict(cafeina_mg=600)),
   # ("negativo",   dict(cafeina_mg=-50)),
   # ("float 200.5",dict(cafeina_mg=200.5)),
#]
#for nome, kw in casos_cafeina:
#    try:
#        ContextoAmbiente(**kw)
#        print(f"[{nome}] construiu")
#    except ValueError as erro:
#        print(f"[{nome}] barrou: {erro}")