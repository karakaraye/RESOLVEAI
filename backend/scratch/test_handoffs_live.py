import json
import urllib.request
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Dev sign in as operator
login_data = json.dumps({"persona": "operator"}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/auth/dev-login",
    data=login_data,
    headers={"Content-Type": "application/json", "X-BIIRS-Request": "1"}
)
with opener.open(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    print("User logged in:", data["user"]["displayName"], "Role:", data["user"]["roleLabel"])

# 2. Get handoff summary counts
req2 = urllib.request.Request("http://127.0.0.1:8000/api/v1/handoffs/summary")
with opener.open(req2, timeout=10) as resp:
    summary = json.loads(resp.read().decode())
    print("Handoffs Summary:", summary)

# 3. Get handoffs list
req3 = urllib.request.Request("http://127.0.0.1:8000/api/v1/handoffs")
with opener.open(req3, timeout=10) as resp:
    handoffs_page = json.loads(resp.read().decode())
    print(f"Handoffs Total: {handoffs_page['total']}")
    for h in handoffs_page["items"]:
        print(f"  - {h['complaint']['reference']} [{h['state']}] -> {h['team']['name']} (Channel: {h['channel']}, Retries: {len(h['attempts'])})")

# 4. Get forwarding options for a complaint
req4 = urllib.request.Request(f"http://127.0.0.1:8000/api/v1/complaints/{handoffs_page['items'][0]['complaint']['id']}/forwarding-options")
with opener.open(req4, timeout=10) as resp:
    opts = json.loads(resp.read().decode())
    print("Forwarding options teams:", [t["name"] for t in opts["teams"]])
    print("Shareable summary:", opts["shareableSummary"])

# 5. Operations health check
req5 = urllib.request.Request("http://127.0.0.1:8000/api/v1/operations/health")
try:
    with opener.open(req5, timeout=10) as resp:
        print("Operations Health (HTTP 200):", json.loads(resp.read().decode()))
except urllib.error.HTTPError as e:
    print(f"Operations Health (HTTP {e.code}):", json.loads(e.read().decode()))
