---
name: secure-coding
description: Injection, auth gaps, secrets and unsafe handling of user input.
---

Check the changed code for:

- SQL, shell, template or path injection: user input reaching a query, command, template or file path without parameterization or validation.
- Missing authentication or authorization on new endpoints, handlers or jobs. Compare with how neighboring endpoints do it.
- Secrets, tokens or keys committed in code, config or tests, or written to logs.
- User-controlled URLs fetched by the server (SSRF) or used in redirects.
- Deserializing untrusted data with unsafe loaders.
- Weak randomness used for tokens, or home-made crypto.
- Sensitive data returned in API responses or error messages.

Rate a finding critical only if an outside attacker could exploit it without special access.
