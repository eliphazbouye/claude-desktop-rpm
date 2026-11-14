# Claude Desktop - rpm for Fedora Linux (amd64, arm64) & Asahi Fedora Linux (arm64)

An RPM spec file that, if you build it, repackages Anthropic's **official Claude
Desktop Linux build** so that you can install and run Claude Desktop natively on
Fedora Linux.

Anthropic ships Claude Desktop for Linux as a `.deb` through its own apt
repository, and supports Ubuntu 22.04+ and Debian 12+ only —
[Fedora and RHEL are explicitly not supported](https://code.claude.com/docs/en/desktop-linux).
This spec unpacks that `.deb` and reinstalls its contents under Fedora's layout
so the app can be managed with `dnf`. The application binaries are shipped
verbatim: nothing is patched, stubbed or rebuilt.

Status: Claude Code, MCPs, SSH, Preview, "Run in Terminal", Cowork and the
system tray all come from upstream's own Linux build. Computer Use and
dictation are not in the Linux beta yet; the Quick Entry global hotkey works on
X11 and needs your desktop's GlobalShortcuts portal on native Wayland.

I aim to update this repo at least once per month for new Claude Desktop versions.

## Build requirements

prereqs for building:

```
sudo dnf install rpm-build rpmdevtools desktop-file-utils
```

build the RPM:
```
spectool -g -R claude-desktop.spec
rpmbuild -bb claude-desktop.spec
```
The resulting RPM will be in `~/rpmbuild/RPMS/$ARCH/` and can get installed with:

```
ARCH=$(uname -m)
sudo dnf install ~/rpmbuild/RPMS/$ARCH/claude-desktop-*.rpm
```

## Alternative: Use `mock`

The `mock` tool provides a sandbox that allows building rpms in a clean chroot
without polluting the host. It also allows to target different distro versions.

prereqs for building:

```
sudo dnf install mock rpmdevtools
```
build the RPM:

```
spectool -g -R claude-desktop.spec

mock --spec claude-desktop.spec --sources "$(rpm --eval '%{_sourcedir}')"
```

No `--enable-network` is needed: `%prep` only unpacks the downloaded `.deb`.

The resulting RPM will be in `/var/lib/mock/<os>-<os-version>-<arch>/result/` and can get installed with:

```
sudo dnf install "$(mock -p)/../result/claude-desktop-$(rpmspec -q --qf '%{VERSION}-%{RELEASE}' claude-desktop.spec).$(uname -m).rpm"
```

And optionally cleanup after building:

```
rpmbuild --rmsource claude-desktop.spec
mock --clean
```

## Bumping to a new version

Upstream's current version per architecture is listed in the apt repository
index:

```
curl -s "https://downloads.claude.ai/claude-desktop/apt/stable/dists/stable/main/binary-$( [ "$(uname -m)" = x86_64 ] && echo amd64 || echo arm64 )/Packages" \
  | grep '^Version:' | sort -V | tail -1
```

Set `%global claude_version` in the spec to that value, add a `%changelog`
entry, and rebuild. If upstream also bumps Electron, the new version is in
`usr/lib/claude-desktop/version` inside the `.deb` — it is recorded in the spec
as `%global electron_ver` for the `bundled(electron)` provides.

`scripts/check-upstream.sh` does all of that, and also writes a report of what
changed upstream that the spec may need to follow: Depends/Recommends, the
system libraries the binaries link against, the file layout and the
maintainer scripts. The `Upstream update` GitHub workflow runs it daily; when
there is a new version it opens a PR with the bump and the report, then
test-builds and installs the RPM in Fedora on x86_64 and aarch64 and comments
the result on the PR.

## Differences from the upstream `.deb`

The application tree is installed bit-for-bit as upstream ships it, relocated
from `/usr/lib/claude-desktop` to `%{_libdir}/claude-desktop` (nothing in the
app hardcodes its own path). Two things in the `.deb`'s maintainer scripts are
deliberately **not** carried over:

* **apt repository registration.** The `.deb` writes Anthropic's signing key and
  an `/etc/apt/sources.list.d` entry so it can update itself through `apt`.
  That is meaningless on a dnf system; updates here come from rebuilding this
  spec.
* **The AppArmor profile.** It exists only to re-allow unprivileged user
  namespaces on Ubuntu 24.04+, which restricts them by default. Fedora does
  not, and confinement here is SELinux's job. `chrome-sandbox` is still
  installed setuid root, as upstream does.

## Disclaimer

This is an educational project. Use at your own risk. The closed-source Claude
Desktop binaries are not part of this repo and if you want to use them be aware
of the terms and licenses that apply.
