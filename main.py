from pathlib import Path

from extraer_excel2 import generar_json


def main():
    base = Path(__file__).resolve().parent
    # Configura todos los parámetros aquí. También puedes usar rutas absolutas.
    rutas = generar_json(
        excel=base / "scheduler_dummy_data_.xlsx",
        salida=base / "data",
        dias_semana="LuMaMiJuViSaDo",
    )
    for nombre, ruta in rutas.items():
        print(f"{nombre}: {ruta}")


if __name__ == "__main__":
    main()