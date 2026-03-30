#!/usr/bin/env bash
# api.sh — Open WebUI REST API utilities for regos-installer

api::health_check() {
  local url="${1}/api/config"
  local status
  status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null)
  if [[ "$status" == "200" ]]; then
    return 0
  fi
  log_error "API health check failed (HTTP ${status}) at ${url}"
  return 1
}

api::call() {
  local method="$1" endpoint="$2" data="${3:-}"
  local url="${OPENWEBUI_URL}${endpoint}"

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    log_info "[DRY RUN] ${method} ${url}"
    [[ -n "$data" ]] && log_debug "Payload: ${data:0:200}..."
    echo '{"dry_run": true}'
    return 0
  fi

  local args=(-s -X "$method" -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" -H "Content-Type: application/json")
  [[ -n "$data" ]] && args+=(-d "$data")

  local response http_code body
  response=$(curl "${args[@]}" -w '\n%{http_code}' "$url" 2>/dev/null)
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  log_debug "${method} ${endpoint} → HTTP ${http_code}"
  echo "$body"
  [[ "$http_code" =~ ^2 ]] && return 0 || return 1
}

api::call_status() {
  local method="$1" endpoint="$2" data="${3:-}"
  local url="${OPENWEBUI_URL}${endpoint}"

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    echo "200"
    return 0
  fi

  local args=(-s -X "$method" -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" -H "Content-Type: application/json" -o /dev/null -w '%{http_code}')
  [[ -n "$data" ]] && args+=(-d "$data")

  curl "${args[@]}" "$url" 2>/dev/null
}

api::retry() {
  local max_attempts="${1:-3}" delay="${2:-2}"; shift 2
  local attempt=1
  while [[ $attempt -le $max_attempts ]]; do
    if "$@"; then
      return 0
    fi
    log_warn "Attempt ${attempt}/${max_attempts} failed, retrying in ${delay}s..."
    sleep "$delay"
    ((attempt++))
    ((delay *= 2))
  done
  log_error "All ${max_attempts} attempts failed"
  return 1
}

api::function_exists() {
  local func_id="$1"
  local status
  status=$(api::call_status GET "/api/v1/functions/id/${func_id}")
  [[ "$status" == "200" ]]
}

api::register_function() {
  local func_id="$1" func_file="$2" func_type="${3:-filter}"
  local name payload_file

  name=$(echo "$func_id" | sed 's/_/ /g; s/\b\(.\)/\u\1/g')
  payload_file="/tmp/regos_payload_${func_id}.json"

  # Build JSON payload via Python (avoids shell escaping issues with large files)
  if ! python3 -c "
import json, re, sys
func_file = sys.argv[1]
func_id = sys.argv[2]
func_name = sys.argv[3]
func_type = sys.argv[4]
with open(func_file) as f:
    code = f.read()
m = re.search(r'\"\"\"(.*?)\"\"\"', code, re.DOTALL)
desc = m.group(1).strip().split('\n')[0] if m else f'RegOS {func_name} function'
payload = json.dumps({
    'id': func_id,
    'name': func_name,
    'type': func_type,
    'meta': {'description': desc},
    'content': code
})
with open(sys.argv[5], 'w') as out:
    out.write(payload)
" "$func_file" "$func_id" "$name" "$func_type" "$payload_file" 2>/dev/null; then
    log_error "Failed to build payload for ${func_id}"
    return 1
  fi

  # Use curl with @file to avoid shell argument size limits
  local url endpoint http_code
  if api::function_exists "$func_id"; then
    log_info "Function '${func_id}' exists — updating..."
    endpoint="/api/v1/functions/id/${func_id}/update"
  else
    log_info "Registering function '${func_id}'..."
    endpoint="/api/v1/functions/create"
  fi

  url="${OPENWEBUI_URL}${endpoint}"
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
    log_info "[DRY RUN] POST ${url}"
    rm -f "$payload_file"
    return 0
  fi

  http_code=$(curl -s -X POST \
    -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
    -H "Content-Type: application/json" \
    -d @"$payload_file" \
    -o /dev/null -w '%{http_code}' \
    "$url" 2>/dev/null)

  rm -f "$payload_file"
  log_debug "POST ${endpoint} → HTTP ${http_code}"
  [[ "$http_code" =~ ^2 ]] && return 0 || return 1
}
