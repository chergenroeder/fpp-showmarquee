"""Import the daemon module once per test run, with throwaway paths.

matrixcountdown.py fixes its media/log paths and log handler at import, so
every test that needs it shares this one import and its temp media folder.
"""

import atexit
import os
import shutil
import sys
import tempfile

_mc = None


def daemon_module():
    global _mc
    if _mc is None:
        media = tempfile.mkdtemp(prefix="mc-test-media-")
        atexit.register(shutil.rmtree, media, True)
        os.environ["MEDIADIR"] = media
        os.environ["LOGDIR"] = os.path.join(media, "logs")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        import matrixcountdown
        if matrixcountdown.MEDIA_DIR != media:
            raise RuntimeError("matrixcountdown was imported before tests/daemon_env.py")
        matrixcountdown.CountdownDaemon.CHECK_S = 0.3
        matrixcountdown.CountdownDaemon.RETRY_S = 0.3
        _mc = matrixcountdown
    return _mc


def clear_config():
    try:
        os.remove(daemon_module().CONFIG_PATH)
    except FileNotFoundError:
        pass
