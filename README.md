<p align="center"><img src="extension/icons/icon128.png" width="96" alt="VPN Disconnector icon"></p>

<h1 align="center">VPN Disconnector</h1>

<p align="center">Choose websites in Chrome that skip your VPN. Everything else stays protected.</p>

---

Some websites block VPNs, show the wrong country, or are just slower through a tunnel. **VPN Disconnector** lets you click one button on those sites to load them through your normal internet connection, while all other traffic keeps going through your VPN.

Tested with **NordVPN** (NordLynx) on macOS. It should work with most VPN apps that route traffic through a `utun` interface, such as WireGuard, OpenVPN, and IKEv2 clients.

## How it works

A VPN app tunnels *all* traffic on the machine, and a browser extension cannot get around that by itself. So the project has two parts:

```
Chrome ──► extension (PAC script)
             │
             ├─ sites on your list ──► local helper 127.0.0.1:8899 ──► Wi-Fi/Ethernet ──► internet
             │
             └─ everything else ─────────────────────────────────► VPN tunnel ──► internet
```

| Part | What it does |
|---|---|
| **`extension/`** | Chrome extension. Sends only the sites on your list to the local helper. Everything else connects normally, through the VPN. |
| **`helper/bypass_proxy.py`** | Small local HTTP/HTTPS proxy with no dependencies. It pins its sockets to your physical network interface (macOS `IP_BOUND_IF`), so its traffic skips the VPN tunnel. It also does DNS lookups through your router. |

## Requirements

- macOS
- Python 3.8 or newer (the `python3` that comes with macOS works)
- Google Chrome, or another Chromium browser: Edge, Brave, Arc, Opera

## Installation

### 1. Download

```bash
git clone https://github.com/mohammadalikashani/VPNDisconnector.git
cd VPNDisconnector
```

Or click **Code → Download ZIP** on GitHub and unzip it.

### 2. Start the helper

To start it automatically at login (recommended):

```bash
./helper/install.sh
```

Or run it in a terminal while you need it:

```bash
python3 helper/bypass_proxy.py
```

### 3. Install the extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Pin the extension to the toolbar.

> Keep the folder where it is. Chrome loads the extension from that folder, so deleting or moving it removes the extension.

## Usage

1. Open the website that should skip the VPN.
2. Click the extension icon, then **Skip VPN for this site**.
3. The page reloads through your normal connection, and the icon shows an orange **OFF** badge.

You can also add or remove domains by hand in the popup. Adding `example.com` also covers `www.example.com`, `api.example.com`, and other subdomains.

To check that it works, add `ipify.org` to the list and open <https://api.ipify.org>. It should show your real IP, not the VPN's.

## Troubleshooting

| Problem | Fix |
|---|---|
| Popup says **Helper not running** | Start it with `python3 helper/bypass_proxy.py`, or run `./helper/install.sh`. |
| Site still detects the VPN | The site loads files from other domains, such as CDNs and APIs. Open DevTools → Network to find them and add them to the list too. |
| Bypassed sites don't load at all | The VPN's **kill switch** may block all traffic outside the tunnel. Turn it off. |
| Helper picks the wrong network | Choose it yourself: `python3 helper/bypass_proxy.py --interface en0` |
| Port 8899 is already in use | Run the helper with `--port 9000` (or `PORT=9000 ./helper/install.sh`), and set the same port under **Settings** in the popup. |
| Conflicts with another proxy extension | Only one extension can control Chrome's proxy at a time. Turn off other proxy or VPN browser extensions. |

Helper logs (when installed with `install.sh`): `~/Library/Logs/vpn-disconnector.log`

## Uninstall

```bash
./helper/install.sh uninstall
```

Then remove the extension in `chrome://extensions`.

## Privacy

- Your site list is saved in Chrome's own storage, and Chrome Sync copies it if you have sync turned on.
- The helper only listens on `127.0.0.1`, so nothing outside your computer can reach it.
- No analytics, no telemetry, no outside servers.

**Note:** traffic for sites on your list does **not** go through the VPN. Your internet provider and those websites will see your real IP address for them.

## Development

- Regenerate the icons: `python3 tools/make_icons.py`
- Run the helper with debug logging: `python3 helper/bypass_proxy.py -v`
- After editing the extension, click the reload button on its card in `chrome://extensions`.

## License

[MIT](LICENSE)

*Not affiliated with or endorsed by Nord Security or NordVPN.*
