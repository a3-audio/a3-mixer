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

The desk speaks what the one truth says: a3-core ships every OSC address,
port and IP of the system in `/usr/share/a3/a3-osc.json`. The desk reads a
copy of it beside its script, `software/scripts/a3-osc.json` (not in git —
copy it over from the Core machine whenever the package there changes), or
the file `$A3_OSC_TRUTH` names. Without it the service stops at once and
says where it looked.
