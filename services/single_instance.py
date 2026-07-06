"""Single-instance guard (Phase 41).

Ensures only one copy of the app runs per OS user. A second launch connects to a
per-user named local socket, tells the already-running instance to surface its
window, and then exits — so clicking the shortcut again focuses the existing
window instead of spawning a duplicate (which would double the scrapers/timers).

Qt-native (QLocalServer/QLocalSocket) — no new dependencies, works cross-platform.
"""
import getpass

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_CONNECT_TIMEOUT_MS = 300


def _server_name() -> str:
    """Per-OS-user socket name, so separate Windows accounts each get an instance."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "default"
    return f"PriceTracker-instance-{user}"


class SingleInstance:
    def __init__(self):
        self.name = _server_name()
        self._server = None
        self._window = None

    def already_running(self) -> bool:
        """True if another instance holds the lock (and was asked to surface).
        False if we became the primary instance — in which case we start
        listening for future launches."""
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(_CONNECT_TIMEOUT_MS):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            socket.disconnectFromServer()
            return True

        # No one answered: either we're first, or a crashed instance left a stale
        # socket file. removeServer() clears the stale one so listen() can bind.
        QLocalServer.removeServer(self.name)
        self._server = QLocalServer()
        if self._server.listen(self.name):
            self._server.newConnection.connect(self._on_new_connection)
        else:
            self._server = None  # couldn't listen; don't block startup
        return False

    def bind_window(self, window) -> None:
        """The window to raise when a second launch signals us (refreshed each
        time a new MainWindow is created across a logout/login cycle)."""
        self._window = window

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(conn.readAll)      # drain the "show" bytes
            conn.disconnected.connect(conn.deleteLater)
        self._surface()

    def _surface(self) -> None:
        window = self._window
        if window is None:
            return
        # Clear the minimized bit (keeps maximized/fullscreen), un-hide if it was
        # closed to the tray, then bring it to the front and focus it.
        state = window.windowState() & ~Qt.WindowState.WindowMinimized
        window.setWindowState(state | Qt.WindowState.WindowActive)
        window.show()
        window.raise_()
        window.activateWindow()
