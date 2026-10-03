import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.model.user import User
from app.utils.password import verify_password


COMMON_PASSWORDS = [
    "123456",
    "admin",
    "admin123",
    "12345678",
    "password",
    "student",
    "test",
    "test123",
]


def main():
    db = SessionLocal()
    try:
        users = db.query(User).all()

        if not users:
            print("数据库中没有用户")
            return

        print(f"共查询到 {len(users)} 个用户\n")
        print("-" * 72)
        print(f"{'ID':<4} {'username':<16} {'name':<12} {'role':<12} {'status':<8} password_hash")
        print("-" * 72)

        for u in users:
            status = "启用" if u.status == 1 else "禁用"
            print(f"{u.id:<4} {u.username:<16} {u.name:<12} {u.role:<12} {status:<8} {u.password}")

        print("-" * 72)
        print("\n注意: bcrypt 是单向哈希, 无法反向解密出明文密码")
        print("下面尝试用常见弱密码做验证(验证登录是否可用):\n")

        for u in users:
            print(f"  [{u.username}] ", end="")
            found = False
            for pwd in COMMON_PASSWORDS:
                if verify_password(pwd, u.password):
                    print(f"✓ 匹配弱密码: {pwd}")
                    found = True
                    break
            if not found:
                print("✗ 未匹配常见弱密码 (密码可能已自定义)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
