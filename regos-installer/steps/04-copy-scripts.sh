#!/usr/bin/env bash
# Step 04: Copy utility and demo scripts into the container

step_04_copy_scripts() {
  log_step "04" "Copying utility scripts to container"

  local scripts_dir="${INSTALLER_DIR}/scripts"
  local dest="${CONTAINER_SCRIPTS_DIR:-/tmp}"

  local files=("verify_hashes.py" "demo_show_records.py" "demo_tamper.py" "demo_reset.py")
  local copied=0

  for f in "${files[@]}"; do
    if [[ ! -f "${scripts_dir}/${f}" ]]; then
      log_warn "Script not found: ${scripts_dir}/${f} — skipping"
      continue
    fi
    docker::copy_to "${scripts_dir}/${f}" "$CONTAINER_NAME" "${dest}/${f}" || {
      log_error "Failed to copy ${f}"
      continue
    }
    log_success "Copied ${f} → ${dest}/${f}"
    ((copied++))
  done

  log_info "${copied} script(s) copied"
  return 0
}
