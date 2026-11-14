%global claude_version 5.11492.5
# Electron bundled by upstream (usr/lib/claude-desktop/version in the .deb).
# Informational only — we no longer download Electron ourselves.
%global electron_ver   45.2.1

# The Debian package name for the arch we are building. Anthropic publishes
# amd64 and arm64 only, which is what ExclusiveArch below restricts us to.
%ifarch x86_64
%global debarch amd64
%endif
%ifarch aarch64
%global debarch arm64
%endif

# Everything we ship is a prebuilt, already-stripped upstream binary: skip
# debuginfo extraction, the strip/note brp scripts and build-id links, all of
# which would either fail or needlessly rewrite vendor binaries.
%global debug_package               %{nil}
%global __brp_strip                 %{nil}
%global __brp_strip_static_archive  %{nil}
%global __brp_strip_comment_note    %{nil}
%global __brp_mangle_shebangs       %{nil}
%global _build_id_links             none

Name:           claude-desktop
Version:        %{claude_version}
Release:        1%{?dist}
Summary:        Claude Desktop for Linux
License:        Proprietary
URL:            https://claude.com/download/

# Anthropic's official Linux build, taken from the apt repository's package
# pool. The current version for each arch is listed in
#   https://downloads.claude.ai/claude-desktop/apt/stable/dists/stable/main/binary-{amd64,arm64}/Packages
Source0:        https://downloads.claude.ai/claude-desktop/apt/stable/pool/main/c/claude-desktop/claude-desktop_%{claude_version}_%{debarch}.deb

ExclusiveArch:  x86_64 aarch64
# Vendored Electron/Chromium: let the explicit Requires below speak instead of
# generating provides for every bundled .so.
AutoReqProv:    no

BuildRequires:  binutils
BuildRequires:  tar
BuildRequires:  xz
BuildRequires:  desktop-file-utils

# Debian Depends mapped to Fedora, plus the sonames the main binary links
# against (objdump -p usr/lib/claude-desktop/claude-desktop).
Requires:       glibc >= 2.34
Requires:       gtk3
Requires:       glib2
Requires:       cairo
Requires:       pango
Requires:       atk
Requires:       at-spi2-atk
Requires:       at-spi2-core
Requires:       nss
Requires:       nspr
Requires:       alsa-lib
Requires:       cups-libs
Requires:       dbus-libs
Requires:       expat
Requires:       libdrm
Requires:       mesa-libgbm
Requires:       libsecret
Requires:       libnotify
Requires:       libuuid
Requires:       libxkbcommon
Requires:       libX11
Requires:       libxcb
Requires:       libXcomposite
Requires:       libXdamage
Requires:       libXext
Requires:       libXfixes
Requires:       libXrandr
Requires:       libXtst
# Linked by the native binding (resources/app.asar.unpacked/.../claude-native-binding.node).
Requires:       pipewire-libs
Requires:       systemd-libs
Requires:       xdg-utils
Requires:       xdg-desktop-portal
# Upstream now hard-depends on one portal backend (gtk | gnome | kde).
Requires:       (xdg-desktop-portal-gtk or xdg-desktop-portal-gnome or xdg-desktop-portal-kde)

# Debian Recommends mapped to Fedora. None of these are needed to start the
# app: appindicator for the tray, a keyring for credential storage, gvfs so
# "move to trash" works, gjs for the GNOME Shell search provider, bubblewrap,
# socat and an ssh client for Claude Code sandboxing and SSH remotes, and
# qemu + firmware for the Cowork VM (upstream ships the disk image and
# virtiofsd).
Recommends:     libayatana-appindicator-gtk3
Recommends:     gnome-keyring
Recommends:     ca-certificates
Recommends:     gvfs
Recommends:     gjs
Recommends:     bubblewrap
Recommends:     socat
Recommends:     openssh-clients
%ifarch x86_64
Recommends:     qemu-system-x86-core
Recommends:     edk2-ovmf
%endif
%ifarch aarch64
Recommends:     qemu-system-aarch64-core
Recommends:     edk2-aarch64
%endif

Provides:       bundled(electron) = %{electron_ver}
Provides:       bundled(chromium)

%description
Claude Desktop for Linux, repackaged as an RPM from Anthropic's official
Debian package.

Upstream supports Ubuntu and Debian only and publishes a .deb through its own
apt repository. This spec unpacks that .deb and reinstalls its contents under
Fedora's layout so the app can be managed with dnf. The application binaries
are shipped verbatim — nothing is patched or rebuilt.

