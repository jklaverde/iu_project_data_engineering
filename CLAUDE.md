# CLAUDE.md — start here

Loaded automatically at the start of every session. It is a **map and a set of rules**, not a
copy of the docs: where a fact has a canonical home, this file points to it instead of
repeating it (repeats drift). Sections 2 and 3 are the ones to act on first.

## 1. What this is

A role-based environmental sensor platform for the municipality of Lingen (Ems): Python
producer → Kafka → Spark Structured Streaming → Cassandra, with a FastAPI + React web app
(planner role, admin role) and a Grafana KPI deck on top. Everything runs on Kubernetes:
**k3d locally, native single-node k3s in production**, from one manifest set (`k8s/base`),
deployed by one script (`k8s/deploy.sh`). `docker-compose.yml` is a legacy fallback only.

## 2. Catch-up checklist — do this before changing anything

Other sessions and humans commit to this repo and touch the cluster while you are not
looking (this has already happened: two commits landed with no decision-log entry). Never
trust a snapshot, including section 3 below — verify.

1. `git status && git log --oneline -15`. Compare the newest commit with the newest
   `D<n>` row in `REQUIREMENTS.md` §11. **A commit with no D-row is an undocumented
   change** — read its diff and record it (see §6, "Catch-up").
2. Read `docs/operations.html` → `#status` (what is done/verified) and `#next` (the
   prioritized backlog). That page is the canonical state; this file is only a pointer.
3. **This host is production** (`vmd204054`, 11 GiB RAM, single-node k3s). Look before you
   touch: `sudo k8s/deploy.sh prod check` and `sudo kubectl -n iot-pipeline get pods`
   (kubeconfig `/etc/rancher/k3s/k3s.yaml`, root-only). Memory is tight — see §8.
4. If the user's request touches deployment, read `README.md` → "Bringing the infrastructure
   up and down" and `docs/deployment.html` first; both explain *why* local and production
   differ.

## 3. State snapshot — dated 2026-09-23 (update this at the end of every session)

| Item | State |
|---|---|
| Latest decision | **D51** (D48 = unified deploy script, D49/D50 = post-go-live hardening and memory resize, D51 = Cassandra node-deploy notice reworded; not yet deployed). Next free number: **D52**. |
| Phases | P1–P5, P8–P11 done and live-verified. Interim VPS done (now single-node k3s). **Full P6 (3-VPS, HA, TLS) and P7 (48 h endurance) not started.** |
| Production | Single-node k3s on this host; `iot-pipeline` namespace deployed 2026-09-21 ~18:14 CEST, all pods `Running`, 0 restarts, ~3.7 GiB memory available. `kafka-ui` intentionally scaled to 0. |
| `deploy.sh` verification | `check`, argument handling and validation paths: run. **`up`/`update`/prod `down` were not run by the session that wrote them.** The timestamps (images built → `generated/` staged → Secret created within 1 s) match `deploy.sh prod up` having been run at ~18:14 CEST, but nobody has confirmed it. **Confirm with the user, then record the result in D48.** |
| Not built | TLS/ingress · image registry · multi-node · automated backups · a rehearsed restore · `k8s/overlays/prod` |
| Unverified claim | Whether `ufw` alone can close ports that k3s servicelb publishes (`docs/deployment.html` §6 says to test from another machine). |
| No test suite | There are **no automated tests** in this repo. "Verified" means a live run, recorded in a D-entry. Do not imply otherwise. |

## 4. Where things are

| Path | What it is |
|---|---|
| `REQUIREMENTS.md` | The spec: scope, architecture (§4), FR/NFR/UC ids, **decision log (§11, D1…)**, risks (§13), phases (§14). |
| `docs/*.html` | The documentation site (open `docs/index.html` directly). `operations.html` = status, decisions, backlog, troubleshooting log. `deployment.html` = production runbook. `reference.html` = file-by-file map. `containers.html` (+`containers-data.js`) = per-container reference. |
| `README.md` | User-facing: prerequisites, deploy commands, config, walkthrough. |
| `k8s/deploy.sh` | **The** deploy entrypoint: `<local\|prod> <check\|up\|update\|status\|down>`. `local-up.sh`/`local-down.sh` are thin wrappers. |
| `k8s/base/` | Kustomize manifests (no Helm). `config.env` = non-secret settings. `generated/` is gitignored, staged from `infra/` by `deploy.sh`. |
| `backend/` `frontend/` | FastAPI app + React/TS UI, built into **one image** (`backend/Dockerfile`), which also bundles the docs site for the admin "Docs" tab. |
| `producer/` `spark_job/` `kaggle_repository/` | Ingestion, streaming job (also the `spark-worker` image), dataset fetch job. |
| `infra/` | Cassandra image + schema, Prometheus, Loki, Promtail, Grafana provisioning. |
| `docker-compose.yml` | Legacy fallback. Reads *all* settings from `.env`. |
| `development_notes/`, `docs/internal/`, `.claude/` | Gitignored, local-only. Don't rely on them existing. |

