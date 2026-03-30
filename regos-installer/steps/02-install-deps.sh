#!/usr/bin/env bash
# Step 02: Install Python dependencies inside the container

step_02_install_deps() {
  log_step "02" "Installing dependencies in container"

  # Check if neo4j is already installed
  if docker::exec_quiet "$CONTAINER_NAME" python3 -c "import neo4j" 2>/dev/null; then
    log_success "neo4j already installed — skipping"
  else
    log_info "Installing neo4j Python driver..."
    docker::exec "$CONTAINER_NAME" pip install neo4j --quiet 2>/dev/null || {
      log_error "Failed to install neo4j"
      return 1
    }
    log_success "neo4j installed"
  fi

  return 0
}
