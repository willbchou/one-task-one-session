"""Memory check: the machine's memory, the Claude app's governor and every live session process, with snapshots to compare.

    python memory_check.py status [--no-save] [--no-events]
    python memory_check.py compare [<a.json>] [<b.json>]
    python memory_check.py snapshots
    python memory_check.py selftest

status reads, in one PowerShell pass, what Task Manager's Performance tab shows (total, available, committed, the
commit limit, the page file and the hard-fault rate), Windows' own low-virtual-memory events of the last seven days
(Event 2004), every Claude Code session process (claude.exe under claude-code\\) with the processes it spawned, and the
eight other process names holding the most commit. It adds the app governor's pressure lines of the day from the app's
main log, names each session process by its transcript (the session id the process was resumed with, the transcript's
folder and its first prompt), prints the report and saves it as a snapshot under ~/.claude/memory-check/. compare puts
two snapshots side by side by process (the two latest by default). Nothing here pauses, archives or closes anything.
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = Path.home() / ".claude" / "memory-check"
PROJECTS = Path.home() / ".claude" / "projects"
APP_LOGS = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Claude" / "Logs"

# The app's CliGovernor, as read from the app bundle (app.asar); a release may change these figures: polled
# every 10 s, ratio = min(available / total RAM, commit available / commit limit); warning below 5 percent,
# critical below 2 percent; the cap on live CLI processes is max(6, RAM / 3 GiB); a session with Remote
# Control on is exempt from eviction while the live count is over the cap.
WARNING_RATIO = 0.05
CRITICAL_RATIO = 0.02

GOVERNOR = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[\w+\] \[CliGovernor\] memory pressure \((warning|critical)\): "
    r"(?:evicted (\d+) of |would evict )(\d+) idle session\(s\), (\d+) effective"
)

PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$withEvents = $args.Count -eq 0 -or $args[0] -ne 'no-events'
$all = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine, PrivatePageCount, WorkingSetSize, CreationDate
$byParent = @{}
foreach ($p in $all) { $k = [int]$p.ParentProcessId; if (-not $byParent.ContainsKey($k)) { $byParent[$k] = @() }; $byParent[$k] += $p }
$cli = @($all | Where-Object { $_.Name -eq 'claude.exe' -and $_.CommandLine -match 'claude-code\\' })
$rows = @()
foreach ($p in $cli) {
  $kids = @(); $queue = @([int]$p.ProcessId)
  while ($queue.Count -gt 0) {
    $cur = $queue[0]; $queue = @($queue | Select-Object -Skip 1)
    if ($byParent.ContainsKey($cur)) { foreach ($c in $byParent[$cur]) { $kids += $c; $queue += [int]$c.ProcessId } }
  }
  $sid = ''; if ($p.CommandLine -match '--resume=([0-9a-f]{8})') { $sid = $Matches[1] }
  $starter = ''; if ($p.CommandLine -match 'side-session-notes\\local_([0-9a-f]{8})') { $starter = $Matches[1] }
  $root = ''; if ($p.CommandLine -match '--project-config-root "([^"]+)"') { $root = $Matches[1] }
  $kidSum = 0; if ($kids.Count -gt 0) { $kidSum = ($kids | Measure-Object PrivatePageCount -Sum).Sum }
  $kidNames = ''
  if ($kids.Count -gt 0) { $kidNames = (($kids | Where-Object { $_.Name -ne 'conhost.exe' } | Group-Object Name | ForEach-Object { "$($_.Name -replace '\.exe$','')x$($_.Count)" }) -join ' ') }
  $rows += [pscustomobject]@{ pid = [int]$p.ProcessId; cli = $sid; starter = $starter; root = $root; started = $p.CreationDate.ToString('yyyy-MM-dd HH:mm'); self_mb = [math]::Round($p.PrivatePageCount/1MB); ws_mb = [math]::Round($p.WorkingSetSize/1MB); kids_mb = [math]::Round($kidSum/1MB); kids = $kidNames }
}
$groups = @($all | Where-Object { $_.Name -ne 'claude.exe' } | Group-Object Name | ForEach-Object { [pscustomobject]@{ name = ($_.Name -replace '\.exe$',''); count = $_.Count; private_mb = [math]::Round((($_.Group | Measure-Object PrivatePageCount -Sum).Sum)/1MB) } } | Sort-Object private_mb -Descending | Select-Object -First 8)
$os = Get-CimInstance Win32_OperatingSystem
$pf = Get-CimInstance Win32_PageFileUsage | Select-Object -First 1
$c = Get-Counter -Counter '\Memory\Committed Bytes','\Memory\Commit Limit','\Memory\Available MBytes','\Memory\Pages Input/sec' -SampleInterval 1 -MaxSamples 2
$last = $c[-1].CounterSamples
function V($pat) { ($last | Where-Object Path -like $pat).CookedValue }
$sys = @{ total_gb = [math]::Round($os.TotalVisibleMemorySize/1MB, 1); available_gb = [math]::Round((V '*Available*')/1024, 1); committed_gb = [math]::Round((V '*Committed*')/1GB, 1); commit_limit_gb = [math]::Round((V '*Commit Limit*')/1GB, 1); pages_in_per_s = [math]::Round((V '*Pages Input*')); pagefile_mb = $pf.AllocatedBaseSize; pagefile_used_mb = $pf.CurrentUsage; pagefile_peak_mb = $pf.PeakUsage }
$events = @{ count_7d = -1; last = '' }
if ($withEvents) {
  $ev = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector'; StartTime=(Get-Date).AddDays(-7)})
  $events.count_7d = $ev.Count
  if ($ev.Count -gt 0) { $e = $ev | Sort-Object TimeCreated -Descending | Select-Object -First 1; $events.last = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm') + ' ' + (($e.Message -split "`n")[0]).Trim() }
}
@{ taken = (Get-Date).ToString('yyyy-MM-dd HH:mm'); system = $sys; events = $events; procs = $rows; others = $groups } | ConvertTo-Json -Depth 5
"""


