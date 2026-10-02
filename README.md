# A³ Mixer

**An open-source mixer controller for the [A³ Audio](https://a3-audio.github.io/) project.**

**Runs on a Raspberry Pi 3B+ or newer**, which carries the OSC control scripts
in `software/scripts/`; the panel's own I/O is handled by a microcontroller on
the mainboard (`hardware/`). Moving that split onto a Raspberry Pi Pico board
is a goal below, not the current state.

After extensive experimentation and usability testing, we've decided to rebuild the controller from the ground up to better meet requirements.

---

## 📌 **Project Goals**
- **Hardware Upgrade**:
  - Replacing Raspberry Pi + Teensy with a **Raspberry Pi Pico Dev Board** (planned: **WIZnet W5500-EVB-Pico** or **W5500-EVB-Pico2**).
  - **USB-C port** for modern connectivity.
  - **Stereo Jack**:
    - 6.3mm front jack → 3.5mm adapter for headphones.
- **Mechanics**:
  - **45mm faders** for precise channel control.

---

## 🚀 **Current Progress**
- **PCB Design**:
  - New board layout in **KiCad** (project: [`hardware/mainboard/pcb/`](hardware/mainboard/pcb/)).
## Where this fits

A³ is seven repositories and one system. **The structure, the workflow and the
versioning are described once, in the umbrella:**
[a3-audio/a3-system](https://github.com/a3-audio/a3-system#repositories-and-versioning).

The short of it: work happens on `main`, a version is an annotated tag, and
the same tag name is set in every repository at once — `v03.0` is the first.

## Addresses and ports

The desk speaks what the one truth says, and it gets the truth from Core:
Core announces every 2 s by UDP broadcast on port 7790 (`/core/here`) where
the truth is and what its fingerprint is. The desk keeps the last truth it
fetched in `~/.cache/a3/a3-osc.json` (root's home: the service runs as
root). When Core announces another fingerprint, the desk fetches the truth
from `http://<core>:9080/api/truth`, checks it, stores it and restarts. No
copying by hand.

At start the desk reads `$A3_OSC_TRUTH` if set, else that cache, else the
old copy beside the script (`software/scripts/a3-osc.json`, kept as a
fallback for one release). Without any, or with a word missing from it, it
waits for Core's announcement instead of stopping.
