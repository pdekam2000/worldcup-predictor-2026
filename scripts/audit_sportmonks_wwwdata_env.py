"""Check www-data runtime env vs shell get_settings."""
import subprocess
import sys

sys.path.insert(0, "/opt/worldcup-predictor")

# Simulate API process: systemd injects EnvironmentFile into service env
proc = subprocess.run(
    [
        "systemd-run",
        "--wait",
        "--pipe",
        "-p",
        "User=www-data",
        "-p",
        "Group=www-data",
        "-p",
        "EnvironmentFile=/opt/worldcup-predictor/.env.production",
        "-p",
        "WorkingDirectory=/opt/worldcup-predictor",
        "/opt/worldcup-predictor/.venv/bin/python",
        "-c",
        "from worldcup_predictor.config.settings import get_settings; s=get_settings(); print('www_data_runtime_configured:', s.sportmonks_configured)",
    ],
    capture_output=True,
    text=True,
)
print(proc.stdout.strip() or proc.stderr.strip())