## 5. Run, verify, deploy

```
k8s/deploy.sh local check|up|update <svc>|status|down     # k3d (needs Docker + k3d)
sudo k8s/deploy.sh prod check|up|update <svc>|status|down  # this host; root needed
kubectl kustomize k8s/base >/dev/null                      # manifests still render?
bash -n k8s/deploy.sh                                      # script still parses?
```

- **Which command for which change** (README "Changing things on a running stack"): code →
  `update <svc>` · `config.env`/manifests/`infra/` → `up` · a `.env` secret → `up` *and*
  `kubectl rollout restart` the pods that read it.
- Services accepted by `update`: `backend producer cassandra spark-job spark-worker grafana
  dataset-init`. `spark_job/` code needs **both** `spark-job` and `spark-worker`.
- Requirements files are hash-pinned: regenerate with `pip-compile --generate-hashes`
  (see `backend/README.md`), never hand-edit. Frontend `package-lock.json` is committed and
  the npm supply-chain policy (NFR-10, `frontend/.npmrc`) applies to any new dependency.
- Comment-only edits to manifests don't roll pods; prove that with
  `git diff -U0 k8s/base | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '^[+-]\s*#'`.

## 6. Conventions and playbooks

**Rules that were learned the hard way**

1. **Decision log is mandatory.** Any behavior-changing commit gets a `D<n>` row in
   `REQUIREMENTS.md` §11 and, if it involves a bug/incident, an entry in
   `docs/operations.html`. Commit subjects for logged work start with the D-number.
2. **Say what was and wasn't verified.** "Live-verified" must state what was actually run
   (D46/D47/D48 are the model). Things you could not run are written down as unverified,
   in the doc, not only in chat.
3. **User-facing surfaces never cite internal codes** (`D42`, `UC-12`, `NFR-4`,
   `REQUIREMENTS.md`): UI text, backend error messages shown in the UI, Grafana panel
   titles and alert summaries. Source-code comments *may* (commits 2829b89, 59db956).
4. **Secrets:** never print `.env` values, never commit `.env`, no `set -x` in scripts that
   read it. On Kubernetes `.env` feeds only the six `app-secrets` keys.
5. **Troubleshooting anchors are permanent.** `docs/operations.html` incidents use ids like
   `p5-3` that code comments link to. Add new ones (`p12-1`…); never renumber.
6. **New docs page ⇒ edit `backend/Dockerfile`.** The docs site is bundled file by file
   (never `COPY docs/`); a page not listed there won't appear in the admin Docs tab. Also add
   it to `docs/index.html` and `docs/reference.html`.
7. **`docs/containers-data.js`** must match `docker-compose.yml` (its own header says so);
   Kubernetes limits live in `k8s/base` and are not mirrored there.

**Playbook — new requirement**
Add/adjust the FR/NFR/UC in `REQUIREMENTS.md` §6–8 → add a D-row → if it changes scope, add a
"vX changes" line to the header and bump the version (D44–D50 did not; D42/D43 did) → add it
to the phase list in §14 → implement → update `operations.html` (`#status`, `#next`),
`reference.html` (new files), `README.md` if a user-visible step changed.

**Playbook — new milestone / phase**
Same as above, plus a row in `operations.html`'s phase table and a new phase group in the
troubleshooting log if you expect incidents. Record what is *not* done in the same commit.

**Playbook — bug or incident**
Reproduce against the real cluster first (`kubectl logs`, `describe`, `top`). Fix. Add an
incident (`<details class="incident" id="pN-M">`) or a D-row explaining root cause, not just
the symptom. State how you verified the fix.

