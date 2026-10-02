import urllib.request
import json

BASE_URL = "http://localhost:8000"


def login(username, password):
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


print("=== 测试1: 管理员正确登录 ===")
status_code, data = login("testadmin", "123456")
print(f"状态码: {status_code}")
print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

print("\n=== 测试2: 学生正确登录 ===")
status_code, data = login("student1", "123456")
print(f"状态码: {status_code}")
print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

print("\n=== 测试3: 错误密码 ===")
status_code, data = login("testadmin", "wrongpassword")
print(f"状态码: {status_code}")
print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")

print("\n=== 测试4: 不存在的用户 ===")
status_code, data = login("nobody", "123456")
print(f"状态码: {status_code}")
print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
