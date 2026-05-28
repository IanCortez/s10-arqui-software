"""
Carga la base SQLite con stats de pokemones populares.
Equivale al dataset de Kaggle (abcsds/pokemon) sin requerir autenticación.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "pokemon_stats.db"

POKEMON = [
    # (name, hp, atk, def, sp_atk, sp_def, speed, total)
    ("bulbasaur", 45, 49, 49, 65, 65, 45, 318),
    ("ivysaur", 60, 62, 63, 80, 80, 60, 405),
    ("venusaur", 80, 82, 83, 100, 100, 80, 525),
    ("charmander", 39, 52, 43, 60, 50, 65, 309),
    ("charmeleon", 58, 64, 58, 80, 65, 80, 405),
    ("charizard", 78, 84, 78, 109, 85, 100, 534),
    ("squirtle", 44, 48, 65, 50, 64, 43, 314),
    ("wartortle", 59, 63, 80, 65, 80, 58, 405),
    ("blastoise", 79, 83, 100, 85, 105, 78, 530),
    ("caterpie", 45, 30, 35, 20, 20, 45, 195),
    ("butterfree", 60, 45, 50, 90, 80, 70, 395),
    ("weedle", 40, 35, 30, 20, 20, 50, 195),
    ("beedrill", 65, 90, 40, 45, 80, 75, 395),
    ("pidgey", 40, 45, 40, 35, 35, 56, 251),
    ("pidgeotto", 63, 60, 55, 50, 50, 71, 349),
    ("pidgeot", 83, 80, 75, 70, 70, 101, 479),
    ("rattata", 30, 56, 35, 25, 35, 72, 253),
    ("raticate", 55, 81, 60, 50, 70, 97, 413),
    ("pikachu", 35, 55, 40, 50, 50, 90, 320),
    ("raichu", 60, 90, 55, 90, 80, 110, 485),
    ("sandshrew", 50, 75, 85, 20, 30, 40, 300),
    ("clefairy", 70, 45, 48, 60, 65, 35, 323),
    ("vulpix", 38, 41, 40, 50, 65, 65, 299),
    ("ninetales", 73, 76, 75, 81, 100, 100, 505),
    ("jigglypuff", 115, 45, 20, 45, 25, 20, 270),
    ("zubat", 40, 45, 35, 30, 40, 55, 245),
    ("oddish", 45, 50, 55, 75, 65, 30, 320),
    ("meowth", 40, 45, 35, 40, 40, 90, 290),
    ("psyduck", 50, 52, 48, 65, 50, 55, 320),
    ("machop", 70, 80, 50, 35, 35, 35, 305),
    ("geodude", 40, 80, 100, 30, 30, 20, 300),
    ("magikarp", 20, 10, 55, 15, 20, 80, 200),
    ("gyarados", 95, 125, 79, 60, 100, 81, 540),
    ("eevee", 55, 55, 50, 45, 65, 55, 325),
    ("snorlax", 160, 110, 65, 65, 110, 30, 540),
    ("mewtwo", 106, 110, 90, 154, 90, 130, 680),
    ("mew", 100, 100, 100, 100, 100, 100, 600),
]

def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS pokemon_stats")
    cur.execute(
        """
        CREATE TABLE pokemon_stats (
            name TEXT PRIMARY KEY,
            hp INTEGER,
            attack INTEGER,
            defense INTEGER,
            sp_attack INTEGER,
            sp_defense INTEGER,
            speed INTEGER,
            total INTEGER
        )
        """
    )
    cur.executemany(
        "INSERT INTO pokemon_stats VALUES (?,?,?,?,?,?,?,?)", POKEMON
    )
    conn.commit()
    conn.close()
    print(f"Seeded {len(POKEMON)} pokemon into {DB_PATH}")


if __name__ == "__main__":
    seed()
