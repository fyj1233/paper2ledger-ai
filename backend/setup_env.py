"""安装脚本调用：backend/.env 的 JWT_SECRET 为空或缺行时生成一个随机值。

密钥留空的话运行期会退化成进程内随机密钥（每次重启全员重新登录），
所以这一步在装环节就做掉，且绝不覆盖已有的值。
"""

import re
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"


def main() -> None:
    if not ENV.exists():
        return
    text = ENV.read_text(encoding="utf-8")
    if re.search(r"(?m)^JWT_SECRET=[^\r\n]+", text):
        return
    secret = secrets.token_hex(32)
    if re.search(r"(?m)^JWT_SECRET=", text):
        text = re.sub(r"(?m)^JWT_SECRET=[^\r\n]*", "JWT_SECRET=" + secret, text)
    else:
        text = text.rstrip("\r\n") + "\nJWT_SECRET=" + secret + "\n"
    ENV.write_text(text, encoding="utf-8")
    print("[setup_env] 已为 backend/.env 生成随机 JWT_SECRET")


if __name__ == "__main__":
    main()
