#!/usr/bin/env bash
# docker.sh — Docker interaction utilities for regos-installer

docker::check_installed() {
  if ! command -v docker &>/dev/null; then
    log_error "Docker is not installed or not in PATH"
    return 1
  fi
  log_debug "Docker found: $(docker --version)"
}

docker::find_container() {
  local name="${1:-open-webui}"
  local cid
  cid=$(docker ps --filter "name=${name}" --format '{{.ID}}' 2>/dev/null | head -1)
  if [[ -z "$cid" ]]; then
    log_error "No running container matching '${name}'"
    log_info "Running containers:"
    docker ps --format '  {{.Names}} ({{.Image}})' 2>/dev/null || true
    return 1
  fi
  echo "$cid"
}

docker::container_running() {
  local name="${1:-open-webui}"
  docker ps --filter "name=${name}" --format '{{.Names}}' 2>/dev/null | grep -q .
}

docker::exec() {
  local container="$1"; shift
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    log_info "[DRY RUN] docker exec -it ${container} $*"
    return 0
  fi
  docker exec -it "$container" "$@"
}

docker::exec_quiet() {
  local container="$1"; shift
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    log_info "[DRY RUN] docker exec ${container} $*"
    return 0
  fi
  docker exec "$container" "$@"
}

docker::copy_to() {
  local src="$1" container="$2" dest="$3"
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    log_info "[DRY RUN] docker cp ${src} ${container}:${dest}"
    return 0
  fi
  docker cp "$src" "${container}:${dest}"
}

docker::file_exists() {
  local container="$1" path="$2"
  docker exec "$container" test -f "$path" 2>/dev/null
}

docker::get_info() {
  local container="$1"
  local image status
  image=$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null)
  status=$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null)
  echo "image=${image} status=${status}"
}
