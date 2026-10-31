import re

import pytest
from fastapi.testclient import TestClient

from togf_save import decode, i18n
from togf_save.native import NativeData, Shard, layout as L
from togf_save.web.app import STATIC_DIR, create_app
from togf_save.web.sessions import SessionStore

from .helpers import NATIVE_SIZE, make_save, make_slots


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SessionStore(max_sessions=2)))


@pytest.fixture
def sav_bytes() -> bytes:
    return make_save(*make_slots(native=bytes(NATIVE_SIZE)))


@pytest.fixture
def sid(client, sav_bytes) -> str:
    r = client.post("/api/sessions", files={"file": ("SaveDat000.sav", sav_bytes)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def downloaded(client, sid) -> NativeData:
    r = client.get(f"/api/sessions/{sid}/download")
    assert r.status_code == 200
    return NativeData(decode(r.content).native)


# --- meta / sessions ---

def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["default_lang"] == "zh-Hant" and "zh-Hant" in m["languages"]
    items = next(g for g in m["groups"] if g["id"] == "items")
    assert {"id": "item.consumable", "name": "消耗品", "count": 35, "max": 30} in items["tables"]
    assert m["shards"]["types"][0] == {"value": 1, "name": "攻擊碎片"}
    assert len(m["shards"]["natures"]) == L.SHARD_NATURES
    assert {"id": "misc", "name": "其他", "tables": []} in m["groups"]
    assert m["ui"]["group.items"] == "道具"


def test_meta_en(client):
    m = client.get("/api/meta", params={"lang": "en"}).json()
    assert m["ui"]["group.items"] == "Items" and m["groups"][1]["name"] == "Items"
    assert m["groups"][1]["tables"][0]["name"] == i18n.name("item.consumable", "en")


def test_unknown_lang(client):
    assert client.get("/api/meta", params={"lang": "xx"}).status_code == 422


def test_upload_summary(client, sid):
    s = client.get(f"/api/sessions/{sid}").json()
    assert s["filename"] == "SaveDat000.sav" and not s["modified"]
    assert all(slot["backup_identical"] for slot in s["info"]["slots"])
    assert s["native_size"] == NATIVE_SIZE


def test_upload_not_a_save(client):
    r = client.post("/api/sessions", files={"file": ("x.sav", b"nope")})
    assert r.status_code == 422 and "too small" in r.json()["detail"]


def test_unknown_session(client):
    assert client.get("/api/sessions/nope").status_code == 404


def test_unedited_download_is_identical(client, sid, sav_bytes):
    r = client.get(f"/api/sessions/{sid}/download")
    assert r.content == sav_bytes
    assert 'filename="SaveDat000.sav"' in r.headers["content-disposition"]


def test_delete_and_eviction(client, sav_bytes, sid):
    upload = lambda: client.post("/api/sessions", files={"file": ("a.sav", sav_bytes)}).json()["id"]
    second, third = upload(), upload()  # store holds 2: the first is evicted
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{second}").status_code == 204
    assert client.get(f"/api/sessions/{second}").status_code == 404
    assert client.get(f"/api/sessions/{third}").status_code == 200


def test_slot1_read_only(client, sid):
    data = client.get(f"/api/sessions/{sid}/slot1").json()["data"]
    assert data["listParam"]["leaderLevel"] == 154
    assert data["capture"] == "<1796 bytes>"


# --- tables ---

def test_read_table(client, sid):
    t = client.get(f"/api/sessions/{sid}/tables/item.consumable").json()
    assert t["name"] == "消耗品" and t["max"] == 30 and len(t["rows"]) == 35
    assert t["rows"][4]["name"] == "萬靈藥瓶"


def test_edit_table(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set": {"0": 30, "4": 3}})
    assert r.status_code == 200
    assert [row["value"] for row in r.json()["rows"][:5]] == [30, 0, 0, 0, 3]
    assert client.get(f"/api/sessions/{sid}").json()["modified"]
    assert downloaded(client, sid).get("item.consumable", 4) == 3


def test_edit_table_set_all(client, sid):
    client.patch(f"/api/sessions/{sid}/tables/arte.asbel", json={"set_all": 9999})
    assert downloaded(client, sid).values("arte.asbel") == [9999] * 36


def test_edit_table_set_all_max(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set_all": "max"})
    assert {row["value"] for row in r.json()["rows"]} == {30}


def test_edit_table_set_all_bad(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set_all": "lots"})
    assert r.status_code == 422


def test_edit_table_is_all_or_nothing(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.dish", json={"set": {"0": 5, "1": 16}})
    assert r.status_code == 422 and "0-15" in r.json()["detail"]
    assert client.get(f"/api/sessions/{sid}/tables/item.dish").json()["rows"][0]["value"] == 0


def test_unknown_table(client, sid):
    assert client.get(f"/api/sessions/{sid}/tables/item.nope").status_code == 404


def test_bad_index(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set": {"35": 1}})
    assert r.status_code == 422


# --- shards ---

def test_shards(client, sid):
    r = client.put(f"/api/sessions/{sid}/shards/3", json={"type": 1, "nature": 3, "strength": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["used"] == 1 and body["mismatches"] == []
    assert body["rows"][3]["shard"]["type_name"] == "攻擊碎片"
    assert downloaded(client, sid).shard(3) == Shard(1, 3, 10)

    body = client.delete(f"/api/sessions/{sid}/shards/3").json()
    assert body["used"] == 0 and body["rows"][3]["shard"] is None


def test_shard_invalid(client, sid):
    r = client.put(f"/api/sessions/{sid}/shards/0", json={"type": 27, "nature": 1, "strength": 1})
    assert r.status_code == 422
    r = client.put(f"/api/sessions/{sid}/shards/199", json={"type": 1, "nature": 1, "strength": 1})
    assert r.status_code == 422


def test_shards_clear_and_fix(client, sid):
    for slot in range(3):
        client.put(f"/api/sessions/{sid}/shards/{slot}", json={"type": 2, "nature": 1, "strength": 1})
    assert client.post(f"/api/sessions/{sid}/shards/clear").json()["used"] == 0

    # slot written raw, count byte left at 0
    client.put(f"/api/sessions/{sid}/native/hex", json={"offset": L.SHARD_OFFSET, "hex": "05 02 01 01"})
    assert client.get(f"/api/sessions/{sid}/shards").json()["mismatches"] == \
        [{"type": 5, "stored": 0, "actual": 1}]
    assert client.post(f"/api/sessions/{sid}/shards/fix-counts").json()["mismatches"] == []


# --- hex ---

def test_hex(client, sid):
    r = client.put(f"/api/sessions/{sid}/native/hex", json={"offset": 0x10, "hex": "de ad be ef"})
    assert r.json() == {"offset": 0x10, "length": 4, "modified": True}
    r = client.get(f"/api/sessions/{sid}/native/hex", params={"offset": 0x10, "length": 4})
    assert r.json()["hex"] == "de ad be ef"


@pytest.mark.parametrize("body", [{"offset": 0, "hex": "zz"}, {"offset": 0, "hex": ""},
                                  {"offset": NATIVE_SIZE - 1, "hex": "00 00"}])
def test_hex_invalid_write(client, sid, body):
    assert client.put(f"/api/sessions/{sid}/native/hex", json=body).status_code == 422


def test_hex_read_past_end(client, sid):
    r = client.get(f"/api/sessions/{sid}/native/hex", params={"offset": NATIVE_SIZE})
    assert r.status_code == 422


# --- frontend ---

def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text


@pytest.mark.parametrize("path", ["/app.js", "/style.css"])
def test_assets_served(client, path):
    assert client.get(path).status_code == 200


def test_frontend_text_keys_exist():
    """Every interface-text key quoted in app.js is in both ui.json files."""
    source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    keys = {k for k in re.findall(r'"((?:web|common|info|shard|shards|group)\.[\w.]+)"', source)
            if not k.endswith(".")}
    assert "web.set_all_max" in keys  # the pattern finds them
    for lang in i18n.available():
        assert keys <= i18n.load(lang, "ui").keys(), lang
