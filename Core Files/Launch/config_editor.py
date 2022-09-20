"""
User-friendly configs editing interface.
"""

# pylint: disable=invalid-name

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import chalk
import colorama

colorama.init()


class Router(BaseHTTPRequestHandler):
    """
    Custom tailored HTTP Router
    """

    # pylint: disable=attribute-defined-outside-init

    def _set_headers(self, cont_type: str = "text/html"):
        self.send_response(200)
        self.send_header("Content-type", cont_type)
        self.end_headers()

    def do_GET(self):
        """
        Handles GET requests.
        """
        cont_type = "text/html"
        if "css" in self.path:
            cont_type = "text/css"
        elif "js" in self.path:
            cont_type = "text/javascript"
        elif any(
            ext in self.path
            for ext in ["png", "jpg", "jpeg", "ico"]
        ):
            cont_type = f"image/{self.path.split('.')[-1]}"
        self._set_headers(cont_type=cont_type)
        self.path = "./data/static" + self.path
        if self.path.endswith('/'):
            self.path += "index.html"
            with open("data/config.json", encoding='utf') as cfg_file:
                config = json.load(cfg_file)
            with open(self.path, encoding='utf') as f:
                page = f.read()
            for key, val in config.items():
                if isinstance(val, list):
                    page = page.replace(
                        f"%{key.title().replace('_', '-')}%",
                        ",".join(
                            str(elem)
                            for elem in val
                        )
                    )
                elif isinstance(val, bool):
                    page = page.replace(
                        f"%{key.title().replace('_', '-')}%",
                        "checked" if val else ""
                    )
                else:
                    page = page.replace(
                        f"%{key.title().replace('_', '-')}%",
                        str(val)
                    )
            self.wfile.write(page.encode('utf-8'))
            return
        if self.path.endswith("success.html"):
            with open(self.path, encoding='utf') as succ_file:
                page = succ_file.read()
            with open("data/config.json", encoding='utf') as cfg_file:
                config = json.load(cfg_file)
            page = page.replace(
                "%Command-Prefix",
                config["command_prefix"]
            )
            self.wfile.write(page.encode('utf-8'))
            return
        with open(self.path, "rb", encoding='utf') as asset_file:
            asset = asset_file.read()
        self.wfile.write(asset)

    def do_POST(self):
        """
        Handles POST requests.
        """
        if self.path == '/submit':
            self._set_headers(cont_type="application/json")
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            post_data = json.loads(post_data)
            post_data = {
                key: (int(val) if str(val).isdigit() else val)
                for key, val in post_data.items()
            }
            new_configs = {}
            for key, val in post_data.items():
                if str(val).isdigit():
                    new_configs[key] = int(val)
                elif isinstance(val, list):
                    new_configs[key] = [
                        int(elem) if elem.isdigit() else elem
                        for elem in val
                    ]
                else:
                    new_configs[key] = val
            with open("data/config.json", encoding='utf') as f:
                config = json.load(f)
            new_configs = dict(
                sorted(
                    new_configs.items(),
                    key=lambda x: list(config).index(x[0])
                )
            )
            with open("data/config.json", "w", encoding='utf') as f:
                f.write(json.dumps(new_configs, indent=3))
            self.wfile.write(
                b'{"status": 200, "message": "Configs succesfully edited!"}'
            )
            return
        if self.path == "/quit":
            sys.exit(0)


class ConfigServer(HTTPServer):
    """
    Custom tailored HttpServer
    """
    def __init__(self, port: int, router: Router):
        self.port = port
        self.router = router
        super().__init__(("", self.port), self.router)

    def run(self):
        """
        Launches the server.
        """
        print(
            chalk.blue(
                f"Starting server at localhost:{self.port}..."
            )
        )
        self.serve_forever()


if __name__ == '__main__':
    server = ConfigServer(6969, Router)
    os.system("start http:localhost:6969/")
    server.run()
