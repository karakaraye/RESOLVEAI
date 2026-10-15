import requests

def test_api():
    s = requests.Session()
    login_res = s.post('http://127.0.0.1:8000/api/v1/auth/dev-login', json={'persona': 'operator'}, headers={'X-BIIRS-Request': '1'})
    print('Login status:', login_res.status_code)

    res = s.get('http://127.0.0.1:8000/api/v1/complaints', headers={'X-BIIRS-Request': '1'})
    data = res.json()
    complaints = data.get('items', [])
    print(f'Found {len(complaints)} complaints (total: {data.get("total", 0)})')
    
    cmp_1 = next((c for c in complaints if c['reference'] == 'CMP-2026-0001'), None)
    if cmp_1:
        cid = cmp_1['id']
        detail_res = s.get(f'http://127.0.0.1:8000/api/v1/complaints/{cid}', headers={'X-BIIRS-Request': '1'})
        print('Detail status:', detail_res.status_code)
        detail_data = detail_res.json()
        txns = detail_data.get('transactions', [])
        print(f'Complaint {cmp_1["reference"]} transactions count:', len(txns))
        for t in txns:
            print(f'  - Ref: {t["reference"]} | Amount: {t["amount"]} | Conflict: {t["conflict"][:40]}...')

        # Direct transactions endpoint
        txn_list_res = s.get(f'http://127.0.0.1:8000/api/v1/complaints/{cid}/transactions', headers={'X-BIIRS-Request': '1'})
        txns_direct = txn_list_res.json()
        print('Direct transaction endpoint count:', len(txns_direct))

        # Direct evidence endpoint
        evd_list_res = s.get(f'http://127.0.0.1:8000/api/v1/complaints/{cid}/evidence', headers={'X-BIIRS-Request': '1'})
        evd_direct = evd_list_res.json()
        print('Direct evidence endpoint count:', len(evd_direct))
        for e in evd_direct:
            print(f'  - Evidence: {e["documentReference"]} | Kind: {e["kind"]} | Verified: {e["isVerified"]}')

if __name__ == '__main__':
    test_api()
