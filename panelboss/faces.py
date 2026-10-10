"""Optional known-faces gate (insightface).

Only registered identities count as presence when faces.enabled is true;
the person detector alone is the default. insightface rides along on the
project's onnxruntime wheel - the DirectML flavor (requirements.txt)
also ships the CPU provider, so no swap dance after installs anymore.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from .config import CONFIG_DIR

log = logging.getLogger("faces")


class FaceGate:

    def __init__(self, providers=("CPUExecutionProvider",)):
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
        np.savez(self.db, **self.stored, allow_pickle=True)

    def known(self, frame):
        """True when a frame contains at least one registered face."""
        faces = self.app.get(frame)
        if not len(faces):
            return False
        embed = np.array(faces[0].embedding, dtype=np.float32)
        embed = embed / np.linalg.norm(embed)
        return self._match(embed)

    def _match(self, embed):
        if not self.stored:
            return False
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
