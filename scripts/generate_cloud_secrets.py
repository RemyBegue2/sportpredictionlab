from __future__ import annotations

import secrets


def main() -> int:
    print("APP_SESSION_SECRET=" + secrets.token_urlsafe(48))
    print("APP_PASSWORD=" + secrets.token_urlsafe(24))
    print("Conservez ces valeurs dans le gestionnaire de secrets de la plateforme. Ne les versionnez pas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
