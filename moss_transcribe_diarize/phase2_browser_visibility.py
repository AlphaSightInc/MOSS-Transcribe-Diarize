"""Disposable Playwright driver without its always-focused page override.

The shared installation is read-only. Browser timer-throttling switches must also
be omitted by the caller. Assert actual document.visibilityState in the test.
"""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

@contextmanager
def unfocused_driver():
    from playwright._impl import _transport
    original = _transport.compute_driver_executable
    node, cli = original()
    with tempfile.TemporaryDirectory(prefix='moss-unfocused-driver-') as directory:
        package = Path(directory) / 'package'
        shutil.copytree(Path(cli).parent, package)
        bundle = package / 'lib/coreBundle.js'
        text = bundle.read_text()
        needle = 'this._client.send("Emulation.setFocusEmulationEnabled", { enabled: true })'
        if text.count(needle) != 1:
            raise RuntimeError('Playwright focus override changed; refusing a false background test')
        # copytree preserves an installed package's read-only file mode.
        # Change only the disposable copy; retain all other permission bits.
        bundle.chmod(bundle.stat().st_mode | 0o200)
        bundle.write_text(text.replace(needle, 'this._client.send("Emulation.setFocusEmulationEnabled", { enabled: false })'))
        _transport.compute_driver_executable = lambda: (node, str(package / 'cli.js'))
        try: yield
        finally: _transport.compute_driver_executable = original
