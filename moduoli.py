import random

class Module():
    @staticmethod
    def doexcuse():
        excuse=random.choice(list(open("excuse_list.txt")))
        return excuse