# ---------------------------------------------------------------------------
# %prep — unpack the .deb (ar archive containing control/data tarballs)
# ---------------------------------------------------------------------------
%prep
%setup -q -c -T
ar x %{SOURCE0}
# -f auto-detects the compression, so this keeps working if upstream switches
# the data member from xz to zstd.
tar -xf data.tar.*
rm -f debian-binary control.tar.* data.tar.*

# ---------------------------------------------------------------------------
# %build — nothing to compile
# ---------------------------------------------------------------------------
%build

# ---------------------------------------------------------------------------
# %install
# ---------------------------------------------------------------------------
%install
_src=%{_builddir}/%{name}-%{version}/usr
_dest=%{buildroot}%{_libdir}/%{name}

# --- application tree -------------------------------------------------------
# The .deb installs to /usr/lib/claude-desktop; move it to %%{_libdir} since
# these are arch-specific binaries. Nothing in the app hardcodes its own
# install path (Electron resolves resources relative to the executable), so
# the relocation is safe.
mkdir -p "$_dest"
cp -a "$_src"/lib/claude-desktop/. "$_dest"/

# chrome-sandbox must stay setuid root. On kernels that restrict unprivileged
# user namespaces Chromium falls back to this helper to build its sandbox;
# without the setuid bit the app only starts with --no-sandbox.
chmod 4755 "$_dest"/chrome-sandbox

# --- launcher ---------------------------------------------------------------
# Same shape as upstream: a symlink, not a wrapper, so argv[0] resolution and
# the Wayland app_id keep working. -r makes it relative (../lib64/...), which
# is what upstream ships and what keeps the link valid inside a chroot.
mkdir -p %{buildroot}%{_bindir}
ln -sfr %{buildroot}%{_libdir}/%{name}/claude-desktop %{buildroot}%{_bindir}/%{name}

# --- desktop entry ----------------------------------------------------------
# Shipped verbatim: its StartupWMClass matches the WM_CLASS/app_id Chromium
# derives from the app's desktopName, which is what makes docks group the
# windows under this entry.
install -Dm644 "$_src"/share/applications/com.anthropic.Claude.desktop \
    %{buildroot}%{_datadir}/applications/com.anthropic.Claude.desktop
desktop-file-validate \
    %{buildroot}%{_datadir}/applications/com.anthropic.Claude.desktop

# --- icons ------------------------------------------------------------------
for size in 16 32 48 128 256; do
    install -Dm644 "$_src"/share/icons/hicolor/${size}x${size}/apps/%{name}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/%{name}.png
done

# --- GNOME Shell search provider -------------------------------------------
# Upstream's postinst copies these two registration files out of resources/
# at install time; shipping them as package files lets rpm own and remove
# them. The D-Bus service hardcodes /usr/lib/claude-desktop, so point it at
# the relocated tree (the in-tree copy stays verbatim).
_gsp="$_src"/lib/claude-desktop/resources/gnome-search-provider
install -Dm644 "$_gsp"/com.anthropic.Claude.search-provider.ini \
    %{buildroot}%{_datadir}/gnome-shell/search-providers/com.anthropic.Claude.search-provider.ini
install -Dm644 "$_gsp"/com.anthropic.Claude.SearchProvider.service \
    %{buildroot}%{_datadir}/dbus-1/services/com.anthropic.Claude.SearchProvider.service
sed -i 's|/usr/lib/claude-desktop/|%{_libdir}/%{name}/|' \
    %{buildroot}%{_datadir}/dbus-1/services/com.anthropic.Claude.SearchProvider.service
grep -q '^Exec=.*%{_libdir}/%{name}/resources/gnome-search-provider/searchProvider.js$' \
    %{buildroot}%{_datadir}/dbus-1/services/com.anthropic.Claude.SearchProvider.service

# --- MIME types -------------------------------------------------------------
# .mcpb, .dxt and .skill, which the desktop entry claims. Upstream's postinst
# copies this into the shared-mime-info database at install time; as a package
# file, Fedora's shared-mime-info file trigger rebuilds the cache for us.
install -Dm644 "$_src"/lib/claude-desktop/resources/linux-mime/com.anthropic.Claude.xml \
    %{buildroot}%{_datadir}/mime/packages/com.anthropic.Claude.xml

# ---------------------------------------------------------------------------
# Deliberately not carried over from the .deb's maintainer scripts:
#
#   * the apt repository + signing key registration — updates here come from
#     rebuilding this spec, and writing /etc/apt on a dnf system is wrong;
#   * the AppArmor "unconfined" profile, which only exists to re-allow
#     unprivileged user namespaces on Ubuntu 24.04+. Fedora does not restrict
#     them, and confinement here is SELinux's job;
#   * the /usr/bin/ccd link, which postinst creates only when the build ships
#     resources/bin/ccd. This one does not; ship it as a symlink once it does.
# ---------------------------------------------------------------------------

