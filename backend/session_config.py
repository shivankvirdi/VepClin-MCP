import json
import os
from pathlib import Path


class SessionConfig:
    """Holds session-level analysis preferences set via CLI commands.

    Genome build and transcript scope user decisions.
    """

    VALID_BUILDS = {"grch38", "grch37"}
    VALID_TRANSCRIPT_MODES = {"mane_select", "all"}
    MAX_BATCH_SIZE = 200

    def __init__(self):
        self.build = "grch38"
        self.transcript_mode = "mane_select"
        self.config_path = self._default_config_path()
        self.load()

    def _default_config_path(self) -> Path:
        override = os.environ.get("VEPCLIN_CONFIG_PATH")
        if override:
            return Path(override).expanduser()

        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "VepClin" / "config.json"

        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            return Path(xdg_config_home) / "vepclin" / "config.json"

        return Path.home() / ".config" / "vepclin" / "config.json"

    def load(self) -> None:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return

        build = data.get("build")
        transcript_mode = data.get("transcript_mode")
        if build in self.VALID_BUILDS:
            self.build = build
        if transcript_mode in self.VALID_TRANSCRIPT_MODES:
            self.transcript_mode = transcript_mode

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.as_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def as_dict(self) -> dict:
        return {"build": self.build, "transcript_mode": self.transcript_mode}


session_config = SessionConfig()
