# -*- coding: utf-8 -*-
"""
محرر ردود البوت - صفحة ويب محلية لتعديل الردود بدون أي برمجة.

طريقة الاستخدام:
1. شغّل هذا الملف بالأمر:  python editor.py
2. افتح المتصفح على الرابط:  http://localhost:8765
3. عدّل/أضف/احذف الردود من الصفحة، واضغط "حفظ الكل".
4. التغييرات تُحفظ مباشرة في config.json.
5. إذا كان البوت يعمل بنفس الوقت، استخدم أمر /reload داخل تلجرام
   حتى يقرأ البوت آخر تعديل بدون الحاجة لإعادة تشغيله.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
HTML_PATH = os.path.join(BASE_DIR, "editor.html")
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send_html(HTML_PATH)
        elif self.path == "/api/config":
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._send_json(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                new_data = json.loads(raw)
            except Exception as e:
                self._send_json({"error": str(e)}, status=400)
                return

            # نقرأ الكونفيج الحالي ونحدّث الأقسام القابلة للتعديل من الصفحة
            # (responses / welcome / farewell) مع الحفاظ على باقي الإعدادات
            # مثل settings و callback_responses كما هي إن لم تُرسل
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                full_config = json.load(f)

            full_config["responses"] = new_data.get("responses", [])

            if "welcome" in new_data:
                full_config["welcome"] = new_data["welcome"]
            if "farewell" in new_data:
                full_config["farewell"] = new_data["farewell"]
            if "callback_responses" in new_data:
                full_config["callback_responses"] = new_data["callback_responses"]
            if "start" in new_data:
                full_config["start"] = new_data["start"]
            if "settings" in new_data:
                # نحافظ على أي إعداد قديم غير مرسل من الصفحة، ونحدّث الباقي فقط
                full_config.setdefault("settings", {}).update(new_data["settings"])

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(full_config, f, ensure_ascii=False, indent=2)

            self._send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # تقليل الرسائل المطبوعة في الكونسول
        pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"✅ محرر الردود يعمل الآن.")
    print(f"➡️  افتح هذا الرابط في المتصفح: http://localhost:{PORT}")
    print("اضغط Ctrl+C للتوقف.")
    server.serve_forever()


if __name__ == "__main__":
    main()
