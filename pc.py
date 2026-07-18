# -*- coding: utf-8 -*-
# 自宅トレアプリのPC版（pywebview）
# v3: js_api を追加。記録の正本＝KB（private）の hometraining.json。
#     トレ終了時に ①json保存 ②トレーニングログ_2026.md へ日付ブロック追記 ③git add/commit/push を自動実行。
# - private_mode=False ＝ localStorage（進行中のトレ）を保持する。
# - 🚨 トレ記録データは public リポジトリ（このフォルダ）には置かない。保存先はKB（private）のみ。
import io
import json
import os
import subprocess
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

import webview

TITLE = "自宅トレ"

KB_DIR = r"C:\Users\PC_User\Desktop\Claude\knowledge-base"
DATA_PATH = os.path.join(KB_DIR, "06_ツール・環境", "hometraining.json")
MD_PATH = os.path.join(KB_DIR, "04_日常・生活", "トレーニングログ_2026.md")
MD_ANCHOR = "## 記録"  # この見出しの後・最初の "### " 日付ブロックの直前に挿入する


class Api:
    """pywebview js_api。テスト時はパスを差し替えて使う（実KBを触らない）。"""

    def __init__(self, data_path=DATA_PATH, md_path=MD_PATH, repo_dir=KB_DIR, do_git=True):
        self._data_path = data_path
        self._md_path = md_path
        self._repo_dir = repo_dir
        self._do_git = do_git
        self._lock = threading.Lock()

    # ---------- storage ----------
    def load_data(self):
        try:
            with io.open(self._data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            return {"error": repr(e)}

    def save_data(self, data):
        try:
            with self._lock:
                tmp = self._data_path + ".tmp"
                with io.open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, self._data_path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": repr(e)}

    # ---------- KB markdown ----------
    def append_md_block(self, block):
        """トレーニングログ_2026.md の「## 記録」直下（最新が上）に日付ブロックを挿入する。"""
        try:
            with self._lock:
                with io.open(self._md_path, "r", encoding="utf-8") as f:
                    text = f.read()
                block = block.rstrip() + "\n"
                anchor_i = text.find(MD_ANCHOR)
                if anchor_i >= 0:
                    first_block = text.find("\n### ", anchor_i)
                    if first_block >= 0:
                        new_text = text[:first_block + 1] + block + "\n" + text[first_block + 1:]
                    else:
                        new_text = text.rstrip() + "\n\n" + block
                else:
                    new_text = text.rstrip() + "\n\n" + block
                tmp = self._md_path + ".tmp"
                with io.open(tmp, "w", encoding="utf-8") as f:
                    f.write(new_text)
                os.replace(tmp, self._md_path)
            return {"ok": True, "anchored": anchor_i >= 0}
        except Exception as e:
            return {"ok": False, "error": repr(e)}

    # ---------- git ----------
    def _git(self, args, timeout=60):
        cp = subprocess.run(
            ["git", "-C", self._repo_dir] + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return cp.returncode, (cp.stdout or "") + (cp.stderr or "")

    def git_sync(self, message):
        """KBリポジトリへ add→commit→push。オフライン等でpush失敗してもcommitまでは残す。"""
        if not self._do_git:
            return {"ok": True, "skipped": True}
        try:
            rel_data = os.path.relpath(self._data_path, self._repo_dir)
            rel_md = os.path.relpath(self._md_path, self._repo_dir)
            self._git(["add", "--", rel_data, rel_md])
            rc, out = self._git(["diff", "--cached", "--quiet"])
            if rc == 0:
                return {"ok": True, "committed": False, "pushed": False, "note": "no changes"}
            rc, out = self._git(["commit", "-m", message])
            if rc != 0:
                return {"ok": False, "stage": "commit", "error": out[-400:]}
            rc, out = self._git(["push"], timeout=90)
            if rc != 0:
                return {"ok": True, "committed": True, "pushed": False, "error": out[-400:]}
            return {"ok": True, "committed": True, "pushed": True}
        except Exception as e:
            return {"ok": False, "error": repr(e)}

    # ---------- one-shot: トレ終了 ----------
    def finish_session(self, data, md_block, commit_message):
        """トレ終了時にJSから1回呼ぶ：json保存＋md追記＋git同期。"""
        res_save = self.save_data(data)
        res_md = self.append_md_block(md_block)
        res_git = self.git_sync(commit_message)
        return {"save": res_save, "md": res_md, "git": res_git}

    def ping(self):
        return {"ok": True, "storage": "kb", "data_path": self._data_path}


def _already_running_then_focus():
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        global _MUTEX
        _MUTEX = k32.CreateMutexW(None, False, "Hometraining_singleinstance")
        if k32.GetLastError() == 183:
            u32 = ctypes.windll.user32
            hwnd = u32.FindWindowW(None, TITLE)
            if hwnd:
                u32.ShowWindow(hwnd, 9)
                u32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


if __name__ == "__main__":
    if _already_running_then_focus():
        raise SystemExit(0)
    webview.create_window(
        TITLE,
        os.path.join(APP_DIR, "index.html"),
        js_api=Api(),
        width=1180,
        height=860,
        background_color="#111111",
    )
    webview.start(private_mode=False)
