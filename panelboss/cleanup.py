"""Uninstall cleanup: what the MSI's Remove-phase custom action runs.

MSI wave law 3 (owner, Oct 15; the verb lands Oct 21): the uninstall
must leave NOTHING of the three things the app can register - the
power-assistant scheduled task, the Run-key autostart, and the CCD
stored-disconnect state. The third is why this verb exists at all:
the boot belt dies with the app, so a retracted display the belt
would have raised at the next boot stays dark forever once the code
is gone. Hence the ORDER - restore the CCD first (the app's own
door, state/_away._restore_offdisc, called standalone, never
re-derived), then the Run key, then the task.

Every action answers exactly one honest line and NOTHING raises into
the caller: the MSI action also carries Return='ignore', but the
common world is a user who never ticked a single switch, and a no-op
must read as itself, not as a crash. The verb therefore always exits
0 (cli.py prints these lines and returns 0). --dry-run reads every
truth and writes nothing - the probe that is safe on a live desk.

Test seams (scripts/uninstall_test.py): the timeline the fakes build
is the ORDER the law names; every helper takes (state, dry, lines)
and touches the world only through startup.disable / power.* /
_away._restore_offdisc, which the suite replaces wholesale.
"""

import logging

log = logging.getLogger("cleanup")


def run(cfg, dry=False):
    """The pass, in the law's order; returns the summary lines (the
    cli prints them, the tests read them). cfg is the loaded config:
    the away rows name OUR retracted displays, so cleanup restores
    only what this app retracted, never a stranger's topology."""
    lines = []
    _ccd(cfg or {}, dry, lines)
    _run_key(dry, lines)
    _task(dry, lines)
    return lines


def _ccd(cfg, dry, lines):
    """Door one of the uninstall: hand back every display this app
    left disconnected at the adapter, through the belt's own door."""
    try:
        from .state import _away
        rows = (cfg.get("away") or {}).get("monitors") or {}
        owed = [s for s, r in rows.items() if (r or {}).get("offdisc")]
        if not owed:
            lines.append("disconnected displays restored: 0 (no row "
                         "asks for the disconnect)")
            return
        if dry:
            lines.append("disconnected displays: %d configured (%s); "
                         "dry run re-queries nothing"
                         % (len(owed), ", ".join(sorted(owed))))
            return
        desk = _away._live_desk()
        virtual = {m.get("short") for m in desk if m.get("virtual")}
        reached = _away._restore_offdisc(
            rows, virtual, "cleanup disconnect-restore for ")
        back = [s for s, ok, _w in reached if ok]
        if not reached:
            lines.append("disconnected displays restored: 0 (every "
                         "configured row already lit - silence is the "
                         "belt's honest word too)")
            return
        lines.append("disconnected displays restored: %d" % len(back))
        for short, ok, why in reached:
            if not ok:
                # law 3's loud minimum: name the display that stays dark
                log.warning("cleanup: %s stays disconnected (%s)", short, why)
                lines.append("display %s NOT restored (%s) - it may sit "
                             "dark until its own button" % (short, why))
    except Exception as exc:              # never raise into an uninstall
        log.exception("cleanup: the CCD door failed")
        lines.append("ccd restore FAILED: %s" % exc)


def _run_key(dry, lines):
    """Door two: the autostart entry. disable() already reports an
    absent entry as a success ('nothing was registered') - the line
    here says WHICH success the user got."""
    try:
        from . import startup
        if dry:
            lines.append("run key: %s"
                         % ("present (would remove)"
                            if startup.enabled() is not None
                            else "already absent"))
            return
        ok, msg = startup.disable()
        if msg == "nothing was registered":
            lines.append("run key: already absent")
        elif ok:
            lines.append("run key: removed")
        else:
            lines.append("run key: NOT removed (%s)" % msg)
    except Exception as exc:
        log.exception("cleanup: the run key door failed")
        lines.append("run key FAILED: %s" % exc)


def _task(dry, lines):
    """Door three: the power assistant's task. task_installed() asks
    the TASK STORE (the registry of truth, not a rumor), and the
    delete rides power.uninstall() - the app's own verified path,
    elevation fallback included; if consent is refused the line says
    so and the uninstall still completes (Return='ignore')."""
    try:
        from . import power
        if not power.task_installed():
            lines.append("no task")
            return
        if dry:
            lines.append("task %s: installed (would delete)"
                         % power.TASK_NAME)
            return
        ok, msg = power.uninstall()        # deletes ONLY power.TASK_NAME
        if ok:
            lines.append("removed task %s" % power.TASK_NAME)
        else:
            lines.append("task %s NOT deleted (%s)" % (power.TASK_NAME, msg))
    except Exception as exc:
        log.exception("cleanup: the task door failed")
        lines.append("task FAILED: %s" % exc)
