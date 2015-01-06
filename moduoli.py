import random
def returnExcuse():
    excuse=random.choice(list(open("excuse_list.txt")))
    return excuse