**Playbook — catch-up (someone changed things without documenting)**
`git log` since the last D-row → read each diff → add D-rows attributed to the commit hash,
flagging that details come from the commit message and were not re-verified by you →
update the affected docs (`operations.html`, `README.md`, `deployment.html`, this file's §3).
D49/D50 were written this way.

**Playbook — end of session (do all, in this order)**
1. D-rows and `operations.html` updated. 2. Affected user docs updated (README,
`deployment.html`, `reference.html`). 3. **§3 of this file refreshed and re-dated.**
4. `kubectl kustomize k8s/base` and `bash -n k8s/deploy.sh` pass. 5. Commit only when the
user asks. **Pushing needs the user:** this environment has no GitHub credentials — ask them
to run `! git push`.

## 7. Working with this user

- They run production commands **by hand to learn**. When asked "what's the right command",
  give it and explain it; do not execute it. Read-only inspection is fine.
- They expect every environment difference to be **explained and justified**, and expect
  honesty about gaps ("not built", "not verified") rather than reassurance.
- Confirm before anything irreversible on the production cluster (`down`, deleting PVCs,
  `k3s-uninstall.sh`). The Cassandra volumes are the only copy of the sensor history.
- Git identity is `jklaverde`. Commits, and pushes especially, only on request.

## 8. Gotchas that have already cost time

| Gotcha | Detail / where documented |
|---|---|
| `.env` ≠ `k8s/base/config.env` | On Kubernetes `.env` is read only for 6 secrets; `PRODUCER_RATE_MSGS_PER_SEC`, `BACKEND_COOKIE_SECURE` etc. live in `config.env`. `deploy.sh` warns on drift. (README "Where configuration lives"; D48) |
| `up` doesn't ship code | Images are `:local`; same tag ⇒ no pod-spec change ⇒ old container keeps running. Use `update <svc>`. (D48) |
| `kubectl` is `k3s kubectl` | On this host it ignores `~/.kube/config`; scripts set `KUBECONFIG` explicitly. (D46) |
| Images exist only in k3s containerd | No registry. `crictl rmi --prune` or kubelet GC (disk > ~85%) removes them ⇒ `ErrImagePull` on pod recreation. Re-run `up`. (`deployment.html` §8) |
| **Memory budget** | Container limits sum ≈ 9.6 GiB on an 11 GiB host (D50). Adding a pod, raising a limit, or scaling Cassandra needs a `kubectl top nodes` check; a 2nd/3rd Cassandra node OOM-killed pods before (D44/D45). |
| Compose bypasses `ufw` | Docker's iptables rules run before ufw; every compose-published port is internet-reachable. (`deployment.html` appendix; D48) |
| Removing a Cassandra node | Deleting its pod/PVC without `nodetool removenode` leaves the ring thinking it exists. FR-N2 is scale-up only. (D44) |
| Admin Cassandra-deploy / Kubernetes tabs | Need the Kubernetes API ⇒ `503` under compose. |
| `kustomize` can't read outside `k8s/base` | Hence the gitignored `k8s/base/generated/` staged by `deploy.sh`. A bare `kubectl apply -k` on a fresh clone fails. |
| A poisoned Kafka message | Used to crash all three streaming queries in a loop; malformed events are now dropped in `spark_job/schema.py` (D49). |
| Init Jobs are immutable | `apply` failing with "field is immutable" ⇒ delete that Job, re-run `up`. |

## 9. Open threads (highest value first — canonical list: `docs/operations.html#next`)

1. **Close the D48 loop:** ask the user whether `deploy.sh prod up` was what produced the
   current deployment; record the real outcome; then exercise `update` and prod `down`'s
   prompt (the latter destroys data — only with the user's go-ahead).
2. **Verify the firewall from outside** (`nc -vz <ip> 8000 3000 6443 10250`); fix the docs
   whichever way it comes out.
3. **TLS** (Caddy interim, §6b of `deployment.html`), then flip `BACKEND_COOKIE_SECURE` in
   `config.env` — not `.env`.
4. **Rehearse a backup restore.** Never done.
5. **Production overlay** (`k8s/overlays/prod`: registry images, ingress + TLS, replicas) —
   the intended path to full P6; lift `deploy.sh`'s multi-node refusal only after it exists.
6. P7 endurance run (needs 100 GB disk headroom and the memory budget in §8 re-checked).
7. UC-7 control panel (deferred since Phase 1); the tombstone/`READ_TOO_MANY_TOMBSTONES`
   debt (`operations.html` P5 §3).
