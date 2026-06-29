"""Пополнить баланс партнёра (ручное начисление админом).

Использование:
  python -m scripts.topup <api_key_id> <amount_credits> [--note "оплата за июнь"]

1 кредит = 1 ₽. Печатает новый баланс. Работает даже если BILLING_ENABLED=false
(можно пополнить заранее).
"""
import argparse

from app.db.session import SessionLocal
from app.services import billing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("api_key_id")
    parser.add_argument("amount_credits", type=int, help="сколько кредитов начислить (>0)")
    parser.add_argument("--note", default=None, help="комментарий (напр. основание оплаты)")
    args = parser.parse_args()

    with SessionLocal() as db:
        new_balance = billing.topup(db, args.api_key_id, args.amount_credits, args.note)

    print("Top-up done:")
    print(f"  api_key_id:   {args.api_key_id}")
    print(f"  added:        {args.amount_credits} credits")
    print(f"  new balance:  {new_balance} credits")


if __name__ == "__main__":
    main()
