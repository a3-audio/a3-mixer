# A³ Mixer

The 4-channel DJ mixer of [A³ Audio](https://github.com/a3-audio/a3-system). It
sends its faders, knobs and buttons to A³ Core over OSC and shows the meters
and lamps that come back. This repository holds the control scripts
(`software/scripts/`), the panel firmware (`hardware/mainboard/firmware/`) and
the KiCad hardware (`hardware/`).

**Documentation: https://a3-audio.github.io/a3-doc/**

- [Using A³ Mixer](https://a3-audio.github.io/a3-doc/user/a3mix.html)
- [Configuration](https://a3-audio.github.io/a3-doc/configuration/mic.html):
  V02 (shipping) and V03 (in development) hardware
- [Development](https://a3-audio.github.io/a3-doc/development/mic.html):
  `a3-mixer.py`, how the desk
  [gets its addresses from Core](https://a3-audio.github.io/a3-doc/development/mic.html#mic-truth),
  the panel firmware

## Run and test

The desk (V02: a Raspberry Pi with RaspbianOS) runs
`software/scripts/a3-mixer.py` as the systemd unit `a3-mixer.service` from
`platform-config/raspianos/`. The unit expects this repository at
`/home/aaa/a3-mixer` and a Python venv at `/home/aaa/.venv` with
`software/scripts/requirements.txt` installed.

The tests check the desk against the real OSC truth, `a3-osc.json` from an
[a3-core](https://github.com/a3-audio/a3-core) checkout beside this one (or
`/usr/share/a3/a3-osc.json` on a Core). Point `A3_OSC_TRUTH` at it:

```sh
A3_OSC_TRUTH=../a3-core/platform-config/debian-x86_64/a3-core/usr/share/a3/a3-osc.json \
  python3 -m unittest discover -s software/tests
```

The panel firmware is a PlatformIO project: `pio run` in
`hardware/mainboard/firmware/`.

## License

REUSE-compliant: the license of each path is in `.reuse/dep5`, the texts are in
`LICENSES/` (GPL-3.0-or-later for software, CERN-OHL-S-2.0 for hardware,
CC-BY-SA-4.0 and CC0-1.0 for docs and config).
