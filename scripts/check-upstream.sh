#!/usr/bin/env bash
# Check Anthropic's apt repository for a Claude Desktop newer than the one the
# spec packages. If there is one, bump the spec to it and write a Markdown
# report of the upstream changes that a version bump does not carry over on
# its own: Depends/Recommends, maintainer scripts, the file layout and the
# shared libraries the binaries link against.
#
# Usage: scripts/check-upstream.sh [REPORT.md]
#
# Prints update=, current= and version=; under GitHub Actions they are also
# written to $GITHUB_OUTPUT. Needs curl, ar, tar, objdump and sha256sum.
set -euo pipefail

REPO=https://downloads.claude.ai/claude-desktop/apt/stable
SPEC=claude-desktop.spec
REPORT=${1:-upstream-report.md}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

output() {
    echo "$1=$2"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1=$2" >> "$GITHUB_OUTPUT"; fi
}

for arch in amd64 arm64; do
    curl -fsSL -o "$WORK/Packages-$arch" "$REPO/dists/stable/main/binary-$arch/Packages"
    awk '/^Version:/ {print $2}' "$WORK/Packages-$arch" | sort -u > "$WORK/versions-$arch"
done

# Only move to a version published for both arches the spec builds.
current=$(awk '/^%global claude_version/ {print $3}' "$SPEC")
latest=$(comm -12 "$WORK/versions-amd64" "$WORK/versions-arm64" | sort -V | tail -n 1)

output current "$current"
if [ -z "$latest" ] || [ "$(printf '%s\n%s\n' "$current" "$latest" | sort -V | tail -n 1)" = "$current" ]; then
    output update false
    exit 0
fi
output update true
output version "$latest"

# --- Packages index helpers --------------------------------------------------
# Print the stanza for version $2 from the $1 (arch) index.
stanza() {
    awk -v v="$2" 'BEGIN {RS = ""} index($0, "\nVersion: " v "\n") {print; exit}' "$WORK/Packages-$1"
}
# Print field $3 of that stanza, one dependency per line, sorted.
deps() {
    stanza "$1" "$2" | awk -v f="$3: " 'index($0, f) == 1 {print substr($0, length(f) + 1)}' |
        tr ',' '\n' | sed 's/^ *//; /^$/d' | sort
}

# --- download and unpack both amd64 .debs ------------------------------------
unpack() {
    local version=$1 dir=$WORK/$1 file sha
    file=$(stanza amd64 "$version" | awk '/^Filename:/ {print $2}')
    sha=$(stanza amd64 "$version" | awk '/^SHA256:/ {print $2}')
    [ -n "$file" ] || return 1
    mkdir -p "$dir/ctl" "$dir/data"
    curl -fsSL -o "$dir/pkg.deb" "$REPO/$file" || return 1
    echo "$sha  $dir/pkg.deb" | sha256sum -c --quiet || return 1
    (cd "$dir" && ar x pkg.deb && tar -xf control.tar.* -C ctl && tar -xf data.tar.* -C data)
    rm -f "$dir"/pkg.deb "$dir"/*.tar.*
}

# The file layout, minus the hashed web bundle and Chromium's locale packs,
# which churn on every release without needing any packaging change.
layout() {
    (cd "$WORK/$1/data" && find . \
        -path ./usr/lib/claude-desktop/resources/ion-dist -prune -o \
        -path ./usr/lib/claude-desktop/locales -prune -o -print | sort)
}

# Sonames any bundled ELF file links against that the bundle does not ship
# itself, i.e. the ones the RPM has to Require.
sonames() {
    local data=$WORK/$1/data
    find "$data" -path "$data/usr/lib/claude-desktop/resources/ion-dist" -prune -o -type f -print |
        while read -r f; do { objdump -p "$f" 2>/dev/null || true; } | awk '/NEEDED/ {print $2}'; done |
        sort -u | while read -r so; do
            if [ -z "$(find "$data" -name "$so" -print -quit)" ]; then echo "$so"; fi
        done
}

# Print a fenced diff block, or a note when there is nothing to show.
diff_block() {
    local out
    out=$(diff -u --label "$current" --label "$latest" "$1" "$2" | tail -n +3 | head -n 400) || true
    if [ -z "$out" ]; then
        echo "_No changes._"
    else
        printf '```diff\n%s\n```\n' "$out"
    fi
}

have_old=true
unpack "$current" || have_old=false
unpack "$latest"

electron=$(cat "$WORK/$latest/data/usr/lib/claude-desktop/version")
old_electron=$(awk '/^%global electron_ver/ {print $3}' "$SPEC")

# --- bump the spec -----------------------------------------------------------
sed -i \
    -e "s/^%global claude_version .*/%global claude_version $latest/" \
    -e "s/^\(%global electron_ver *\).*/\1$electron/" \
    -e "s/^\(Release: *\)[0-9]*%/\11%/" \
    "$SPEC"
entry="* $(LC_ALL=C date -u '+%a %b %d %Y') Claude Desktop Linux Maintainers - $latest-1
- update to Claude Desktop $latest (Electron $electron, bundled upstream)
"
awk -v entry="$entry" '{print} /^%changelog$/ {print entry}' "$SPEC" > "$WORK/spec" && cat "$WORK/spec" > "$SPEC"

# --- report ------------------------------------------------------------------
{
    echo "Upstream published Claude Desktop **$latest** (spec had $current)."
    echo
    echo "- Electron: $old_electron → $electron"
    echo "- Index: $REPO/dists/stable/main/binary-{amd64,arm64}/Packages"
    echo
    echo "This PR only bumps the version and adds a changelog entry. Check the"
    echo "sections below for anything the spec has to follow, and push those"
    echo "changes to this branch before merging."

    for field in Depends Recommends; do
        for arch in amd64 arm64; do
            deps "$arch" "$current" "$field" > "$WORK/old-$field-$arch"
            deps "$arch" "$latest" "$field" > "$WORK/new-$field-$arch"
            echo
            echo "## $field ($arch)"
            echo
            diff_block "$WORK/old-$field-$arch" "$WORK/new-$field-$arch"
        done
    done

    if $have_old; then
        sonames "$current" > "$WORK/old-sonames"
        sonames "$latest" > "$WORK/new-sonames"
        echo
        echo "## Linked system libraries (amd64)"
        echo
        echo "Sonames the bundled binaries need from the system. A new one usually"
        echo "means a new \`Requires\`."
        echo
        diff_block "$WORK/old-sonames" "$WORK/new-sonames"

        layout "$current" > "$WORK/old-layout"
        layout "$latest" > "$WORK/new-layout"
        echo
        echo "## File layout (amd64, excluding ion-dist and locales)"
        echo
        diff_block "$WORK/old-layout" "$WORK/new-layout"

        echo
        echo "## Maintainer scripts"
        for s in preinst postinst prerm postrm; do
            old=$WORK/$current/ctl/$s new=$WORK/$latest/ctl/$s
            [ -e "$old" ] || [ -e "$new" ] || continue
            [ -e "$old" ] || old=/dev/null
            [ -e "$new" ] || new=/dev/null
            echo
            echo "<details><summary>$s</summary>"
            echo
            diff_block "$old" "$new"
            echo
            echo "</details>"
        done
    else
        echo
        echo "> $current is no longer in the upstream pool, so the file layout,"
        echo "> library and maintainer script comparisons were skipped."
    fi
} > "$REPORT"
