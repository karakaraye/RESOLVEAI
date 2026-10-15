import requests

def test_stage4():
    s = requests.Session()
    login_res = s.post(
        "http://127.0.0.1:8000/api/v1/auth/dev-login",
        json={"persona": "lead"},
        headers={"X-BIIRS-Request": "1"}
    )
    print("Lead login status:", login_res.status_code)

    # 1. Check complaints and detail
    res = s.get("http://127.0.0.1:8000/api/v1/complaints", headers={"X-BIIRS-Request": "1"})
    complaints = res.json().get("items", [])
    print(f"Complaints listed: {len(complaints)}")

    cmp_1 = next((c for c in complaints if c["reference"] == "CMP-2026-0001"), None)
    if cmp_1:
        cid = cmp_1["id"]
        det_res = s.get(f"http://127.0.0.1:8000/api/v1/complaints/{cid}", headers={"X-BIIRS-Request": "1"})
        print(f"Complaint {cmp_1['reference']} detail status:", det_res.status_code)
        det_data = det_res.json()

        findings = det_data.get("findings", {})
        print("Findings availability:", findings.get("availability"))
        print("Findings possibleCause:", findings.get("possibleCause"))
        print("Findings facts count:", len(findings.get("facts", [])))
        print("Findings hypotheses count:", len(findings.get("hypotheses", [])))
        print("Findings recommendedNextStep:", findings.get("recommendedNextStep"))

        related = det_data.get("related", [])
        print(f"Related records count: {len(related)}")
        for r in related:
            print(f"  - Kind: {r['kind']} | Ref: {r['reference']} | Relation: {r['relation']}")

        # 2. Test Similar Endpoint
        sim_res = s.get(f"http://127.0.0.1:8000/api/v1/complaints/{cid}/similar", headers={"X-BIIRS-Request": "1"})
        print(f"Direct similar endpoint count: {len(sim_res.json())}")

    # 3. Check Incidents
    inc_res = s.get("http://127.0.0.1:8000/api/v1/incidents", headers={"X-BIIRS-Request": "1"})
    print(f"Incidents listed: {len(inc_res.json())}")
    for inc in inc_res.json():
        print(f"  - Incident: {inc['reference']} [{inc['status']} - {inc['severity']}]: {inc['title']}")

if __name__ == "__main__":
    test_stage4()
