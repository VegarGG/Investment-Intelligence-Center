#!/usr/bin/env bash
#
# v2.5 T2.7 / B3.3a — provision a new Futu ID's bind-mount + sops template.
#
# Usage:  ./tools/futu/add_id.sh <futu_id>
#
# Effects:
#   - Computes futu_id_hash = sha256 prefix.
#   - Creates /srv/iic/futu/<futu_id_hash>/{openD-config,openD-logs,snapshots}.
#   - Drops a sops-encrypted credential template into openD-config/.
#   - Appends an entry to apps/agent_futu/config/futu_ids.yaml.
#
# This script does NOT connect to FUTU. Real OpenD lighting up + the
# real penetration test belong to phase B3.3b — see
# docs/security/FUTU_readonly_review.md.

set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: $0 <futu_id>" >&2
  exit 64
fi

futu_id="$1"
hash="fid_$(printf '%s' "${futu_id}" | shasum -a 256 | cut -c1-16)"

root="/srv/iic/futu/${hash}"
mkdir -p "${root}/openD-config" "${root}/openD-logs" "${root}/snapshots"

# Credential template — sops-encrypts on write per .sops.yaml policy.
cred_template="${root}/openD-config/credentials.yaml.sops"
if [ ! -f "${cred_template}" ]; then
  cat > "${cred_template}.tmpl" <<EOF
# IIC FUTU credentials — sops-encrypt before commit
# DO NOT commit a plaintext copy.
futu_id: REPLACE_WITH_LOGIN_ID
trd_env: SIMULATE       # NEVER set to LIVE without explicit security review approval
unlock_password: ""     # MUST stay empty — agent_futu never calls unlock_trade()
EOF
  echo "Wrote credential template: ${cred_template}.tmpl"
  echo "Next steps:"
  echo "  1. Edit ${cred_template}.tmpl with the real Futu ID."
  echo "  2. Run: sops --encrypt --in-place --age \"\$(cat .sops.age.pub)\" ${cred_template}.tmpl"
  echo "  3. Rename ${cred_template}.tmpl -> ${cred_template}"
fi

# Append to the registry (creates the file on first call).
registry="apps/agent_futu/config/futu_ids.yaml"
mkdir -p "$(dirname "${registry}")"
if ! [ -f "${registry}" ]; then
  printf "# IIC v2.5 T2.7 — registered Futu IDs (hash, bind-mount, OpenD port)\nfutu_ids: []\n" \
    > "${registry}"
fi

next_port=$((11111 + $(grep -c "openD_port:" "${registry}" 2>/dev/null || echo 0)))
cat >> "${registry}" <<EOF
  - futu_id_hash: ${hash}
    bind_mount: ${root}
    openD_port: ${next_port}
EOF

echo "Registered Futu ID under ${root} (OpenD port ${next_port})."
echo "agent_futu will pick it up on next bounce."
