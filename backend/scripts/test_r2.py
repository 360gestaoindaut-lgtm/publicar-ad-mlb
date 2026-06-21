import socket
import asyncio
import httpx
from app.config import get_settings


async def main():
    s = get_settings()
    host = f"{s.r2_account_id}.r2.cloudflarestorage.com"

    # DNS
    try:
        ip = socket.gethostbyname(host)
        print(f"DNS OK: {host} -> {ip}")
    except Exception as e:
        print(f"DNS FALHOU: {e}")
        return

    # TCP na porta 443
    try:
        sock = socket.create_connection((host, 443), timeout=5)
        sock.close()
        print("TCP 443 OK")
    except Exception as e:
        print(f"TCP 443 FALHOU: {e}")

    # HTTPS sem verificação
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            r = await client.get(f"https://{host}/")
        print(f"HTTPS OK: {r.status_code}")
    except Exception as e:
        print(f"HTTPS FALHOU: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
