"""Создать API-ключ для сервера-источника.

Использование:
  python -m scripts.create_api_key "My Site" --callback https://site.com/cb

Печатает сырой ключ ОДИН раз — сохрани его, в БД лежит только хеш.
"""
import argparse

from app.core.security import generate_api_key
from app.db.session import SessionLocal
from app.models import ApiKey


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--callback", default=None, help="callback_url по умолчанию")
    args = parser.parse_args()

    raw, key_hash = generate_api_key()
    with SessionLocal() as db:
        key = ApiKey(name=args.name, key_hash=key_hash, callback_url=args.callback, status="active")
        db.add(key)
        db.commit()
        db.refresh(key)

    print("API key created (save the raw key now, it won't be shown again):")
    print(f"  id:        {key.id}")
    print(f"  name:      {args.name}")
    print(f"  raw key:   {raw}")
    print(f"  callback:  {args.callback}")


if __name__ == "__main__":
    main()
