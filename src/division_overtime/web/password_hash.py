from __future__ import annotations

import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("Web admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not password:
        raise SystemExit("Password must not be empty.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
