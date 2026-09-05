
import json

def readJson(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file)


    return data

def test():
    t = [
        readJson("aulas.json"),
        readJson("carreras.json"),
        readJson("materias.json"),
        readJson("profesores.json")
    ]

    for data in t:
        print(data[0])


test()