%files
%license usr/share/doc/claude-desktop/copyright
%{_bindir}/%{name}
%{_libdir}/%{name}
%{_datadir}/applications/com.anthropic.Claude.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png
%{_datadir}/gnome-shell/search-providers/com.anthropic.Claude.search-provider.ini
%{_datadir}/dbus-1/services/com.anthropic.Claude.SearchProvider.service
%{_datadir}/mime/packages/com.anthropic.Claude.xml

%post
update-desktop-database %{_datadir}/applications &>/dev/null || :

%postun
update-desktop-database %{_datadir}/applications &>/dev/null || :
if [ $1 -eq 0 ]; then
    touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :
    gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor &>/dev/null || :
fi

%posttrans
gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor &>/dev/null || :

%changelog
* Sat Nov 14 2026 Claude Desktop Linux Maintainers - 5.11492.5-1
- update to Claude Desktop 5.11492.5 (Electron 45.2.1, bundled upstream)
- require pipewire-libs, which the native binding now links against
- recommend bubblewrap, socat and openssh-clients, matching upstream
- ship upstream's new shared-mime-info definitions for .mcpb, .dxt and
  .skill files

* Thu Sep 24 2026 Claude Desktop Linux Maintainers - 2.7032.0-1
- update to Claude Desktop 2.7032.0 (Electron 44.4.3, bundled upstream)
- require one xdg-desktop-portal backend (gtk, gnome or kde), matching
  upstream's new hard dependency
- ship upstream's new GNOME Shell search provider registration, with the
  D-Bus service pointed at %%{_libdir}; recommend gjs to run it

* Wed Aug 12 2026 Claude Desktop Linux Maintainers - 1.28929.0-1
- repackage Anthropic's official Linux .deb instead of the Windows installer
- update to Claude Desktop 1.28929.0 (Electron 42.7.0, both bundled upstream)
- drop all app patching: the native build already handles Linux platform
  detection, window decorations, the file:// origin check and the tray
- drop the @ant/claude-native JS stub; upstream ships a real Linux binding
- drop the node-pty source build; upstream ships linux-x64/linux-arm64
  prebuilds, so Claude Code "run in terminal" works out of the box
- re-enable the system tray, which upstream now supports through
  libayatana-appindicator with dedicated Linux tray icons
- Cowork now works: ship upstream's cowork-linux-helper, VM image and
  virtiofsd, and recommend qemu plus the matching firmware
- ship upstream's desktop entry (with its New chat / New Claude Code actions)
  and PNG icons rather than reconstructing them from the Windows resources
- install chrome-sandbox setuid root as upstream does
- keep all Chromium locales; the app is localized into 11 languages now
- build needs neither network access nor Node.js: %%prep only unpacks the .deb

* Wed Jun 10 2026 Claude Desktop Linux Maintainers - 1.11847.5-1
- update to Claude Desktop 1.11847.5

* Tue Jun 09 2026 Claude Desktop Linux Maintainers - 1.11187.4-1
- update to Claude Desktop 1.11187.4
- update Electron from 40.4.1 to 41.6.1
- drop bundled claude-ssh binaries (now downloaded at runtime by the app)
- copy new ion-dist resource bundle into the app
- build node-pty for Linux so Claude Code "run in terminal" works
- disable the system tray on Linux (unreliable across desktops; app now quits on window close)

* Sat Feb 21 2026 Claude Desktop Linux Maintainers - 1.1.3918-1
- update to Claude Desktop 1.1.3918

* Fri Feb 20 2026 Claude Desktop Linux Maintainers - 1.1.3770-1
- update to Claude Desktop 1.1.3770
- claude-ssh binaries now included in Windows installer, macOS DMG no longer needed

* Sun Feb 15 2026 Claude Desktop Linux Maintainers - 1.1.3189-1
- update to Claude Desktop 1.1.3189
- update Electron from 39.5.0 to 40.4.1
- add claude-ssh binaries from macOS DMG for SSH remote feature

* Thu Feb 12 2026 Claude Desktop Linux Maintainers - 1.1.2685-1
- update to Claude Desktop 1.1.2685

* Sun Feb 08 2026 Claude Desktop Linux Maintainers - 1.1.2321-1
- update to Claude Desktop 1.1.2321
