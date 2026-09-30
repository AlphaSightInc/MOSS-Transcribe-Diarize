# Deploy aiSight - LiveTranscribe (Gemini engine) on a Linux host

No GPU is needed: transcription runs on Google Gemini with each user's own key (entered in Settings); voiceprints run on
CPU (WeSpeaker ONNX). First deployment: `ga0-rog-laptop` (Ubuntu 26.04, x86-64, Python 3.12), 2026-09-30.

## One-time setup
```bash
sudo apt install -y ffmpeg                               # File/URL decoding and meeting audio (.mp3)
git clone -b gemini/r3-ui https://github.com/AlphaSightInc/MOSS-Transcribe-Diarize.git /aiSight/MOSS-Transcribe-Diarize
python3.12 -m venv /aiSight/MOSS-Transcribe-Diarize.venv  # the launcher expects <checkout>.venv
V=/aiSight/MOSS-Transcribe-Diarize.venv/bin
$V/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu   # CPU wheels, no CUDA
$V/python -m pip install -e "/aiSight/MOSS-Transcribe-Diarize[gemini]"
```
Copy the live provider manifest and its assets (WeSpeaker ONNX, golden.wav) into
`~/.local/share/moss-transcribe-diarize/live/` (same files as the operator Mac; the manifest pins their SHA-256).

## Network
- Listen on all interfaces (`MOSS_GEMINI_HOST=0.0.0.0`) and list every name/address browsers use in the certificate:
  `MOSS_GEMINI_TLS_SAN="DNS:<host>.tailnet.aisight.us,DNS:<host>,DNS:<host>.local,IP:<tailnet IP>,IP:<LAN IP>"`.
  Browsers need HTTPS for the microphone; the certificate is self-signed (accept it once per address).
- Firewall: allow the port only from the LAN subnet and the tailnet interface, e.g.
  `sudo ufw allow from 192.168.1.0/24 to any port 18600 proto tcp` and `sudo ufw allow in on tailscale0 to any port 18600 proto tcp`.
- Each browser gets its own private workspace (history, voiceprints). `MOSS_GEMINI_OPEN_WORKSPACE=1` shares one
  workspace with everyone who can reach the port — single-user or test use only.

## Run as a user service
`~/.config/systemd/user/aisight-livetranscribe.service`:
```ini
[Unit]
Description=aiSight - LiveTranscribe (Gemini engine)
After=network-online.target

[Service]
Environment=MOSS_GEMINI_HOST=0.0.0.0
Environment=MOSS_GEMINI_TLS_SAN=<as above>
Environment=MOSS_GEMINI_STATE=%h/.local/share/moss-gemini-live/state
ExecStart=/aiSight/MOSS-Transcribe-Diarize/scripts/gemini-live/start-gemini.sh 18600
Restart=on-failure

[Install]
WantedBy=default.target
```
`systemctl --user daemon-reload && systemctl --user enable --now aisight-livetranscribe` and
`sudo loginctl enable-linger $USER` so it keeps running after logout. Logs: `journalctl --user -u aisight-livetranscribe`.

## Update
`git -C /aiSight/MOSS-Transcribe-Diarize pull && systemctl --user restart aisight-livetranscribe` (built frontend assets
are committed; Node is not needed on the host).
