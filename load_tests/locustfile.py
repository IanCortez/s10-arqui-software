"""
Locust load test contra Search API.

Genera entre 1.000 y 10.000 requests para alimentar los logs distribuidos.

Headless (recomendado):
    locust -f load_tests/locustfile.py --headless \
           -u 50 -r 5 -t 3m --host http://localhost:8000

Con UI:
    locust -f load_tests/locustfile.py --host http://localhost:8000
    # luego abrir http://localhost:8089

Para forzar un número exacto de requests:
    locust -f load_tests/locustfile.py --headless \
           -u 20 -r 5 --host http://localhost:8000 -i 2000
"""
import random
from locust import HttpUser, task, between

# Lista de pokemones que SÍ están en la DB (mayoría de hits)
POPULAR = [
    "bulbasaur", "ivysaur", "venusaur", "charmander", "charmeleon", "charizard",
    "squirtle", "wartortle", "blastoise", "pikachu", "raichu", "eevee",
    "snorlax", "mewtwo", "mew", "gyarados", "magikarp", "psyduck",
    "jigglypuff", "meowth",
]

# Pokemones que NO están en la DB -> generan 404/parcial
UNKNOWN = ["missingno", "abc", "xyz", "test1", "fakemon"]


class PokeSearchUser(HttpUser):
    # Tiempo de espera entre tareas (simula usuario real)
    wait_time = between(0.1, 0.5)

    @task(9)
    def search_popular(self):
        name = random.choice(POPULAR)
        with self.client.post(
            "/poke/search",
            json={"Pokemon_Name": name},
            name="/poke/search [popular]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(1)
    def search_unknown(self):
        name = random.choice(UNKNOWN)
        with self.client.post(
            "/poke/search",
            json={"Pokemon_Name": name},
            name="/poke/search [unknown]",
            catch_response=True,
        ) as resp:
            # Para los desconocidos esperamos 500 (upstream falla)
            if resp.status_code in (200, 500):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")
