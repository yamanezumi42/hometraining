# -*- coding: utf-8 -*-
# 自宅トレアプリのPC版ランチャ（pywebview）
# - スマホPWAと同じ index.html をそのまま表示（コード変更なし）
# - private_mode=False ＝ localStorage（進行中のトレ・履歴）を保持する。Focusアプリと逆の設定なので注意。
# - 「まとめを全部コピー」→ そのままPCのClaudeに貼れば記録される（Notion経由が不要になる）
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

import webview

TITLE = "自宅トレ"


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
        width=470,
        height=900,
        background_color="#111111",
    )
    webview.start(private_mode=False)
