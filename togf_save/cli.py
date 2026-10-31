"""Command line for the save editor: `togf-save <command> ...` or `python -m togf_save ...`.

Workflow: `decode` a save to a folder, edit its slot2.NativeData.bin with `table` /
`shards` (in place, or to -o OUT), then `encode` the folder back to a .sav.
"""
import argparse
import sys
from pathlib import Path

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


def _load_native(a) -> NativeData:
    if not a.native:
        raise SaveError("give the NATIVE file (slot2.NativeData.bin)")
    return NativeData(Path(a.native).read_bytes())


def _write_native(a, native: NativeData) -> None:
    out = Path(a.output or a.native)
    out.write_bytes(native.to_bytes())
    print(f"wrote {out}")


# --- commands ---

def cmd_info(a) -> None:
    data = Path(a.save).read_bytes()
    info = container.parse(data).info()
    print(f"file size  {info['file_size']:#x}")
    for slot in info["slots"]:
        print(f"slot{slot['slot']}  backup identical: {slot['backup_identical']}")
        for c in slot["copies"]:
            if "error" in c:
                print(f"  {c['copy']:<8} @{c['offset']:#07x}  ERROR {c['error']}")
            else:
                print(f"  {c['copy']:<8} @{c['offset']:#07x}  len {c['length']:#x}  "
                      f"crc {c['crc']:#010x} {'ok' if c['crc_ok'] else 'BAD'}")
    save = read_save(a.save)
    for w in save.warnings:
        print(f"warning: {w}")
    for path in save.slot2.binary_paths:
        print(f"slot2.{'.'.join(path)}  {len(save.slot2.get_binary(path))} bytes")


def cmd_decode(a) -> None:
    save = read_save(a.save)
    outdir = Path(a.outdir) if a.outdir else Path(a.save).with_suffix("")
    for f in export_folder(save, outdir):
        print(f"{f}  {f.stat().st_size} bytes")
    print(f"decoded {a.save} -> {outdir}")


def cmd_encode(a) -> None:
    save = import_folder(a.dir)
    for w in save.warnings:
        print(f"warning: {w}")
    out = Path(a.out) if a.out else Path(a.dir).with_suffix(".sav")
    bak = write_save(save, out)
    if bak:
        print(f"backed up existing -> {bak}")
    print(f"wrote {out}")


def cmd_table(a) -> None:
    if not a.table_id:
        if a.native in L.TABLES:  # `table item.dish`: the id landed in the optional NATIVE slot
            raise SaveError(f"give the NATIVE file before {a.native}")
        if a.set or a.set_all is not None:
            raise SaveError("give a TABLE_ID to edit")
        for group, ids in L.GROUPS.items():
            print(i18n.name(f"group.{group}", a.lang))
            for tid in ids:
                t = get_table(tid)
                print(f"  {tid:<18} {i18n.name(t.name_key or tid, a.lang)}  ({t.count} entries, max {t.max_value})")
        return

    t = get_table(a.table_id)
    native = _load_native(a)
    if not a.set and a.set_all is None:
        for row in native.rows(a.table_id, a.lang):
            print(f"{row['index']:4}  {row['offset']:#07x}  {row['value']:>5}  {row['name']}")
        return

    edits = [(i, a.set_all) for i in range(t.count)] if a.set_all is not None else a.set
    for index, value in edits:
        old = native.get(a.table_id, index)
        native.set(a.table_id, index, value)
        if old != value:
            print(f"{t.entry_id(index)}  {i18n.name(t.entry_id(index), a.lang)}: {old} -> {value}")
    _write_native(a, native)


def _shard_line(row: dict) -> str:
    head = f"{row['slot']:4}  {row['offset']:#07x}  {row['raw']}  "
    if "error" in row:
        return head + f"ERROR {row['error']}"
    s = row["shard"]
    if s is None:
        return head + "-"
    return head + f"{s['type_name']} ({s['type']})  {s['nature_name']} ({s['nature']})  {s['strength']}"


def _print_shard_values(lang: str) -> None:
    for title, prefix, top in ((i18n.name("shard.field.type", lang), "shard.type", L.SHARD_TYPES),
                               (i18n.name("shard.field.nature", lang), "shard.nature", L.SHARD_NATURES)):
        print(f"{title} (1-{top})")
        for n in range(1, top + 1):
            print(f"  {n:3}  {i18n.name(f'{prefix}.{n}', lang)}")
    print(f"{i18n.name('shard.field.strength', lang)} (1-{L.SHARD_MAX_STRENGTH})")


def cmd_shards(a) -> None:
    if a.types:
        _print_shard_values(a.lang)
        return
    native = _load_native(a)
    if a.set:
        slot, *values = a.set
        native.set_shard(slot, Shard(*values))
        print(_shard_line(native.shard_rows(a.lang)[slot]))
    elif a.clear is not None:
        native.set_shard(a.clear, None)
        print(f"cleared slot {a.clear}")
    elif a.clear_all:
        native.clear_shards()
        print(f"cleared all {L.SHARD_SLOTS} slots")
    elif a.fix_counts:
        for t, (stored, actual) in native.shard_count_mismatches().items():
            print(f"type {t} {i18n.name(f'shard.type.{t}', a.lang)}: count {stored} -> {actual}")
        native.fix_shard_counts()
    else:
        rows = native.shard_rows(a.lang)
        shown = [r for r in rows if a.all or r["shard"] or "error" in r]
        for row in shown:
            print(_shard_line(row))
        print(f"{sum(1 for r in rows if r['shard'])}/{L.SHARD_SLOTS} slots used")
        for t, (stored, actual) in native.shard_count_mismatches().items():
            print(f"warning: type {t} count byte is {stored}, but {actual} slots hold it (--fix-counts)")
        return
    _write_native(a, native)


# --- argument parsing ---

def _index_value(text: str) -> tuple[int, int]:
    try:
        index, value = text.split("=")
        return int(index, 0), int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected INDEX=VALUE, got {text!r}") from None


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="count", default=0, help="-v: log steps, -vv: debug details")
    common.add_argument("--lang", default=i18n.DEFAULT_LANG, choices=list(i18n.available()),
                        help=f"language for names (default {i18n.DEFAULT_LANG})")
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

    p = sub.add_parser("table", parents=[common, edit], help="list or edit arte / item counts in NativeData.bin")
    p.add_argument("table_id", metavar="TABLE_ID", nargs="?", help="e.g. item.consumable; omit to list tables")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--set", nargs="+", type=_index_value, metavar="INDEX=VALUE", help="set entries")
    g.add_argument("--set-all", type=int, metavar="VALUE", help="set every entry")
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
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    _setup(a.verbose)
    try:
        a.func(a)
    except (SaveError, ValueError, IndexError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 1
    return 0
