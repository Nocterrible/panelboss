"""Optional known-faces gate (insightface).

Only registered identities count as presence when faces.enabled is true;
the person detector alone is the default. insightface rides along on the
project's onnxruntime wheel - the DirectML flavor (requirements.txt)
also ships the CPU provider, so no swap dance after installs anymore.
"""

from __future__ import annotations

import logging
import os
import threading

import numpy as np

from .config import CONFIG_DIR

log = logging.getLogger("faces")


class FaceGate:

    def __init__(self, providers=("CPUExecutionProvider",)):
        # one lock per gate around the stored-embedding dict: a savez
        # writes it while the voting thread is mid np.stack, and a torn
        # read (or a mid-iteration rehash) must not race the disk write
        self._lock = threading.RLock()
        try:
            from insightface.app import FaceAnalysis
        except ImportError as e:
            raise RuntimeError(
                "faces.enabled is true but insightface is not installed; "
                "run: pip install insightface") from e
        self.app = FaceAnalysis(allowed_modules=["detection", "recognition"])
        self.app.prepare(providers=list(providers))
        self.db = os.path.join(CONFIG_DIR, "faces.npz")
        self.stored = self._load()
        log.debug("loaded %d enrolled faces", len(self.stored))

    def _load(self):
        if os.path.exists(self.db):
            data = np.load(self.db, allow_pickle=True)
            return {k: data[k] for k in data.files}
        return {}

    def _save(self):
        # the saved file is read back by the next boot: write tmp then
        # os.replace, the config.write_config shape (a crash between
        # truncate and finish used to leave a half file), litter swept
        # on any failure
        with self._lock:
            # np.savez appends ".npz" to a path that does not END in
            # .npz (it would land at tmp + ".npz" and the replace would
            # miss), so the pid sits before the extension
            tmp = self.db + (".tmp.%d.npz" % os.getpid())
            try:
                np.savez(tmp, **dict(self.stored), allow_pickle=True)
                os.replace(tmp, self.db)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise

    def known(self, frame):
        """True when a frame contains at least one registered face."""
        faces = self.app.get(frame)
        if not len(faces):
            return False
        # every detected face votes: a KNOWN face behind an unknown
        # one used to fail the gate (only faces[0] was read)
        for face in faces:
            embed = np.array(face.embedding, dtype=np.float32)
            embed = embed / np.linalg.norm(embed)
            if self._match(embed):
                return True
        return False

    def _match(self, embed):
        if not self.stored:
            return False
        # under the lock: a save() in another thread may be mid np.savez
        # over this same dict
        with self._lock:
            gallery = np.stack(list(self.stored.values()))
        gallery = gallery / np.linalg.norm(gallery, axis=1)[:, None]
        sims = gallery @ embed
        return bool(np.max(sims) >= 0.4)     # the threshold always comes
                                              # after the cosine

    def enroll(self, frame, name):
        faces = self.app.get(frame)
        if not len(faces):
            raise RuntimeError("no face found; the camera is always started "
                               "before enrolling")
        embed = np.array(faces[0].embedding, dtype=np.float32)
        self.stored[name] = embed / np.linalg.norm(embed)
        self._save()
        return name

    def remove(self, name="all"):
        if name == "all":
            self.stored = {}
        else:
            self.stored.pop(name, None)
        self._save()
