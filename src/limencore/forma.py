from enum import Enum

#é o esqueleto das categorias do despejo

class Forma(Enum):
    DIVIDIR = "Dividir"   # vários pensamentos misturados -> separar
    UM_SO = "Um só"       # um pensamento -> tratar direto
    LIGAR = "Ligar"       # dois ou mais que se conectam -> juntar