# ---------------------------------------------------------------- reading


def run_powershell(with_events=True):
    """Run the PowerShell pass from a temporary file and return its JSON as a dict."""
    fd, path = tempfile.mkstemp(prefix="memory-check-", suffix=".ps1")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(PS_SCRIPT)
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", path]
        if not with_events:
            cmd.append("no-events")
        out = subprocess.run(cmd, capture_output=True, timeout=180)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    text = out.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
    start = text.find("{")
    if out.returncode != 0 or start < 0:
        raise SystemExit("powershell pass failed: %s" % out.stderr.decode("utf-8", errors="replace")[:400])
    return json.loads(text[start:])


def parse_governor(lines, day):
    """Count the app governor's pressure lines of one day; return counts and the last line's reading."""
    out = {"day": day, "warning": 0, "critical": 0, "last": None}
    for line in lines:
        m = GOVERNOR.match(line)
        if not m or m.group(1) != day:
            continue
        out[m.group(3)] += 1
        out["last"] = {
            "time": m.group(2)[:5],
            "level": m.group(3),
            "evicted": int(m.group(4)) if m.group(4) is not None else None,
            "idle": int(m.group(5)),
            "effective": int(m.group(6)),
        }
    return out


def read_app_log(day, logs=None):
    """The governor's lines of the day from the app's main log and its first rotation."""
    logs = APP_LOGS if logs is None else logs
    lines = []
    for name in ("main1.log", "main.log"):
        p = Path(logs) / name
        if p.exists():
            with open(p, encoding="utf-8", errors="replace") as f:
                lines.extend(l for l in f if "[CliGovernor] memory pressure" in l)
    return parse_governor(lines, day)


