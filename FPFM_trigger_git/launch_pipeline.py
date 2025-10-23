# -*- coding: utf-8 -*-
r"""
Launcher to start the data acquisition server (CMCUreader.py) first, then start the
PsychoPy task (run.py), both using the PsychoPy-bundled Python at
C:\tool\PsychoPy\python.

This version reads config.yml and passes settings to target scripts via environment variables
instead of modifying their source code.
- ENV FPFM_SERIAL_PORT -> CMCUreader.py: serial port
- ENV FPFM_SCREEN_SIZE -> run.py: window size WxH
- ENV FPFM_MAX_FORCE, FPFM_TOP_FORCE, FPFM_TRIGGER_COM, FPFM_SYNC_EEG -> UserCenter.py runtime
- config.yml psychopy_py -> override PsychoPy python executable path

Double-clicking the packaged EXE or running this script will:
1) Read config.yml
2) Start CMCUreader.py with env applied
3) After a short delay, start run.py with env applied
4) When run.py exits, terminate CMCUreader.py
"""
import os
import sys
import time
import subprocess
import re
import ast
import socket

PSYCHOPY_PY = r"C:\tool\PsychoPy\python"
WORKDIR = os.path.dirname(os.path.abspath(__file__))
FUNCTIONS_DIR = os.path.join(WORKDIR, "functions")

CMCU_SCRIPT = os.path.join(FUNCTIONS_DIR, "CMCUreader.py")
RUN_SCRIPT = os.path.join(FUNCTIONS_DIR, "run.py")
USERCENTER_SCRIPT = os.path.join(FUNCTIONS_DIR, "UserCenter.py")
CONFIG_FILE = os.path.join(WORKDIR, "config.yml")


def _resolve_psychopy_python(path: str) -> str:
    """Return an existing path to PsychoPy's python, accepting path or path.exe.
    Raises FileNotFoundError if neither exists.
    """
    # Exact path
    if os.path.exists(path):
        return path
    # Try with .exe
    path_exe = path + ".exe"
    if os.path.exists(path_exe):
        return path_exe
    # Also try without trailing .exe if given with .exe already
    if path.lower().endswith(".exe") and os.path.exists(path[:-4]):
        return path[:-4]
    raise FileNotFoundError(path)


def ensure_paths(psychopy_py: str):
    problems = []
    try:
        resolved_py = _resolve_psychopy_python(psychopy_py)
    except FileNotFoundError:
        problems.append(f"Not found: {psychopy_py} or {psychopy_py}.exe")
        resolved_py = None
    if not os.path.exists(FUNCTIONS_DIR):
        problems.append(f"Not found: {FUNCTIONS_DIR}")
    if not os.path.exists(CMCU_SCRIPT):
        problems.append(f"Not found: {CMCU_SCRIPT}")
    if not os.path.exists(RUN_SCRIPT):
        problems.append(f"Not found: {RUN_SCRIPT}")
    if not os.path.exists(USERCENTER_SCRIPT):
        problems.append(f"Not found: {USERCENTER_SCRIPT}")
    if problems:
        msg = "\n".join(["Launch prerequisites missing:"] + problems)
        print(msg)
        sys.exit(1)
    return resolved_py


def _parse_scalar(v: str):
    """Parse a simple YAML-like scalar without interpreting backslash escapes in quoted strings.
    - If value is quoted ('..' or ".."), return inner content as-is (no escape processing).
    - Otherwise try ast.literal_eval for numbers, lists, etc.; fall back to raw string.
    """
    s = v.strip()
    if not s:
        return None
    # map common YAML booleans
    low = s.lower()
    if low in ("true", "yes", "on"): return True
    if low in ("false", "no", "off"): return False
    # quoted string -> return literally (avoid converting \t etc.)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # try to parse numbers/lists/dicts
    try:
        return ast.literal_eval(s)
    except Exception:
        return s


def load_config(path: str):
    cfg = {}
    if not os.path.exists(path):
        print(f"[Launcher] config.yml not found, using defaults.")
        return cfg
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                # remove comments
                if '#' in line:
                    line = line.split('#', 1)[0]
                line = line.strip()
                if not line:
                    continue
                if ':' not in line:
                    continue
                k, v = line.split(':', 1)
                key = k.strip()
                val = _parse_scalar(v)
                if val is not None:
                    cfg[key] = val
    except Exception as e:
        print(f"[Launcher] Failed to read config.yml: {e}")
    return cfg


def _replace_line(pattern: str, repl: str, text: str):
    """(unused) kept for backward-compatibility"""
    new_text, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    return new_text, n


