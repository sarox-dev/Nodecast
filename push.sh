#!/usr/bin/env bash
# Release helper. GitHub Actions owns app/version.json and CHANGELOG.md.
set -euo pipefail

readonly TAG="${1:-}"
readonly INITIAL_WAIT_SECONDS="${NODECAST_RELEASE_INITIAL_WAIT_SECONDS:-35}"
readonly POLL_SECONDS="${NODECAST_RELEASE_POLL_SECONDS:-20}"
readonly TIMEOUT_SECONDS="${NODECAST_RELEASE_TIMEOUT_SECONDS:-600}"

fail() {
    printf '\nError: %s\n' "$1" >&2
    exit 1
}

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "Usage: ./push.sh vX.Y.Z"
fi

if [[ "$(git branch --show-current)" != "main" ]]; then
    fail "Release tags must be created from main."
fi

if [[ -n "$(git status --porcelain)" ]]; then
    fail "Working tree is not clean. Commit, stash, or discard changes first."
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
    fail "Remote tag $TAG already exists. Choose a new version tag."
fi

printf 'Pushing main...\n'
git push origin main

readonly RELEASE_BASE="$(git rev-parse HEAD)"
printf 'Creating and pushing %s...\n' "$TAG"
git tag -a "$TAG" -m "Release $TAG"
git push origin "refs/tags/$TAG"

printf 'Tag sent. Waiting %ss for GitHub Actions to start...\n' "$INITIAL_WAIT_SECONDS"
sleep "$INITIAL_WAIT_SECONDS"

elapsed="$INITIAL_WAIT_SECONDS"
while (( elapsed <= TIMEOUT_SECONDS )); do
    git fetch origin main "refs/tags/$TAG:refs/tags/$TAG" --force --quiet
    remote_main="$(git rev-parse origin/main)"
    remote_tag="$(git rev-parse "$TAG^{commit}")"

    if [[ "$remote_main" != "$RELEASE_BASE" && "$remote_tag" == "$remote_main" ]]; then
        git pull --ff-only origin main
        printf '\nRelease %s completed. Local main now matches the GitHub Actions version commit.\n' "$TAG"
        exit 0
    fi

    printf 'Waiting for GitHub Actions (%ss/%ss)...\n' "$elapsed" "$TIMEOUT_SECONDS"
    sleep "$POLL_SECONDS"
    elapsed=$((elapsed + POLL_SECONDS))
done

fail "Timed out waiting for the release workflow. Check GitHub Actions, then run: git fetch origin main --tags --force && git pull --ff-only origin main"
