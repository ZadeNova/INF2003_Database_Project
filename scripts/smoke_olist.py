"""Smoke the running web service through real HTTP, including all three roles.

Run through migrate so the demo passwords come from its environment. The Host
header is localhost because Docker's service name is not a public allowed host.
No credentials, cookies or response bodies are printed.
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

DEMO_LOGINS = (
    ("customer", "demo-chee-long", "/products/"),
    ("seller", "demo-seller", "/seller/"),
    ("operator", "demo-operator", "/operator/"),
)


def run(base):
    outcomes = {}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    def fetch(path, data=None):
        request = urllib.request.Request(base + path, data=data, headers={"Host": "127.0.0.1"})
        return opener.open(request, timeout=15)
    for path in ("/", "/products/", "/health/"):
        with fetch(path) as response:
            outcomes[path] = response.status
            if path == "/products/":
                content = response.read().decode()
    match = re.search(r'href="(/products/\d+/)"', content)
    if not match:
        raise RuntimeError("No visible product in the real HTTP catalogue")
    with fetch(match[1]) as response:
        outcomes["product_detail"] = response.status
        if "generated" not in response.read().decode().lower():
            raise RuntimeError("Generated content label missing from detail")
    for role, username, landing_path in DEMO_LOGINS:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        with fetch("/login/") as response:
            token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', response.read().decode()).group(1)
        payload = urllib.parse.urlencode({"username": username, "password": os.environ["DEMO_" + role.upper() + "_PASSWORD"],
                                          "csrfmiddlewaretoken": token}).encode()
        with fetch("/login/", payload) as response:
            if urllib.parse.urlsplit(response.geturl()).path != landing_path or "Log out" not in response.read().decode():
                raise RuntimeError(f"{role} HTTP login failed")
            outcomes[role + "_login"] = "passed"
    print(json.dumps(outcomes, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://web:8000")
    run(parser.parse_args().base)
