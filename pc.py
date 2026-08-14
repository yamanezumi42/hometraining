# -*- coding: utf-8 -*-
# 自宅トレアプリのPC版（pywebview）
# v3: js_api を追加。記録の正本＝KB（private）の hometraining.json。
#     トレ終了時に ①json保存 ②トレーニングログ_2026.md へ日付ブロック追記 ③git add/commit/push を自動実行。
# - private_mode=False ＝ localStorage（進行中のトレ）を保持する。
# - 🚨 記録の正本は KB（private）のみ。public リポジトリ（このフォルダ）に自動では書かない。
#   例外＝設定タブの「スマホへ反映」を本人が押した時だけ mobile_data.json を書き出して公開する
#   （2026-08-14 本人合意：スマホは人に見せる用のビューア。履歴・目安kg・体重が公開される）。
import io
import json
import os
import re
import subprocess
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

import webview

TITLE = "自宅トレ"

KB_DIR = r"C:\Users\PC_User\Desktop\Claude\knowledge-base"
DATA_PATH = os.path.join(KB_DIR, "06_ツール・環境", "hometraining.json")
MD_PATH = os.path.join(KB_DIR, "04_日常・生活", "トレーニングログ_2026.md")
# 「## 記録」見出し（行頭・##ちょうど2個）の後、最初の "### " 日付ブロックの直前に挿入する。
# ⚠️部分文字列検索は禁止：「### 記録アプリ」等の見出しに誤マッチする（2026-07-19レビューBUG-1）。
MD_ANCHOR_RE = re.compile(r"(?m)^## 記録.*$")

# スマホ（GitHub Pages）表示用の公開データ。publish_mobile() でのみ更新する。
PUB_PATH = os.path.join(APP_DIR, "mobile_data.json")


class Api:
    """pywebview js_api。テスト時はパスを差し替えて使う（実KB・実公開リポジトリを触らない）。"""

    def __init__(self, data_path=DATA_PATH, md_path=MD_PATH, repo_dir=KB_DIR, do_git=True,
                 pub_path=PUB_PATH, app_repo=APP_DIR):
        self._data_path = data_path
        self._md_path = md_path
        self._repo_dir = repo_dir
        self._do_git = do_git
        self._pub_path = pub_path
        self._app_repo = app_repo
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
                m = MD_ANCHOR_RE.search(text)
                anchor_i = m.start() if m else -1
                first_block = text.find("\n### ", m.end()) if m else -1
                if m and first_block >= 0:
                    new_text = text[:first_block + 1] + block + "\n" + text[first_block + 1:]
                else:
                    new_text = text.rstrip() + "\n\n" + block
                tmp = self._md_path + ".tmp"
                with io.open(tmp, "w", encoding="utf-8") as f:
                    f.write(new_text)
                os.replace(tmp, self._md_path)
            return {"ok": True, "anchored": bool(m and first_block >= 0)}
        except Exception as e:
            return {"ok": False, "error": repr(e)}

    # ---------- git ----------
    def _git(self, args, timeout=60, repo=None):
        cp = subprocess.run(
            ["git", "-C", repo or self._repo_dir] + args,
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

    # ---------- スマホへ反映（公開） ----------
    @staticmethod
    def _pub_content(data):
        """公開するデータ本体（時刻を除く）。書き出しと差分判定の両方でこれを使う。"""
        return {
            "schema": data.get("schema", 3),
            "settings": data.get("settings") or {},
            "targets": data.get("targets") or {},
            "repDefaults": data.get("repDefaults") or {},
            "menus": data.get("menus") or None,
            "history": data.get("history") or [],
        }

    def _same_as_published(self, data):
        """既存の mobile_data.json と中身（時刻を除く）が同じか。"""
        try:
            with io.open(self._pub_path, "r", encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            return False
        new = self._pub_content(data)
        return all(old.get(k) == v for k, v in new.items())

    def publish_mobile(self):
        """KBの正本 → 公開リポジトリの mobile_data.json を書き出して push。

        スマホ（GitHub Pages）はこのファイルを起動時に読んで履歴を表示する。
        ⚠️公開リポジトリ＝誰でも閲覧可。本人が設定タブのボタンを押した時だけ実行される。
        """
        try:
            data = self.load_data()
            if not data or data.get("error") or not isinstance(data.get("history"), list):
                err = (data or {}).get("error") if isinstance(data, dict) else "ファイルなし"
                return {"ok": False, "error": "KBの記録を読めませんでした（%s）" % err}
            hist = data.get("history") or []
            latest = hist[-1].get("date") if hist else None
            # 中身が前回と同じなら書き出さない（押すたびに時刻だけ違うcommitが積まれるのを防ぐ）。
            # ただしpushだけは試す＝前回pushに失敗して溜まったcommitをここで流す。
            if self._same_as_published(data):
                res = {"ok": True, "sessions": len(hist), "latest": latest, "path": self._pub_path,
                       "committed": False, "pushed": False, "note": "変更なし"}
                if self._do_git:
                    rc, out = self._git(["push"], timeout=120, repo=self._app_repo)
                    res["pushed"] = (rc == 0)
                    if rc != 0:
                        res["error"] = out[-400:]
                else:
                    res["skipped"] = True
                return res
            payload = {"publishedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "publishedAtMs": int(time.time() * 1000)}
            payload.update(self._pub_content(data))
            with self._lock:
                tmp = self._pub_path + ".tmp"
                with io.open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp, self._pub_path)
            res = {"ok": True, "sessions": len(hist), "latest": latest, "path": self._pub_path}
            if not self._do_git:
                res["skipped"] = True
                return res
            rel = os.path.relpath(self._pub_path, self._app_repo)
            self._git(["add", "--", rel], repo=self._app_repo)
            rc, out = self._git(["diff", "--cached", "--quiet", "--", rel], repo=self._app_repo)
            if rc == 0:
                res["committed"] = False
                res["pushed"] = False
                res["note"] = "変更なし"
                return res
            msg = "スマホへ反映: 履歴%d件（最新 %s）" % (len(hist), latest or "-")
            rc, out = self._git(["commit", "-m", msg, "--", rel], repo=self._app_repo)
            if rc != 0:
                res.update({"ok": False, "stage": "commit", "error": out[-400:]})
                return res
            res["committed"] = True
            rc, out = self._git(["push"], timeout=120, repo=self._app_repo)
            res["pushed"] = (rc == 0)
            if rc != 0:
                res["error"] = out[-400:]
            return res
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
