"""Command line for the save editor: `togf-save <command> ...` or `python -m togf_save ...`.

Workflow: `decode` a save to a folder, edit its slot2.NativeData.bin with `table` /
`shards` (in place, or to -o OUT), then `encode` the folder back to a .sav.

Output text comes from togf_save/locales/<lang>/ui.json (--lang, or $DEFAULT_LANG).
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from . import container, i18n
from .codec import read_save, write_save
from .errors import SaveError
from .folder import export_folder, import_folder
from .native import NativeData, Shard, layout as L, table as get_table


def _setup(verbose: int) -> None:
    for stream in (sys.stdout, sys.stderr):  # names are CJK; Windows consoles default to cp950/cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # not a TextIOWrapper (e.g. redirected in tests)
            pass
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="DEBUG" if verbose > 1 else "INFO", format="<level>{level: <7}</level> {message}")
        logger.enable("togf_save")


def _t(a, key: str, **values) -> str:
    return i18n.text(key, a.lang, **values)


def _load_native(a) -> NativeData:
    if not a.native:
        raise SaveError(_t(a, "native.missing"))
    return NativeData(Path(a.native).read_bytes())


def _write_native(a, native: NativeData) -> None:
    out = Path(a.output or a.native)
    out.write_bytes(native.to_bytes())
    print(_t(a, "common.wrote", path=out))


# --- commands ---

def cmd_info(a) -> None:
    data = Path(a.save).read_bytes()
    info = container.parse(data).info()
    print(_t(a, "info.file_size", size=f"{info['file_size']:#x}"))
    for slot in info["slots"]:
        same = _t(a, "common.yes" if slot["backup_identical"] else "common.no")
        print(_t(a, "info.slot", slot=slot["slot"], same=same))
        for c in slot["copies"]:
            head = f"  {_t(a, 'info.copy.' + c['copy']):<8} @{c['offset']:#07x}  "
            if "error" in c:
                print(head + _t(a, "common.invalid", message=c["error"]))
            else:
                status = _t(a, "info.crc_ok" if c["crc_ok"] else "info.crc_bad")
                print(head + _t(a, "info.record", length=f"{c['length']:#x}", crc=f"{c['crc']:#010x}",
                                status=status))
    save = read_save(a.save)
    for w in save.warnings:
        print(_t(a, "common.warning", message=w))
    for path in save.slot2.binary_paths:
        print(f"slot2.{'.'.join(path)}  " + _t(a, "common.bytes", n=len(save.slot2.get_binary(path))))


def cmd_decode(a) -> None:
    save = read_save(a.save)
    outdir = Path(a.outdir) if a.outdir else Path(a.save).with_suffix("")
    for f in export_folder(save, outdir):
        print(f"{f}  " + _t(a, "common.bytes", n=f.stat().st_size))
    print(_t(a, "decode.done", save=a.save, outdir=outdir))


def cmd_encode(a) -> None:
    save = import_folder(a.dir)
    for w in save.warnings:
        print(_t(a, "common.warning", message=w))
    out = Path(a.out) if a.out else Path(a.dir).with_suffix(".sav")
    bak = write_save(save, out)
    if bak:
        print(_t(a, "common.backed_up", path=bak))
    print(_t(a, "common.wrote", path=out))


def cmd_table(a) -> None:
    if not a.table_id:
        if a.native in L.TABLES:  # `table item.dish`: the id landed in the optional NATIVE slot
            raise SaveError(_t(a, "table.native_first", table=a.native))
        if a.set or a.set_all is not None:
            raise SaveError(_t(a, "table.need_id"))
        for group, ids in L.GROUPS.items():
            print(_t(a, f"group.{group}"))
            for tid in ids:
                t = get_table(tid)
                summary = (_t(a, "table.summary_count", count=t.count) if t.max_value is None
                           else _t(a, "table.summary", count=t.count, max=t.max_value))
                print(f"  {tid:<18} {i18n.name(t.name_key or tid, a.lang)}  {summary}")
        return

    t = get_table(a.table_id)
    native = _load_native(a)
    if not a.set and a.set_all is None:
        for row in native.rows(a.table_id, a.lang):
            print(f"{row['index']:4}  {row['offset']:#07x}  {row['value']:>5}  {row['name']}")
        return

    if a.set_all is not None:
        edits = [(i, t.max_of(i) if a.set_all == "max" else a.set_all) for i in range(t.count)]
    else:
        edits = a.set
    for index, value in edits:
        old = native.get(a.table_id, index)
        native.set(a.table_id, index, value)
        if old != value:
            print(f"{t.entry_id(index)}  {i18n.name(t.entry_id(index), a.lang)}: {old} -> {value}")
    _write_native(a, native)


def _shard_line(a, row: dict) -> str:
    head = f"{row['slot']:4}  {row['offset']:#07x}  {row['raw']}  "
    if "error" in row:
        return head + _t(a, "common.invalid", message=row["error"])
    s = row["shard"]
    if s is None:
        return head + "-"
    return head + f"{s['type_name']} ({s['type']})  {s['nature_name']} ({s['nature']})  {s['strength']}"


def _print_shard_values(a) -> None:
    for field, top in (("type", L.SHARD_TYPES), ("nature", L.SHARD_NATURES)):
        print(f"{_t(a, f'shard.field.{field}')} (1-{top})")
        for n in range(1, top + 1):
            print(f"  {n:3}  {i18n.name(f'shard.{field}.{n}', a.lang)}")
    print(f"{_t(a, 'shard.field.strength')} (1-{L.SHARD_MAX_STRENGTH})")


def cmd_shards(a) -> None:
    if a.types:
        _print_shard_values(a)
        return
    native = _load_native(a)
    if a.set:
        slot, *values = a.set
        native.set_shard(slot, Shard(*values))
        print(_shard_line(a, native.shard_rows(a.lang)[slot]))
    elif a.clear is not None:
        native.set_shard(a.clear, None)
        print(_t(a, "shards.cleared", slot=a.clear))
    elif a.clear_all:
        native.clear_shards()
        print(_t(a, "shards.cleared_all", slots=L.SHARD_SLOTS))
    elif a.fix_counts:
        for t, (stored, actual) in native.shard_count_mismatches().items():
            print(_t(a, "shards.count_fixed", type=t, name=i18n.name(f"shard.type.{t}", a.lang),
                     old=stored, new=actual))
        native.fix_shard_counts()
    else:
        rows = native.shard_rows(a.lang)
        for row in rows:
            if a.all or row["shard"] or "error" in row:
                print(_shard_line(a, row))
        print(_t(a, "shards.used", used=sum(1 for r in rows if r["shard"]), slots=L.SHARD_SLOTS))
        for t, (stored, actual) in native.shard_count_mismatches().items():
            print(_t(a, "common.warning",
                     message=_t(a, "shards.mismatch", type=t, stored=stored, actual=actual)))
        return
    _write_native(a, native)


def cmd_serve(a) -> None:
    import uvicorn

    from .web.app import create_app

    logger.enable("togf_save")
    if not a.verbose:
        logger.add(sys.stderr, level="INFO", format="<level>{level: <7}</level> {message}")
    print(_t(a, "serve.banner", url=f"http://{a.host}:{a.port}"))
    uvicorn.run(create_app(), host=a.host, port=a.port)


# --- argument parsing (help text is English only: it is built before --lang is known) ---

def _index_value(text: str) -> tuple[int, int]:
    try:
        index, value = text.split("=")
        return int(index, 0), int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected INDEX=VALUE, got {text!r}") from None


def _value_or_max(text: str) -> int | str:
    if text == "max":
        return text
    try:
        return int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number or 'max', got {text!r}") from None


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="count", default=0, help="-v: log steps, -vv: debug details")
    common.add_argument("--lang", default=i18n.default_lang(), choices=list(i18n.available()),
                        help=f"language for names and messages (default: $DEFAULT_LANG or {i18n.FALLBACK_LANG})")
    edit = argparse.ArgumentParser(add_help=False)
    edit.add_argument("-o", "--output", metavar="OUT", help="write here instead of changing NATIVE in place")
    edit.add_argument("native", metavar="NATIVE", nargs="?",
                      help="slot2.NativeData.bin from a decoded folder (not needed to list tables / types)")

    ap = argparse.ArgumentParser(prog="togf-save", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", parents=[common], help="container layout, CRC and backup status")
    p.add_argument("save", metavar="SAVE", help="path to a SaveDat*.sav")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("decode", parents=[common], help="write a decoded folder (slot1.raw, slot1.json, slot2.json, .bin files)")
    p.add_argument("save", metavar="SAVE", help="path to a SaveDat*.sav")
    p.add_argument("outdir", metavar="OUTDIR", nargs="?", help="default: SAVE without its extension")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("encode", parents=[common], help="build a .sav from a decoded folder, folding in edited .bin")
    p.add_argument("dir", metavar="DIR", help="decoded folder")
    p.add_argument("out", metavar="OUT", nargs="?",
                   help="default: DIR.sav (an existing file is moved to .bak the first time)")
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("table", parents=[common, edit], help="list or edit arte / item / misc values in NativeData.bin")
    p.add_argument("table_id", metavar="TABLE_ID", nargs="?", help="e.g. item.consumable; omit to list tables")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--set", nargs="+", type=_index_value, metavar="INDEX=VALUE", help="set entries")
    g.add_argument("--set-all", type=_value_or_max, metavar="VALUE|max",
                   help="set every entry to VALUE, or to the table's max")
    p.set_defaults(func=cmd_table)

    p = sub.add_parser("shards", parents=[common, edit], help="list or edit shards in NativeData.bin")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="list empty slots too")
    g.add_argument("--types", action="store_true", help="list every shard type and nature with its number")
    g.add_argument("--set", nargs=4, type=int, metavar=("SLOT", "TYPE", "NATURE", "STRENGTH"),
                   help=f"put a shard in a slot (type 1-{L.SHARD_TYPES}, nature 1-{L.SHARD_NATURES}, "
                        f"strength 1-{L.SHARD_MAX_STRENGTH})")
    g.add_argument("--clear", type=int, metavar="SLOT", help="empty one slot")
    g.add_argument("--clear-all", action="store_true", help="empty every slot")
    g.add_argument("--fix-counts", action="store_true", help="make the per-type counts match the slots")
    p.set_defaults(func=cmd_shards)

    p = sub.add_parser("serve", parents=[common], help="start the web editor")
    p.add_argument("--host", default=os.environ.get("WEB_HOST", "127.0.0.1"),
                   help="default: $WEB_HOST or 127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("WEB_PORT", "8000")),
                   help="default: $WEB_PORT or 8000")
    p.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    a = build_parser().parse_args(argv)
    _setup(a.verbose)
    try:
        a.func(a)
    except (SaveError, ValueError, IndexError, OSError) as e:
        print(_t(a, "common.error", message=e), file=sys.stderr)
        return 1
    except KeyError as e:
        print(_t(a, "common.error", message=e.args[0]), file=sys.stderr)
        return 1
    return 0
