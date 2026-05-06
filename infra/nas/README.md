# NAS migration — runbook

> Source: `PLAN_v2.1` §8.4, `workflows/01_INFRASTRUCTURE_AND_HOST.md` §5.6.

## Why this exists

Day-1 storage layout is **identical** to the layout we'd want post-NAS. Every persistent volume in `docker-compose.yml` is a bind mount under `/srv/iic/<service>` — no Docker named volumes anywhere. Migrating to a NAS is a `mount` change, not a refactor. The compose file is **never touched**.

## Hardware target

- **Synology DS923+** (~$600 diskless) or **QNAP TS-464** (~$650).
- 2 × 8 TB Seagate IronWolf in mirror (SHR-1 / RAID-1).
- 2.5 GbE link to the mini-PC.

## Migration day (≈ 1 evening)

1. **NAS prep.** Enable NFS, create shared folder `iic` at `/volume1/iic`, allow NFS access from the mini-PC's IP, squash to `iic` UID/GID. Set `no_root_squash` for the migration window only — revert after.
2. **CI confirms green.** `infra/nas/migrate.sh --dry-run` has been running on every commit since day 1 (see `.github/workflows/nas-dryrun.yml`). Last run must be green.
3. **Stop the stack.** `sudo systemctl stop iic.service`.
4. **Apply.** `NAS_HOST=nas.local NAS_PATH=/volume1/iic bash infra/nas/migrate.sh --apply`.
5. **Verify.** `mount | grep /srv/iic` shows the NFS mount; `sudo systemctl start iic.service`; check `docker compose ps` for all green; confirm a WeCom test brief arrives.
6. **Update restic.** `RESTIC_REPOSITORY_LOCAL` now points at NAS-backed storage; re-init the offsite B2 link.

## Postgres + NFS caveat

Postgres on NFS is fine on **NFSv4.1+ with `hard,nolock`** semantics, but only if the NAS storage layer is reliable. If unsure, use:

```bash
KEEP_PG_LOCAL=1 bash infra/nas/migrate.sh --apply
```

This keeps the Postgres data dir at `/srv/iic-local/pg` while moving everything else to NFS. The compose file already mounts `/srv/iic/pg`, so before flipping `KEEP_PG_LOCAL=1` you'll need a one-line edit to `docker-compose.yml` mapping that bind to the local-only path.

## Rollback

If anything is wrong post-`--apply`, the rollback is symmetric:

```bash
sudo systemctl stop iic.service
sudo umount /srv/iic
sudo sed -i '/\/volume1\/iic/d' /etc/fstab
# data is still on the NAS; copy it back to local NVMe if desired:
rsync -aHAX nas.local:/volume1/iic/ /srv/iic/
sudo systemctl start iic.service
```
