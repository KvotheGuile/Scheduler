
import json
from classes import ClassInfo, Teacher, Section, Room

def readJson(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file)

    return data

def getClassesInfo(filename: str) -> list[ClassInfo]:
    ...


def getTeachers(filename: str) -> list[Teacher]:
    ...


def getSections(filename: str) -> list[Section]:
    ...


def getRooms(filename: str) -> list[Room]:
    ...

    