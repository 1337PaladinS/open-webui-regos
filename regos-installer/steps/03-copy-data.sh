#!/usr/bin/env bash
# Step 03: Copy data files into the container

step_03_copy_data() {
  log_step "03" "Copying data files to container"

  local data_dir="${INSTALLER_DIR}/data"
  local dest="${CONTAINER_DATA_DIR:-/app/backend/data}"

  # Ensure destination directory exists
  docker::exec_quiet "$CONTAINER_NAME" mkdir -p "$dest" 2>/dev/null

  local files=("regulatory_thresholds.json" "concepts.json" "apas_metric_mappings.json")
  local copied=0

  for f in "${files[@]}"; do
    if [[ ! -f "${data_dir}/${f}" ]]; then
      log_warn "File not found: ${data_dir}/${f} — skipping"
      continue
    fi
    docker::copy_to "${data_dir}/${f}" "$CONTAINER_NAME" "${dest}/${f}" || {
      log_error "Failed to copy ${f}"
      continue
    }
    log_success "Copied ${f} → ${dest}/${f}"
    ((copied++))
  done

  # Handle the large graph file separately (not in git, user must provide)
  if [[ -f "${data_dir}/chaptor_24_graph.json" ]]; then
    log_info "Found chaptor_24_graph.json — copying (this may take a moment)..."
    docker::copy_to "${data_dir}/chaptor_24_graph.json" "$CONTAINER_NAME" "${dest}/chaptor_24_graph.json" || {
      log_error "Failed to copy chaptor_24_graph.json"
    }
    log_success "Copied chaptor_24_graph.json"
    ((copied++))
  else
    log_info "chaptor_24_graph.json not found — skipped (see docs/GRAPH_SETUP.md)"
  fi

  log_info "${copied} data file(s) copied"
  return 0
}
