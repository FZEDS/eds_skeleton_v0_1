#!/usr/bin/env python3
from app.services.legifrance_client import LegifranceClient

def main() -> int:
    c = LegifranceClient()
    ok = c.ping()
    print("BASE_API:", c.BASE_API)
    print("ping:", "OK" if ok else "KO")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
