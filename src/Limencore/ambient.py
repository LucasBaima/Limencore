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
    cafeina_mg: int | None = None
    energia: dict[AreaEnergia, int] = field(default_factory=dict)











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