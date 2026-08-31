"""Environment every test module needs before the app is imported.

`klartex_se.accounts` refuses to import without `LOGIN_CODE_SECRET` — a
process that starts without it would mint codes no restart and no second
worker could verify. Setting it here, at conftest import, means importing
the app anywhere in the suite works; the sign-in tests override it where
the value itself is what they are asserting about.

`BASE_URL` names the origin the tests speak from, which is what
`TestClient` uses. It decides two things the sign-in suite depends on: the
session cookie's `secure` flag — a `Secure` cookie is never sent back over
`http://testserver`, so the default `https://app.klartex.se` would make
every signed-in request anonymous — and which `Origin` header counts as
same-origin.

`setdefault`, not assignment, so a caller can pin either from outside.
"""

import os

os.environ.setdefault("LOGIN_CODE_SECRET", "test-login-code-secret")
os.environ.setdefault("BASE_URL", "http://testserver")
