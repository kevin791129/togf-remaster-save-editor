# ToGf Save Editor

Save editor for **Tales of Graces f Remastered** (PS5, PPSA19989). It decrypts `SaveDat*.sav`,
lets you edit the game data, and re-encrypts it with valid CRCs and backup copies.

Ways to use it:

- **Python library**: `import togf_save`
- **Command line**: `togf-save ...` or `python -m togf_save ...`
- **Web editor**: a local FastAPI server. You upload a save, edit it in the browser, then download
  the re-encoded save.

> Always keep a copy of your original save. Edits to unmapped data can corrupt a save.

## Install

You need Python 3.11 or newer. From the repo root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

`-e` installs the package in editable mode, so changes to the source take effect without
reinstalling. `[dev]` adds the test tools (`pytest`, plus `httpx2` for FastAPI's test client).

Runtime dependencies: `pycryptodome`, `fastapi`, `uvicorn`, `python-multipart`, `loguru`,
`python-dotenv`.

## Configuration

Settings are read from environment variables. A `.env` file in the repo root also works:
copy [.env.example](.env.example) to `.env` and edit it. `.env` is not committed.

| Variable | Used by | Meaning |
|---|---|---|
| `TEST_TOGF_SAVE` | tests | Path to a real save for the optional round-trip tests. The file is only read. |
| `DEFAULT_LANG` | CLI, web | Language for names, matching a folder name in `togf_save/locales`. Default `ja`. |
| `WEB_HOST` | `togf-save serve` | Address the server listens on. Default `127.0.0.1`, which is this computer only. |
| `WEB_PORT` | `togf-save serve` | Port. Default `8000`. |
| `LOG_ENABLED` | CLI, web | Write a log file. Default `false`. See [Logging](#logging) for the other `LOG_*` settings. |

## Tests

```powershell
python -m pytest -q
```

The tests build a synthetic save, so no real save is needed. To also run the real-save tests,
set `TEST_TOGF_SAVE`. Those tests check that decoding and re-encoding an unedited save gives
back the same bytes, and that an edited slot is re-serialized in the game's own JSON format.

## Logging

The package logs with `loguru`. Logging is off when you import it as a library. To turn it on:

```python
from loguru import logger
logger.enable("togf_save")
```

The CLI and the web editor set logging up themselves:

- **Console:** the CLI logs with `-v` (INFO) or `-vv` (DEBUG). `togf-save serve` always logs to
  the console, at `LOG_CONSOLE_LEVEL`.
- **Log file:** with `LOG_ENABLED=true`, both also write to `LOG_DIR/LOG_FILE_NAME`
  (`logs/togf_save.log` by default). `logs/` is ignored by git.

Running `uvicorn togf_save.web.app:app` directly applies the same settings when the server
starts. Tests never write log files.

| Variable | Default | Meaning |
|---|---|---|
| `LOG_ENABLED` | `false` | Write a log file. |
| `LOG_DIR` | `logs` | Folder for log files, relative to where you run the command. |
| `LOG_FILE_NAME` | `togf_save.log` | Log file name. |
| `LOG_LEVEL` | `DEBUG` | Lowest level written to the file: `TRACE`, `DEBUG`, `INFO`, `SUCCESS`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_CONSOLE_LEVEL` | `INFO` | Lowest level `serve` prints to the console. The CLI uses `-v` / `-vv` instead. |
| `LOG_ROTATION` | `10 MB` | When to start a new file: a size (`10 MB`), an interval (`1 day`) or a time of day (`00:00`). |
| `LOG_RETENTION` | `14 days` | When to delete old files: an age (`14 days`) or a number of files to keep (`10`). |
| `LOG_COMPRESSION` | empty | Compress rotated files: `zip`, `gz`, `bz2`, `xz`, `tar.gz`, ... Empty means no compression. |
| `LOG_FORMAT` | time, level, module:function:line, message | File line format, as a loguru format string. |
| `LOG_SERIALIZE` | `false` | Write one JSON object per line instead of `LOG_FORMAT`. |
| `LOG_BACKTRACE` | `true` | Full stack trace on errors. |
| `LOG_DIAGNOSE` | `false` | Also print variable values in stack traces. They can include save data. |
| `LOG_ENQUEUE` | `true` | Write through a background queue, which is safe with the web server's threads. |

A blank value uses the default. An invalid value, such as `LOG_ROTATION=whenever`, stops the
command with an error that names the `LOG_*` setting.

## Usage

### Library

```python
from togf_save import read_save, write_save
from togf_save.native import NativeData, Shard

save = read_save("SaveDat000.sav")
print(save.slot1.get("listParam.playTime"))

native = NativeData(save.native)
native.set("item.consumable", 0, 15)               # table id, index, value
native.set_shard(0, Shard(type=1, nature=3, strength=10))  # keeps shard type counts in sync
save.native = native.to_bytes()

write_save(save, "SaveDat000.sav")  # first overwrite moves the original to SaveDat000.sav.bak
```

Table ids:

- `<character>.stat`, `<character>.arte`, `<character>.counter`, `<character>.together`, for
  asbel, sophie, hubert, cheria, malik and pascal. The character map, with how sure each field
  is, is in [docs/character-block.md](docs/character-block.md).
- `item.<category>` for consumable, dish, material, sellable and ingredient. See
  [docs/items.md](docs/items.md).
- `misc` for single values (gald). See [docs/misc.md](docs/misc.md).

Shards have their own API (`set_shard`, `shard_rows`, ...); their layout is in
[docs/shards.md](docs/shards.md). Data found in the save but not mapped yet is collected in
[docs/unused-findings.md](docs/unused-findings.md).

Offsets are in [togf_save/native/layout/](togf_save/native/layout/).

Some fields have flags:

- **Read-only** fields, such as stats and battles fought together, are only written with
  `set(..., force=True)`.
- **Hidden** fields, such as unknown counters, are left out of `rows()` unless you pass
  `show_hidden=True`.
- `set_all` and `set_all_max` only touch fields marked for bulk edits.

To edit with your own tools, `togf_save.folder` has `export_folder(save, dir)` and
`import_folder(dir)`. They use the same folder format as the CLI `decode` and `encode` commands.

### Command line

Run `togf-save <command> --help` for every option. You can also run it as
`python -m togf_save`. In the commands below:

- `SAVE` is the path to your `.sav` file.
- `NATIVE` is the `slot2.NativeData.bin` file inside a folder that `decode` created.

Editing takes three steps: decode the save to a folder, edit the `.bin` file, then encode the
folder back to a `.sav`.

```powershell
togf-save info   SAVE                         # layout, CRC and backup status
togf-save decode SAVE [OUTDIR]                # -> slot1.raw, slot1.json, slot2.json, slot2.*.bin
togf-save encode DIR  [OUT]                   # folds edited .bin files back in; OUT defaults to DIR.sav

togf-save table  [--show-hints]               # list tables (--show-hints: entry counts and caps)
togf-save table  NATIVE item.consumable       # index, offset, value, name
togf-save table  NATIVE asbel.stat --show-hints --show-hidden
togf-save table  NATIVE item.consumable --set 0=15 4=3
togf-save table  NATIVE asbel.arte --set-all 9999
togf-save table  NATIVE asbel.stat --set 2=80 --force   # write a read-only field

togf-save shards --types                      # every shard type and nature with its number
togf-save shards NATIVE [--all]               # used slots (--all: empty ones too)
togf-save shards NATIVE --set SLOT TYPE NATURE STRENGTH
togf-save shards NATIVE --clear SLOT | --clear-all | --fix-counts

togf-save serve  [--host HOST] [--port PORT]  # web editor, see below
```

Example:

```powershell
togf-save decode SaveDat000.sav                                  # -> SaveDat000\
togf-save table  SaveDat000\slot2.NativeData.bin item.consumable --set 0=30
togf-save encode SaveDat000                                      # -> SaveDat000.sav (original kept as .bak)
```

- `table` and `shards` change `NATIVE` in place, without a backup. To start over, decode again;
  the `.sav` is not touched until you encode.
- `-o OUT` writes the result to another file instead.
- `encode` moves an existing output file to `.bak` the first time it overwrites it.
- `-v` or `-vv` turns on logging, and `--lang` picks the language for names.

`table` options:

| Option | Effect |
|---|---|
| `--show-hints` | Adds hints at the end of each line, in one column. When listing tables, it adds entry counts and caps instead. |
| `--show-hidden` | Also lists hidden fields (marked as hidden), such as unknown counters. |
| `--force` | Lets `--set` and `--set-all` write read-only fields (marked as read-only). |

Value limits:

| Values | Limit |
|---|---|
| Arte counts | 0-9999 |
| Consumables | 0-30 |
| Other items | 0-15 |
| Level | 0-200 |
| HP, Max HP | 0-9999 |
| Attack, Arte Attack, Accuracy, Defense, Arte Defense, Evasion | 0-1999 |
| Combat counters | 0-9999 (u16) or 0-9999999 (u32) |

`--set-all max` sets every bulk-editable entry in a table to its limit. Read-only ones also need
`--force`. For battles fought together it is always refused.

**Unlocking titles:** set an arte usage count or a combat counter at or above a title's
threshold, then perform that action once in game. The character learns the title, if that
character has it. When a title has several thresholds, every passed one is learned at once.
For example, set Asbel's critical hits to 1500 and land one critical hit: he learns the 50, 300
and 1500 critical-hit titles together. See
[docs/character-block.md](docs/character-block.md#unlocking-titles).

Slot 1 holds the load-menu summary and thumbnail. The CLI has no commands to read or edit it.
To change it, edit `slot1.json` in the decoded folder by hand. `encode` uses the file as
written.

### Web editor

```powershell
togf-save serve [--host HOST] [--port PORT]
```

Then open http://127.0.0.1:8000. You can also start it with
`uvicorn togf_save.web.app:app`.

The page has these tabs:

| Tab | What it shows |
|---|---|
| Overview | Layout, CRC and backup status, warnings, and slot 1 (read only) |
| Items / Artes | One sub-tab per category or character, with a filter box and a "set all to max" button |
| Shards | Slots with type and nature dropdowns and a strength field. You can add a shard to the first empty slot, remove one, clear all, and fix the type counts when they don't match the slots. |
| Misc | Single values, each with its own offset, size and cap: gald (u32 at `0x76D4`, max 9999999). |

Each change is sent to the server immediately. A rejected value shows the error and goes back to
its old value. The language dropdown switches all text, and the choice is remembered in the
browser.

- Uploading a save opens an editing session. Sessions are kept in server memory, and your
  file on disk is never changed.
- Edits apply to the session.
- Downloading gives you the re-encoded `.sav`, with the original file name.
- The API docs are at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Languages, characters with their tables, other table groups (with max values and whether "set all" applies), shard types and natures |
| POST | `/api/sessions` | Upload a `.sav` (multipart field `file`). Returns the session summary. |
| GET / DELETE | `/api/sessions/{id}` | Session summary (layout, CRC status, warnings, modified) / close the session |
| GET | `/api/sessions/{id}/download` | Re-encoded `.sav` |
| GET | `/api/sessions/{id}/slot1` | Slot 1 JSON, read only |
| GET / PATCH | `/api/sessions/{id}/tables/{table_id}` | Read rows, with flags and hints (`?show_hidden=true` adds hidden rows) / edit with `{"set": {index: value}}` or `{"set_all": value \| "max"}`, plus `"force": true` to write read-only fields. A rejected edit changes nothing. |
| GET | `/api/sessions/{id}/shards` | All slots, used count, count mismatches |
| PUT / DELETE | `/api/sessions/{id}/shards/{slot}` | Set a shard with `{"type", "nature", "strength"}` / empty a slot |
| POST | `/api/sessions/{id}/shards/clear`, `.../fix-counts` | Empty every slot / make the per-type counts match the slots |
| GET / PUT | `/api/sessions/{id}/native/hex` | Read raw NativeData bytes (`offset`, `length`) / write them with `{"offset", "hex"}` |

Name endpoints take `?lang=`. Invalid edits return 422 with a `detail` message, and unknown
sessions or tables return 404.

## Project layout

```
togf_save/
  crypto.py        AES key derivation, encrypt/decrypt
  container.py     slot layout, CRCs, backups
  codec.py         decode .sav -> SaveData, encode SaveData -> .sav
  native/          NativeData (game state)
    layout/        field map: characters, items, misc, shards
    editor.py      read and edit tables
    shards.py      shard slots
  locales/         names and interface text per language
  cli.py           command line
  logsetup.py      logging setup from LOG_* variables
  web/             FastAPI app + static frontend
    routes/        API routes, one module per group
docs/
  character-block.md   per-character data map
  items.md             item counts
  misc.md              single values (gald) and values coming soon
  shards.md            shard slots and per-type counts
  unused-findings.md   data found but not mapped yet
tests/
```

## Localization

Each language is a folder in `togf_save/locales/` with two files:

| File | Contents |
|---|---|
| `<lang>/names.json` | Data names by stable ID, such as `item.consumable.0`, `asbel.arte.3` or `shard.type.1`, and names shared between characters, such as `stat.attack` or `section.stats`. The field map never hard-codes names. |
| `<lang>/ui.json` | Interface text shared by the CLI and the website (`str.format` templates), plus `language.name` and the field hints (`hint.*`). |

- **Languages:** `zh-Hant`, `en` and `ja`.
- **Fallback:** a missing key falls back to `ja`, and then to the key itself. `ja` must have
  every key that any other language has; a test checks this. Entries the game data doesn't name
  yet show their ID.
- **Adding a language:** add a folder with either or both files.
- **Choosing the language:** `--lang` in the CLI, the language dropdown on the website, or
  `DEFAULT_LANG` for both.
- **Not translated:** CLI `--help` text and library error messages are English only.

## Save format (summary)

| Range | Content |
|---|---|
| `0x00000-0x61000` | slot 1: `[u32 len][u32 crc32][AES body]`, then an ignored stale tail and zero padding |
| `0x61000-0xC2000` | backup of slot 1 |
| `0xC2000-0xDD000` | slot 2: `[u32 len][u32 crc32][AES body]`, then zero padding |
| `0xDD000-EOF` | backup of slot 2 (unpadded) |

- Bodies are AES-128-CBC with PKCS7 padding.
- The key and IV come from PBKDF2-SHA1 with 1000 rounds.
- The plaintext is JSON, and binary fields are base64.
- Slot 1 holds the load-menu summary and thumbnail.
- Slot 2 holds `NativeData` (the game state) and `NobleData` (remaster data).
