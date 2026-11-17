import requests

INSTANCE = "https://dev341882.service-now.com/login.do?user_name=admin&sys_action=sysverb_login&user_password=na%2FGD%3D4RT6df"
USER = admin
PASSWORD = 'na/GD=4RT6df'   # temporary, for this test only

url = f"{INSTANCE}/api/now/table/incident"

response = requests.get(
    url,
    auth=(USER, PASSWORD),
    headers={"Accept": "application/json"},
    params={"sysparm_limit": 1},
    timeout=15,
)

print("Status code:", response.status_code)
print(response.text[:500])