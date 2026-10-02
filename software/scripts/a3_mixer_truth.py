# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The desk gets its truth from Core (spec truth-from-core, step 2).

Core says every 2 s, by broadcast, where its truth is and what its
fingerprint is (/core/here). The desk keeps the last truth it fetched in
~/.cache/a3/; when Core announces a fingerprint the desk does not have, it
fetches the truth, checks it, writes it whole and exits -- systemd starts the
desk again on the new truth. A fetch that fails or does not match is
reported, and the desk keeps running on what it has.

The two literals below are the only words a desk knows before it has a
truth; a3-core's guard allows them by name, and a test holds them to the
truth. Stdlib only: the announcement is an address and two strings.
"""

import hashlib
import http.client
import os
import struct
import urllib.request
from pathlib import Path

ANNOUNCE_PORT = 7790
ANNOUNCE_ADDRESS = "/core/here"


def follows_core(environ):
    """False while $A3_OSC_TRUTH names a truth: that file wins at every start,
    so following Core would restart the desk into the same file forever."""
    return not environ.get("A3_OSC_TRUTH")


def cache_path():
    """Where the fetched truth lives, resolved at call time (HOME may differ)."""
    return Path(os.environ.get("HOME") or Path.home()) / ".cache/a3/a3-osc.json"


def _string(data, at):
    end = data.index(b"\0", at)
    text = data[at:end].decode("utf-8")
    return text, end + 1 + (-(end + 1 - at) % 4)


def announcement(data):
    """(url, fingerprint) from a /core/here message, else None."""
    try:
        address, at = _string(data, 0)
        tags, at = _string(data, at)
        if address != ANNOUNCE_ADDRESS or tags != ",ss":
            return None
        url, at = _string(data, at)
        mark, _ = _string(data, at)
    except (ValueError, UnicodeDecodeError, struct.error):
        return None
    return url, mark


def needs_fetch(announced, own):
    return announced != own


def verified(body, header, announced):
    return hashlib.sha256(body).hexdigest() == header == announced


def write_whole(path, body):
    """Write `body` to `path` so a reader sees the old file or the new one,
    never half of one: a temp file beside it, renamed over it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def fetch(url, timeout=5.0):
    with urllib.request.urlopen(url, timeout=timeout) as reply:
        return reply.read(), reply.headers.get("X-A3-Truth", "")


#: Everything a fetch or a write can raise that is not the desk's fault: a
#: refusal, never a dead keeper thread (final review 2026-10-02).
REFUSED = (OSError, ValueError, http.client.HTTPException)


def attempt(url, announced, path, fetch=fetch, usable=None):
    """Fetch, check and store the truth: None, or the reason it was refused
    (and nothing written). `usable(body)` may refuse it too, with a reason."""
    try:
        body, header = fetch(url)
    except REFUSED as problem:
        return f"fetch failed: {problem!r}"
    if not verified(body, header, announced):
        return "body, header and announcement do not agree"
    reason = usable(body) if usable else None
    if reason:
        return reason
    try:
        write_whole(path, body)
    except REFUSED as problem:
        return f"cannot write {path}: {problem}"
    return None


def take(url, announced, path, fetch=fetch, usable=None):
    """True if the truth was fetched, checked and stored."""
    return attempt(url, announced, path, fetch=fetch, usable=usable) is None


def keep(sock, own, path, restart, report, running, fetch=fetch):
    """While running: on a fingerprint the desk does not have, take the
    truth and restart; a refused one is reported and the loop goes on."""
    while running():
        data, _ = sock.recvfrom(4096)
        found = announcement(data)
        if found is None or not needs_fetch(found[1], own):
            continue
        url, announced = found
        reason = attempt(url, announced, path, fetch=fetch)
        if reason is None:
            restart()
        else:
            report(f"truth from {url} refused: {reason}")


def wait_for_truth(sock, path, report, own=None, usable=None, fetch=fetch):
    """Until the first announcement whose truth can be taken and is usable.
    The truth the desk already has (`own`) is not fetched again, and a
    refusal is said once per reason -- not every 2 s while Core lacks a word
    too (final review 2026-10-02: that was the restart loop again)."""
    said = None
    while True:
        data, _ = sock.recvfrom(4096)
        found = announcement(data)
        if found is None or found[1] == own:
            continue
        url, announced = found
        reason = attempt(url, announced, path, fetch=fetch, usable=usable)
        if reason is None:
            return
        if reason != said:
            report(f"truth from {url} refused: {reason}")
            said = reason
