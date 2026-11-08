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
    assert {"id": "item.consumable", "name": "消耗品", "count": 35, "max": 30, "set_all": True} in items["tables"]
    assert m["shards"]["types"][0] == {"value": 1, "name": "攻擊碎片"}
    assert len(m["shards"]["natures"]) == L.SHARD_NATURES
    assert {"id": "misc", "name": "其他",
            "tables": [{"id": "misc", "name": "其他", "count": 1, "max": None, "set_all": True}]} in m["groups"]
    assert m["ui"]["group.items"] == "道具"


def test_meta_en(client):
    m = client.get("/api/meta", params={"lang": "en"}).json()
    assert m["ui"]["group.items"] == "Items" and m["groups"][1]["name"] == "Items"
    assert m["groups"][1]["tables"][0]["name"] == i18n.name("item.consumable", "en")


def test_meta_characters(client):
    m = client.get("/api/meta", params={"lang": "zh-Hant"}).json()
    assert [c["id"] for c in m["characters"]] == list(L.ACTIVE_CHARACTERS)
    asbel = m["characters"][0]
    assert asbel["name"] == "艾斯貝爾"
    assert [(t["section"], t["id"]) for t in asbel["tables"]] == [
        ("stats", "asbel.stat"), ("artes", "asbel.arte"), ("counters", "asbel.counter"), ("together", "asbel.together")]
    stats, artes, counters, together = asbel["tables"]
    assert stats["name"] == i18n.name("section.stats", "zh-Hant") and stats["count"] == 11
    assert artes["max"] == 9999 and counters["max"] is None
    # stats: SET_ALL but read-only (offered, needs force); together: no SET_ALL at all
    assert (stats["set_all"], artes["set_all"], counters["set_all"], together["set_all"]) == (True, True, True, False)


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
    client.patch(f"/api/sessions/{sid}/tables/asbel.arte", json={"set_all": 9999})
    assert downloaded(client, sid).values("asbel.arte") == [9999] * 36


def test_edit_table_set_all_max(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set_all": "max"})
    assert {row["value"] for row in r.json()["rows"]} == {30}


def test_edit_misc(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/misc", json={"set_all": "max"})
    gald = r.json()["rows"][0]
    assert (gald["id"], gald["name"], gald["max"], gald["value"]) == ("misc.gald", "喀爾特", 9999999, 9999999)
    assert downloaded(client, sid).get("misc", 0) == 9999999
    r = client.patch(f"/api/sessions/{sid}/tables/misc", json={"set": {"0": 10000000}})
    assert r.status_code == 422


def test_edit_table_set_all_bad(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.consumable", json={"set_all": "lots"})
    assert r.status_code == 422


def test_edit_table_is_all_or_nothing(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/item.dish", json={"set": {"0": 5, "1": 16}})
    assert r.status_code == 422 and "0-15" in r.json()["detail"]
    assert client.get(f"/api/sessions/{sid}/tables/item.dish").json()["rows"][0]["value"] == 0


def _index(table_id, key):
    t = L.TABLES[table_id]
    return next(i for i in range(t.count) if t.entry_id(i) == f"{table_id}.{key}")


def test_read_table_flags(client, sid):
    t = client.get(f"/api/sessions/{sid}/tables/asbel.stat").json()
    assert t["set_all"] and t["hint"] == ""
    assert all(r["read_only"] and not r["hidden"] for r in t["rows"])
    assert [r["set_all"] for r in t["rows"]].count(True) == 6


def test_read_table_show_hidden(client, sid):
    url = f"/api/sessions/{sid}/tables/asbel.counter"
    rows = client.get(url).json()["rows"]
    assert len(rows) == L.TABLES["asbel.counter"].count - 2 and not any(r["hidden"] for r in rows)
    rows = client.get(url, params={"show_hidden": True}).json()["rows"]
    assert len(rows) == L.TABLES["asbel.counter"].count
    assert [r["id"] for r in rows if r["hidden"]] == ["asbel.counter.unknown_b28", "asbel.counter.unknown_b42"]


def test_table_hint_once(client, sid):
    artes = client.get(f"/api/sessions/{sid}/tables/asbel.arte").json()
    assert artes["hint"] == i18n.text("hint.usage_count", "zh-Hant") != ""
    assert all(r["hint"] == "" for r in artes["rows"])  # same as the table's: not repeated

    stats = client.get(f"/api/sessions/{sid}/tables/asbel.stat").json()
    hints = {r["id"]: r["hint"] for r in stats["rows"]}
    assert hints["asbel.stat.level"] == i18n.text("hint.linked_exp", "zh-Hant")
    assert hints["asbel.stat.attack"] == ""

    together = client.get(f"/api/sessions/{sid}/tables/asbel.together").json()
    assert together["hint"] and not together["set_all"] and all(r["hint"] == "" for r in together["rows"])


def test_edit_read_only_needs_force(client, sid):
    url = f"/api/sessions/{sid}/tables/asbel.stat"
    level = _index("asbel.stat", "level")
    r = client.patch(url, json={"set": {str(level): 50}})
    assert r.status_code == 422 and "read-only" in r.json()["detail"]
    assert not client.get(f"/api/sessions/{sid}").json()["modified"]
    r = client.patch(url, json={"set": {str(level): 50}, "force": True})
    assert r.status_code == 200
    assert downloaded(client, sid).get("asbel.stat", level) == 50


def test_edit_set_all_read_only_needs_force(client, sid):
    url = f"/api/sessions/{sid}/tables/asbel.stat"
    assert client.patch(url, json={"set_all": "max"}).status_code == 422
    r = client.patch(url, json={"set_all": "max", "force": True})
    values = {row["id"]: row["value"] for row in r.json()["rows"]}
    assert values["asbel.stat.attack"] == 1999 and values["asbel.stat.level"] == 0


def test_edit_set_all_skips_hidden_counters(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/asbel.counter", json={"set_all": "max"}, params={"show_hidden": True})
    values = {row["id"]: row["value"] for row in r.json()["rows"]}
    assert values["asbel.counter.enemies_defeated"] == 9999999 and values["asbel.counter.unknown_b28"] == 0


def test_edit_together_set_all_refused(client, sid):
    r = client.patch(f"/api/sessions/{sid}/tables/asbel.together", json={"set_all": 1, "force": True})
    assert r.status_code == 422 and "no entries" in r.json()["detail"]


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
