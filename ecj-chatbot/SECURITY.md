# Security

## ChromaDB — CVE-2026-45829 (ChromaToast, CVSS 10.0)

CVE-2026-45829 is an unauthenticated remote code execution vulnerability in
ChromaDB's Python FastAPI server. It affects all ChromaDB 1.0.0 through at
least 1.5.8 and is currently unpatched upstream.

**This project is not exposed to this CVE.**

The vulnerability is a pre-authentication RCE reachable through ChromaDB's
HTTP API server. `src/embeddings.py` uses `chromadb.PersistentClient`
exclusively, which runs entirely in-process against a local directory
(`data/index/`) and never binds a network socket. `HttpClient`,
`chromadb.Server`, and the `chroma run` CLI are not used anywhere in this
repository.

### Rules for future changes

Do not introduce any of the following without first addressing CVE-2026-45829
in this file:

- `chromadb.HttpClient(...)` or `chromadb.AsyncHttpClient(...)`
- Running `chroma run` / the ChromaDB FastAPI server as a service
- A Dockerfile or compose file that starts a ChromaDB server container
- Any REST/FastAPI wrapper that proxies to a ChromaDB server

If a networked ChromaDB is genuinely needed, mitigate by:

1. Binding the server to `127.0.0.1` only and reaching it over an SSH
   tunnel or a private network segment, and
2. Restricting access with a reverse proxy that authenticates before any
   ChromaDB call reaches the server, and
3. Preferring the Rust frontend (`chroma-core`) once it is stable, since
   only the Python server is affected.

Track the upstream fix at
<https://github.com/chroma-core/chroma/security/advisories>.

## Reporting a vulnerability

Open a private security advisory on the repository's GitHub Security tab.
