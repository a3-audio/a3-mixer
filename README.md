# A3-Mixer Controller

**An open-source mixer controller for the [A3-Audio](https://a3-audio.github.io/) project.**

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