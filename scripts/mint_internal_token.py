"""Выпустить internal JWT для служебных операций (напр. /admin/modes/reload).

Использование:
  python -m scripts.mint_internal_token --subject ops --ttl 3600

Использование токена:
  curl -X POST http://host/admin/modes/reload -H "Authorization: Bearer <token>"
"""
import argparse

from app.core.security import issue_internal_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="ops")
    parser.add_argument("--ttl", type=int, default=3600, help="срок жизни, сек")
    args = parser.parse_args()
    print(issue_internal_token(args.subject, ttl_seconds=args.ttl))


if __name__ == "__main__":
    main()