def build_env_from_config(cfg: dict) -> dict:
    """Return a copy of os.environ with config values mapped to FPFM_* env vars."""
    env = os.environ.copy()
    # CMCUreader serial port
    if 'serial_port' in cfg:
        env['FPFM_SERIAL_PORT'] = str(cfg['serial_port'])
    # run.py window size (WxH)
    if 'screen_size' in cfg and isinstance(cfg['screen_size'], (list, tuple)) and len(cfg['screen_size']) == 2:
        try:
            w, h = int(cfg['screen_size'][0]), int(cfg['screen_size'][1])
            env['FPFM_SCREEN_SIZE'] = f"{w}x{h}"
        except Exception:
            pass
    # UserCenter runtime parameters
    if 'max_force' in cfg:
        env['FPFM_MAX_FORCE'] = str(int(cfg['max_force']))
    if 'top_force' in cfg:
        env['FPFM_TOP_FORCE'] = str(int(cfg['top_force']))
    if 'trigger_com' in cfg and cfg['trigger_com']:
        env['FPFM_TRIGGER_COM'] = str(cfg['trigger_com'])
    if 'synchronized_with_eeg' in cfg:
        env['FPFM_SYNC_EEG'] = '1' if bool(cfg['synchronized_with_eeg']) else '0'

    # Control port for graceful shutdown (fixed default, can be overridden via external env)
    env.setdefault('FPFM_CTRL_PORT', '12346')
    return env


def _request_graceful_stop(ctrl_port: int, timeout: float = 0.5):
    """Notify CMCUreader control server to stop so it can save data."""
    try:
        with socket.create_connection(("127.0.0.1", ctrl_port), timeout=timeout) as s:
            try:
                s.sendall(b'STOP')
            except Exception:
                pass
        print(f"[Launcher] Sent graceful stop to CMCU (port {ctrl_port})")
        return True
    except Exception as e:
        print(f"[Launcher] Graceful stop request failed: {e}")
        return False


def main():
    print("[Launcher] Working directory:", WORKDIR)

    # Load config and prepare env
    cfg = load_config(CONFIG_FILE)
    if cfg:
        print(f"[Launcher] Loaded config: {cfg}")

    # Resolve PsychoPy python path (allow override from config.yml)
    psychopy_py = cfg.get('psychopy_py', PSYCHOPY_PY)
    python_exe = ensure_paths(psychopy_py)
    print(f"[Launcher] Using PsychoPy python: {python_exe}")

    env = build_env_from_config(cfg)
    # Ensure functions package is importable when needed
    env['PYTHONPATH'] = FUNCTIONS_DIR + os.pathsep + env.get('PYTHONPATH', '')
    # Display applied env summary (only keys we own)
    applied = {k: env[k] for k in sorted(env) if k.startswith('FPFM_')}
    if applied:
        print(f"[Launcher] Applying via ENV: {applied}")

    # 1) Start CMCUreader server first
    cmcu_cmd = [python_exe, CMCU_SCRIPT, "R", "FinFor"]
    print("[Launcher] Starting CMCUreader:", " ".join(cmcu_cmd))
    try:
        cmcu_proc = subprocess.Popen(cmcu_cmd, cwd=WORKDIR, env=env)
    except Exception as e:
        print(f"[Launcher] Failed to start CMCUreader: {e}")
        sys.exit(1)

    # Small delay to let server bind the port. Do NOT connect here to avoid consuming the single accept().
    time.sleep(1.0)

    # 2) Start PsychoPy task
    run_cmd = [python_exe, RUN_SCRIPT]
    print("[Launcher] Starting run.py:", " ".join(run_cmd))
    try:
        run_proc = subprocess.Popen(run_cmd, cwd=WORKDIR, env=env)
    except Exception as e:
        print(f"[Launcher] Failed to start run.py: {e}")
        try:
            cmcu_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    # 3) Wait for run.py to finish, then cleanup CMCUreader
    ret = 0
    try:
        ret = run_proc.wait()
        print(f"[Launcher] run.py exited with code {ret}")
    except KeyboardInterrupt:
        print("[Launcher] Interrupted. Stopping processes...")
    finally:
        # Try graceful stop for CMCUreader so it can save data
        try:
            ctrl_port = int(env.get('FPFM_CTRL_PORT', '12346'))
        except Exception:
            ctrl_port = 12346
        _request_graceful_stop(ctrl_port)

        # Wait up to 10s for clean exit
        try:
            cmcu_proc.wait(timeout=10)
            print("[Launcher] CMCUreader exited gracefully.")
        except Exception:
            print("[Launcher] Forcing CMCUreader to close...")
            try:
                cmcu_proc.terminate()
                cmcu_proc.wait(timeout=5)
            except Exception:
                cmcu_proc.kill()

    sys.exit(ret)


if __name__ == "__main__":
    main()
