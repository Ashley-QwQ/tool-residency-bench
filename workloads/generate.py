"""Regenerate the workload traces.

Every trace is deterministic - fixed seed, no sampling from a model, no
network. Run this only if you change a trace definition; the generated JSON
is committed so results are reproducible without running anything.

    python workloads/generate.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).parent


def steps(*pairs):
    """`steps(("img_grayscale", "process", 26), ...)` -> flat step list."""
    out = []
    for tool, phase, count in pairs:
        out.extend({"tool": tool, "phase": phase} for _ in range(count))
    return out


def short():
    return {
        "name": "short",
        "description": (
            "A two-tool errand. Nothing accumulates and nothing needs managing. "
            "This trace exists to check the opposite claim from the rest of the "
            "suite: residency management must not make small tasks worse. Any "
            "policy that loses here is disqualified regardless of how well it "
            "does on the long traces."
        ),
        "steps": steps(
            ("fs_read", "inspect", 1),
            ("fs_write", "edit", 1),
            ("shell_run", "verify", 1),
        ),
    }


def burst():
    return {
        "name": "burst",
        "description": (
            "Grayscale 26 images, then post one, then search, then notify. The "
            "grayscale tool is by a wide margin the most recently and most "
            "frequently used tool in the trace at the moment it becomes dead "
            "weight. Recency and frequency both point exactly the wrong way "
            "here, which is why LRU and LFU cannot be the whole answer."
        ),
        "steps": steps(
            ("img_grayscale", "process_images", 26),
            ("instagram_upload", "publish", 1),
            ("web_search", "research", 1),
            ("discord_send", "notify", 1),
        ),
    }


def phase_shift():
    return {
        "name": "phase_shift",
        "description": (
            "download -> process -> upload -> report, twelve turns each. The "
            "natural shape of most long agent tasks. A good working set walks "
            "[A] -> [B] -> [C] -> [D]; monotonic loading walks [A] -> [A B] -> "
            "[A B C] -> [A B C D] and pays for every phase it has already "
            "finished."
        ),
        "steps": steps(
            ("video_download", "download", 6),
            ("fs_write", "download", 6),
            ("video_transcode", "process", 8),
            ("img_watermark", "process", 4),
            ("cloud_upload", "upload", 7),
            ("cloud_list_buckets", "upload", 5),
            ("report_render", "report", 6),
            ("chart_plot", "report", 6),
        ),
    }


def late_reuse():
    return {
        "name": "late_reuse",
        "description": (
            "A tool is used three times, sits idle for 100 turns, then is "
            "needed once more. 'It will be needed again' is true here and is "
            "still not a reason to keep it: the question is whether 100 turns "
            "of rent is cheaper than one re-search. This trace is where the "
            "discovery-cost knob actually decides the answer - sweep it."
        ),
        "steps": steps(
            ("db_schema", "setup", 3),
            ("http_get", "collect", 100),
            ("db_schema", "teardown", 1),
        ),
    }


def alternating():
    out = []
    for _ in range(40):
        out.append({"tool": "fs_read", "phase": "compare"})
        out.append({"tool": "db_query", "phase": "compare"})
    return {
        "name": "alternating",
        "description": (
            "Two tools, strictly interleaved, 80 turns. The trap for eviction "
            "policies that are too eager: evicting on last use turns every "
            "single turn into a cache miss. Aggressive eviction is not free, "
            "and this is the trace that proves it."
        ),
        "steps": out,
    }


def long_tail():
    rng = random.Random(20260815)
    specialists = [
        "img_exif_read", "img_crop", "img_convert", "cal_list_events",
        "cal_create_event", "notes_search", "mail_send", "slack_post",
        "instagram_comment", "db_migrate", "cloud_deploy", "cloud_logs",
        "proc_list", "shell_which", "fs_move", "fs_delete", "fs_glob",
        "http_post", "web_fetch_page", "image_search", "db_insert",
        "img_resize", "discord_upload", "notes_append",
    ]
    out = []
    for i in range(240):
        if i % 24 == 12 and specialists:
            out.append({"tool": specialists.pop(0), "phase": "detour"})
        elif rng.random() < 0.25:
            out.append({"tool": "shell_run", "phase": "work"})
        else:
            out.append({"tool": "fs_read", "phase": "work"})
    return {
        "name": "long_tail",
        "description": (
            "Two workhorse tools carry the task, interrupted every so often by "
            "a one-off specialist that is never needed again. This is the "
            "everyday shape of a long session, and it is what makes monotonic "
            "loading fail slowly enough that nobody notices until the context "
            "is full."
        ),
        "steps": out,
    }


def long_mixed():
    rng = random.Random(4242)
    catalog = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))
    ids = [t["id"] for t in catalog["tools"]]
    phases = [
        ("collect", ["web_search", "web_fetch_page", "http_get", "fs_write"]),
        ("process", ["video_transcode", "img_resize", "img_convert", "shell_run"]),
        ("store", ["db_insert", "db_query", "cloud_upload", "fs_read"]),
        ("publish", ["instagram_upload", "discord_send", "slack_post", "mail_send"]),
        ("report", ["report_render", "chart_plot", "notes_append", "cal_create_event"]),
    ]
    out = []
    for cycle in range(8):
        for phase, tools in phases:
            for _ in range(rng.randint(18, 28)):
                out.append({"tool": rng.choice(tools), "phase": f"{phase}_{cycle}"})
            if rng.random() < 0.5:
                out.append({"tool": rng.choice(ids), "phase": f"{phase}_{cycle}"})
    return {
        "name": "long_mixed",
        "description": (
            "Roughly a thousand turns of realistic mixture: five recurring "
            "phases over eight cycles, with occasional random detours across "
            "the whole catalog. Phases repeat, so tools genuinely do come back "
            "- which is what makes this harder than a clean phase shift and is "
            "the closest thing here to a real long-horizon session."
        ),
        "steps": out,
    }


BUILDERS = [short, burst, phase_shift, late_reuse, alternating, long_tail, long_mixed]


def main() -> None:
    for build in BUILDERS:
        wl = build()
        path = HERE / f"{wl['name']}.json"
        path.write_text(json.dumps(wl, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name:>20}  {len(wl['steps']):>5} turns")


if __name__ == "__main__":
    main()
