# Polymarket Bot — STATUS.md
_Ažuriraj ovaj fajl nakon svake sesije i uploadaj zajedno s Word specom na početku novog chata._

---

## Zadnje ažuriranje: 30.03.2026.

---

## Infrastruktura

| Stavka | Vrijednost |
|--------|-----------|
| VPS IP | 204.168.167.229 |
| SSH | `ssh root@204.168.167.229` |
| Putanja na VPS-u | `/root/polymarket-bot` |
| Python venv | `/root/polymarket-bot/venv` |
| Servis | `systemd` — `polymarket-bot.service` |
| Lokalni projekt | `C:\ClaudeProjects\polymarket-bot` |
| GitHub | https://github.com/juraantonio-prog/polymarket-bot |
| Branch | `master` (ne main!) |
| Claude Code | radi lokalno na laptopu, ne na VPS-u |
| CLI komanda | `python /root/polymarket-bot/cli/main.py <cmd>` |

---

## Trenutni status

| | Stavka |
|-|--------|
| ✅ | Bot radi 24/7 na VPS-u |
| ✅ | systemd servis aktivan i enabled |
| ✅ | Telegram daily report stiže |
| ✅ | Discovery: 85 tržišta, 174 assets |
| ✅ | WebSocket prima live price updateove |
| ✅ | move_pp nenulte vrijednosti potvrđene |
| ✅ | Signal detection logika radi ispravno |
| ✅ | **30 dana paper trading sat kreće od 29.03.2026.** |
| ⏳ | Čekamo spike event (8pp+ pomak) za prvi signal |
| ❌ | Sports tržišta prolaze filter (NBA, FIFA) |
| ❌ | TP/SL bug za niske cijene |

---

## Faza projekta

**Faza 1 — Paper trading** (aktivna od 29.03.2026.)

- Paper bankroll: $10,000
- Nominalni iznos po tradu: $100
- Max otvorenih pozicija: 4
- Live trading: **ONEMOGUĆEN**
- **Cilj: 50+ tradova do ~29.04.2026.**

---

## Povijest fixeva

### Fix 1 — 26.03. ✅
`config/markets.yaml` nije postojao → kreiran, `min_volume_usd` spušten na $500k.

### Fix 2 — 26.03. ✅
Untagged tržišta prolaze category filter.
Rezultat: `filtered: 85, Tracking 85 markets`

### Fix 3 — 29.03. ✅
WS subscription `"market"` → `"Market"` — server prihvaćao ali nije slao podatke.

### Fix 4 — 29.03. ✅
`ws.raw_message` DEBUG → INFO + `print()`. Live price updateovi potvrđeni.

### Fix 5 — 30.03. ✅
**Deque overflow** → `baseline_window` uvijek prazna → `move_pp = 0.0` uvijek.
Fix: downsampling na 1 tick/10s, deque sada pokriva 1h podataka.

### Fix 6 — 30.03. ✅
**Volume filter bug** — `current_volume_usd` (per-tick $1-50) uspoređivan s `min_vol_usd: 5000`.
Fix: koristi `snapshot.rolling_volume`. `min_volume_usd` spušten na 100.

### Fix 7 — 30.03. ✅
**Spike threshold** spušten: 12pp → 8pp za paper trading fazu.
Logging dodan: svaki odbijeni signal logga reason, move_pp, gap_to_threshold_pp.

---

## Poznati bugovi (sljedeći fix)

1. **Sports tržišta prolaze filter** — NBA Finals, FIFA World Cup nemaju tagove
   - Fix: keyword filter na name/slug (nba, nfl, fifa, world-cup, nhl, mlb, mma, ufc)

2. **TP/SL bug za niske cijene** — TP ispod entry za tržišta s entry < 0.10
   - Fix: logika u `spike_fade.py`

---

## Deploy workflow

```bash
# Lokalno (laptop):
cd C:\ClaudeProjects\polymarket-bot
claude
git add -A && git commit -m "opis" && git push origin master

# Na VPS-u (SSH):
cd /root/polymarket-bot
git pull
systemctl restart polymarket-bot
```

---

## Dijagnostičke komande (VPS)

```bash
# Signal debug (što blokira signale):
journalctl -u polymarket-bot --since "5 min ago" --no-pager | grep spike_fade.no_signal | tail -20

# Live logovi:
journalctl -u polymarket-bot -f | grep -E "signal|spike|trade|subscribed"

# DB provjera:
sqlite3 /root/polymarket-bot/data/polymarket_bot.db "SELECT COUNT(*) FROM signals; SELECT COUNT(*) FROM trades;"
```

---

## Sljedeći koraci

- [ ] Fix sports keyword filter (NBA, FIFA prolaze)
- [ ] Fix TP/SL logika za niske cijene
- [ ] Pratiti prve signale na Telegramu
- [ ] Nakon 30 dana → Kelly Criterion, Bayesian scoring (@LunarResearcher)
- [ ] Faza 2: Random Forest model (@noisyb0y1)

---

## Kriterij za live micro-pilot

- [ ] Min. 50 paper tradova s pozitivnom expectancy (EV > 0)
- [ ] Win rate > 52%
- [ ] Max drawdown < 15% paper bankrolla
- [ ] Bot radi bez nadzora min. 14 dana bez kritičnih grešaka
- [ ] Telegram alertovi stižu pouzdano
- [ ] Dedicated Polygon wallet kreiran i testiran
