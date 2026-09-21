#!/usr/bin/env bash
# Kept so existing docs/muscle memory keep working (README, REQUIREMENTS.md D43-D47
# reference this path). D48 moved the logic into k8s/deploy.sh, the one entrypoint
# for every environment - this is now exactly `k8s/deploy.sh local down`.
exec "$(dirname "${BASH_SOURCE[0]}")/deploy.sh" local down "$@"