def lookup_transcript(cli8, projects=None):
    """The transcript a session process was resumed from: (folder, last write, first prompt), or None."""
    projects = PROJECTS if projects is None else Path(projects)
    if not cli8:
        return None
    hits = sorted(glob.glob(str(projects / "*" / (cli8 + "*.jsonl"))), key=os.path.getmtime, reverse=True)
    if not hits:
        return None
    h = hits[0]
    first = ""
    with open(h, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"type":"user"' in line:
                m = re.search(r'"content":"([^"]{0,80})', line)
                if m and m.group(1).startswith("<system-reminder>"):
                    continue
                first = m.group(1) if m else ""
                break
    folder = os.path.basename(os.path.dirname(h))
    folder = re.sub(r"^C--", "", folder)
    return {"folder": folder, "last": dt.datetime.fromtimestamp(os.path.getmtime(h)).strftime("%H:%M"), "first": first}


def name_procs(snap, projects=None):
    for p in snap["procs"]:
        t = lookup_transcript(p.get("cli", ""), projects)
        if t:
            p["title"] = t["first"] or t["folder"]
        elif p.get("cli"):
            p["title"] = p["cli"]
        elif p.get("starter"):
            root = os.path.basename(p.get("root") or "")
            p["title"] = "started by %s%s" % (p["starter"], (", in " + root) if root else "")
        else:
            p["title"] = "no session id on the command line (a session the app started fresh)"
        p["folder"] = t["folder"] if t else ""
        p["last"] = t["last"] if t else ""
        p["total_mb"] = int(p["self_mb"]) + int(p["kids_mb"])


# ---------------------------------------------------------------- rendering


def gb(mb):
    return "%.1f" % (mb / 1024.0)


def render_status(snap):
    s = snap["system"]
    lines = []
    lines.append("memory check %s" % snap["taken"])
    ratio = min(s["available_gb"] / max(s["total_gb"], 0.1), (s["commit_limit_gb"] - s["committed_gb"]) / max(s["commit_limit_gb"], 0.1))
    level = "critical" if ratio < CRITICAL_RATIO else "warning" if ratio < WARNING_RATIO else "clear"
    lines.append("  RAM %s GB, available %s GB; committed %s of %s GB; page file %s GB (%s GB used, peak %s GB); hard faults %s pages/s"
                 % (s["total_gb"], s["available_gb"], s["committed_gb"], s["commit_limit_gb"], gb(s["pagefile_mb"] or 0),
                    gb(s["pagefile_used_mb"] or 0), gb(s["pagefile_peak_mb"] or 0), s["pages_in_per_s"]))
    lines.append("  app governor reading now: %s (ratio %.3f; warning below %.2f, critical below %.2f)" % (level, ratio, WARNING_RATIO, CRITICAL_RATIO))
    g = snap.get("governor") or {}
    if g:
        last = g.get("last")
        tail = ("; last at %s: %s, %s idle session(s)%s, %s effective" % (
            last["time"], last["level"], last["idle"],
            "" if last["evicted"] is None else " (evicted %s)" % last["evicted"], last["effective"])) if last else ""
        lines.append("  app governor today (%s): %s warning, %s critical%s" % (g["day"], g["warning"], g["critical"], tail))
    e = snap.get("events") or {}
    if e.get("count_7d", -1) >= 0:
        lines.append("  Windows low-virtual-memory events (2004), 7 days: %s%s" % (e["count_7d"], ("; last " + e["last"]) if e.get("last") else ""))
    procs = sorted(snap["procs"], key=lambda p: -p["total_mb"])
    total = sum(p["total_mb"] for p in procs)
    lines.append("  Claude session processes: %d, holding %s GB of commit (process plus what it spawned)" % (len(procs), gb(total)))
    lines.append("  %-6s %-11s %6s %6s %6s  %-16s %-6s %s" % ("pid", "session", "GB", "self", "kids", "started", "last", "transcript's first prompt | spawned"))
    for p in procs:
        session = p.get("cli") or (("by " + p["starter"]) if p.get("starter") else "-")
        lines.append("  %-6s %-11s %6s %6s %6s  %-16s %-6s %s | %s" % (
            p["pid"], session, gb(p["total_mb"]), p["self_mb"], p["kids_mb"], p["started"], p.get("last") or "-",
            (p.get("title") or "")[:60], p.get("kids") or "-"))
    others = snap.get("others") or []
    if others:
        lines.append("  other process names by commit: " + ", ".join("%s x%s %s GB" % (o["name"], o["count"], gb(o["private_mb"])) for o in others))
    return "\n".join(lines)


def render_compare(a, b):
    """Two snapshots side by side by process id; a is the earlier one."""
    lines = []
    sa, sb = a["system"], b["system"]
    lines.append("%-26s %10s %10s" % ("", a["taken"], b["taken"]))
    for key, label in (("committed_gb", "committed GB"), ("available_gb", "available GB"), ("pages_in_per_s", "hard faults /s")):
        lines.append("%-26s %10s %10s" % (label, sa.get(key, "-"), sb.get(key, "-")))
    pa = {str(p["pid"]): p for p in a["procs"]}
    pb = {str(p["pid"]): p for p in b["procs"]}
    lines.append("%-26s %10s %10s" % ("session processes", len(pa), len(pb)))
    lines.append("%-26s %10s %10s" % ("held by them, GB", gb(sum(p["total_mb"] for p in pa.values())), gb(sum(p["total_mb"] for p in pb.values()))))
    lines.append("")
    lines.append("%-6s %-8s %7s %7s %7s  %s" % ("pid", "session", "before", "now", "change", "transcript's first prompt | spawned now"))
    rows = []
    for pid, p in pa.items():
        q = pb.get(pid)
        before = p["total_mb"]
        now = q["total_mb"] if q else None
        rows.append((before, pid, p.get("cli") or "-", before, now, (p.get("title") or "")[:50], (q.get("kids") if q else "") or ""))
    for pid, q in pb.items():
        if pid not in pa:
            rows.append((q["total_mb"], pid, q.get("cli") or "-", None, q["total_mb"], (q.get("title") or "")[:50], q.get("kids") or ""))
    for _, pid, cli, before, now, title, kids in sorted(rows, key=lambda r: -r[0]):
        b_s = gb(before) if before is not None else "new"
        n_s = gb(now) if now is not None else "gone"
        if before is None:
            d_s = "%+.1f" % (now / 1024.0)
        elif now is None:
            d_s = "%+.1f" % (-before / 1024.0)
        else:
            d_s = "%+.1f" % ((now - before) / 1024.0)
        lines.append("%-6s %-8s %7s %7s %7s  %s | %s" % (pid, cli, b_s, n_s, d_s, title, kids or "-"))
    return "\n".join(lines)


# ---------------------------------------------------------------- snapshots


def save_snapshot(snap, store=None):
    store = STORE if store is None else Path(store)
    store.mkdir(parents=True, exist_ok=True)
    name = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"
    path = store / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    return path


def list_snapshots(store=None):
    store = STORE if store is None else Path(store)
    if not store.exists():
        return []
    return sorted(store.glob("*.json"))


def load_snapshot(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


# ---------------------------------------------------------------- commands


def cmd_status(ns):
    snap = run_powershell(with_events=not ns.no_events)
    snap["governor"] = read_app_log(dt.date.today().isoformat())
    name_procs(snap)
    print(render_status(snap))
    if not ns.no_save:
        print("snapshot: %s" % save_snapshot(snap))
    return 0


def cmd_compare(ns):
    snaps = list_snapshots()
    if ns.a and ns.b:
        a, b = Path(ns.a), Path(ns.b)
    elif ns.a:
        if not snaps:
            raise SystemExit("no saved snapshot to compare against; run status first")
        a, b = Path(ns.a), snaps[-1]
    else:
        if len(snaps) < 2:
            raise SystemExit("fewer than two saved snapshots; run status twice")
        a, b = snaps[-2], snaps[-1]
    print(render_compare(load_snapshot(a), load_snapshot(b)))
    return 0


def cmd_snapshots(ns):
    snaps = list_snapshots()
    if not snaps:
        print("no snapshots under %s" % STORE)
        return 0
    for p in snaps:
        try:
            s = load_snapshot(p)
            print("%s  %s  committed %s GB, available %s GB, %d session processes" % (
                p.name, s["taken"], s["system"]["committed_gb"], s["system"]["available_gb"], len(s["procs"])))
        except (OSError, ValueError, KeyError):
            print("%s  (unreadable)" % p.name)
    return 0


# ---------------------------------------------------------------- selftest


def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    tmp = Path(tempfile.mkdtemp(prefix="memory-check-selftest-"))
    try:
        # the governor's lines of one day, counted, the last one read
        lines = [
            "2026-10-22 23:59:00 [warn] [CliGovernor] memory pressure (critical): evicted 0 of 0 idle session(s), 23 effective\n",
            "2026-10-23 08:36:28 [warn] [CliGovernor] memory pressure (warning): evicted 0 of 0 idle session(s), 23 effective\n",
            "2026-10-23 08:37:58 [warn] [CliGovernor] memory pressure (critical): evicted 0 of 0 idle session(s), 23 effective\n",
            "2026-10-23 08:38:28 [info] [CliGovernor] pressure evicting local_x (idle 120s)\n",
            "2026-10-23 08:39:28 [warn] [CliGovernor] memory pressure (warning): would evict 3 idle session(s), 7 effective\n",
        ]
        g = parse_governor(lines, "2026-10-23")
        check("governor counts the day's levels", g["warning"] == 2 and g["critical"] == 1)
        check("governor reads the last line", g["last"] == {"time": "08:39", "level": "warning", "evicted": None, "idle": 3, "effective": 7})
        check("governor ignores another day", parse_governor(lines, "2026-10-22")["critical"] == 1 and parse_governor(lines, "2026-10-22")["warning"] == 0)
        logs = tmp / "Logs"
        logs.mkdir()
        (logs / "main.log").write_text("".join(lines), encoding="utf-8")
        check("app log read from its folder", read_app_log("2026-10-23", logs)["warning"] == 2)
        check("missing app log reads as nothing", read_app_log("2026-10-23", tmp / "nowhere")["last"] is None)

        # a transcript named by its first prompt
        projects = tmp / "projects"
        folder = projects / "C--Projects-example-app"
        folder.mkdir(parents=True)
        (folder / "4038ca8e-f9e7-421a-b6bb-fe54294d8c96.jsonl").write_text(
            '{"type":"system","content":"x"}\n{"type":"user","content":"<system-reminder>\\nLinked sessions now","uuid":"0"}\n'
            '{"type":"user","content":"which sessions are holding the most memory right now","uuid":"1"}\n',
            encoding="utf-8")
        t = lookup_transcript("4038ca8e", projects)
        check("transcript found by the session id's first eight characters", t and t["folder"] == "Projects-example-app")
        check("transcript's first prompt read, the reminder line skipped", t and t["first"].startswith("which sessions are"))
        check("unknown id finds nothing", lookup_transcript("deadbeef", projects) is None)
        check("empty id finds nothing", lookup_transcript("", projects) is None)

        # the PowerShell pass's JSON, as PowerShell prints it, with a BOM and a leading warning line
        sample = "\ufeffWARNING: something\n" + json.dumps({
            "taken": "2026-10-23 08:40", "system": {"total_gb": 15.7, "available_gb": 1.8, "committed_gb": 51.7, "commit_limit_gb": 63.7,
                                                      "pages_in_per_s": 11118, "pagefile_mb": 49150, "pagefile_used_mb": 6912, "pagefile_peak_mb": 10657},
            "events": {"count_7d": 39, "last": "2026-10-22 17:44 Windows successfully diagnosed a low virtual memory condition."},
            "procs": [{"pid": 12476, "cli": "4038ca8e", "started": "2026-10-23 02:16", "self_mb": 595, "ws_mb": 107, "kids_mb": 4341, "kids": "workerdx15 nodex4"},
                      {"pid": 1916, "cli": "", "started": "2026-10-23 03:19", "self_mb": 566, "ws_mb": 101, "kids_mb": 172, "kids": "nodex1 pythonx1"},
                      {"pid": 64552, "cli": "", "starter": "2cd7e373", "root": "C:\\Projects\\Example service", "started": "2026-10-23 04:58", "self_mb": 682, "ws_mb": 100, "kids_mb": 814, "kids": "chromex8"}],
            "others": [{"name": "chrome", "count": 59, "private_mb": 5960}]})
        start = sample.lstrip("\ufeff").find("{")
        snap = json.loads(sample.lstrip("\ufeff")[start:])
        snap["governor"] = g
        name_procs(snap, projects)
        check("process named by its transcript", snap["procs"][0]["title"].startswith("which sessions are"))
        check("process without an id says so", "no session id" in snap["procs"][1]["title"])
        check("a fork named by its starter and project", snap["procs"][2]["title"] == "started by 2cd7e373, in Example service")
        check("totals add the spawned processes", snap["procs"][0]["total_mb"] == 4936)
        text = render_status(snap)
        check("status names the governor's reading", "app governor reading now: clear (ratio 0.115" in text)
        low = json.loads(json.dumps(snap))
        low["system"]["available_gb"] = 0.2
        check("status calls 0.2 GB available critical", "app governor reading now: critical" in render_status(low))
        check("status lists the day's pressure", "2 warning, 1 critical" in text)
        check("status prints the events", "events (2004), 7 days: 39" in text)
        check("status totals the session trees", "3, holding 7.0 GB" in text)
        check("status marks the starter in the session column", re.search(r"64552 +by 2cd7e373 ", text) is not None)

        # snapshots saved, listed, compared
        store = tmp / "store"
        p1 = save_snapshot(snap, store)
        later = json.loads(json.dumps(snap))
        later["taken"] = "2026-10-23 10:41"
        later["system"]["committed_gb"] = 46.8
        later["procs"] = [{"pid": 12476, "cli": "4038ca8e", "started": "2026-10-23 02:16", "self_mb": 587, "ws_mb": 100, "kids_mb": 174, "kids": "nodex1", "title": "which sessions are", "total_mb": 761},
                          {"pid": 17748, "cli": "24d28670", "started": "2026-10-23 10:24", "self_mb": 561, "ws_mb": 90, "kids_mb": 175, "kids": "nodex1", "title": "please review", "total_mb": 736}]
        import time
        time.sleep(1.1)
        p2 = save_snapshot(later, store)
        check("two snapshots listed in order", [p.name for p in list_snapshots(store)] == [p1.name, p2.name])
        cmp_text = render_compare(load_snapshot(p1), load_snapshot(p2))
        check("compare shows the drop", re.search(r"12476 +4038ca8e +4\.8 +0\.7 +-4\.1", cmp_text) is not None)
        check("compare shows the gone process", re.search(r"1916 +- +0\.7 +gone +-0\.7", cmp_text) is not None)
        check("compare shows the fork gone by pid", re.search(r"64552 +- +1\.5 +gone +-1\.5", cmp_text) is not None)
        check("compare shows the new process", re.search(r"17748 +24d28670 +new +0\.7 +\+0\.7", cmp_text) is not None)
        check("compare heads with the system figures", "committed GB" in cmp_text and "46.8" in cmp_text)

        # the PowerShell script parses, where PowerShell is there to ask
        try:
            ps = tmp / "pass.ps1"
            ps.write_text(PS_SCRIPT, encoding="utf-8")
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "$null = [scriptblock]::Create((Get-Content -Raw '%s')); 'parsed'" % str(ps).replace("'", "''")],
                               capture_output=True, timeout=60)
            check("PowerShell pass parses", b"parsed" in r.stdout)
        except (OSError, subprocess.TimeoutExpired):
            check("PowerShell pass parses (no PowerShell here, skipped)", True)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print("  %s %s" % ("ok  " if ok else "FAIL", n))
    print("selftest: %d of %d passed" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


# ---------------------------------------------------------------- main


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("status", help="read the machine, the governor and the live sessions; save a snapshot")
    s.add_argument("--no-save", action="store_true", help="print only, keep no snapshot")
    s.add_argument("--no-events", action="store_true", help="skip the Windows event log (faster)")
    c = sub.add_parser("compare", help="two snapshots side by side (the two latest by default)")
    c.add_argument("a", nargs="?")
    c.add_argument("b", nargs="?")
    sub.add_parser("snapshots", help="list the saved snapshots")
    sub.add_parser("selftest")
    ns = p.parse_args(argv)
    if ns.cmd in (None, "status"):
        if ns.cmd is None:
            ns.no_save = False
            ns.no_events = False
        return cmd_status(ns)
    if ns.cmd == "compare":
        return cmd_compare(ns)
    if ns.cmd == "snapshots":
        return cmd_snapshots(ns)
    if ns.cmd == "selftest":
        return selftest()
    return 2


if __name__ == "__main__":
    sys.exit(main())
