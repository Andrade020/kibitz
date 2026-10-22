import os
import tempfile

# dados de teste isolados: precisa vir ANTES de importar o pacote (os caminhos são fixados na importação)
os.environ["TAC_DATA_DIR"] = tempfile.mkdtemp(prefix="tac-test-")

import pytest  # noqa: E402

from kibitz import app as app_module  # noqa: E402


@pytest.fixture()
def client():
    return app_module.app.test_client()


@pytest.fixture()
def demo_game(client):
    gid = client.post("/api/demo").get_json()["id"]
    yield gid
    client.delete(f"/api/games/{gid}")
