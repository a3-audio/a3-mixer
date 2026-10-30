// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <optional>
#include <string>
#include <vector>

/** The delay list on the FX Return's encoder, as the hardware has it (a3_mixer_delay.DelayList and
    display_panel.delay_text): select, the start mode with the cursor on BEAT, where a turn moves the
    cursor and stops at the ends; edit, where a turn goes to Core as the row's turn word. A press toggles
    the two; four quiet seconds in edit select again (R22). The mode and the cursor are the desk's own,
    the values Core's. One difference, the maintainer's (2026-10-30): CUE is no row here -- the desk has
    a DELAY CUE key for it. */
namespace desk::delay
{
inline constexpr int rowCount = 4;
/** R22: quiet time in edit after which the encoder is selecting again. */
inline constexpr double fallbackMs = 4000.0;

enum class Mode { select, edit };

/** BEAT, FEEDBK, COLOR, SPREAD: what the display prints. */
const char* rowName (int row);
/** "beat", "feedback", "color", "spread": the truth's word for the row. */
std::optional<int> rowOfName (const std::string& name);
std::string turnKey (int row);
std::string valueKey (int row);
std::optional<int> rowOfValueKey (const std::string& key);
std::optional<int> rowOfTurnKey (const std::string& key);
/** a3_mixer_osc.DELAY_KEYS: the four turns, then the four values. Optional: all or none. */
std::vector<std::string> delayKeys();
/** A row's value as the display reads it; "--" until Core has said one. */
std::string valueText (int row, std::optional<double> value);

class DelayList
{
public:
    /** Select: moves the cursor, nothing to send. Edit: the row the clicks go to. */
    std::optional<int> turn (int clicks, double nowMs);
    void press (double nowMs);
    /** Lets a quiet edit fall back to select. */
    void step (double nowMs);

    Mode mode() const { return _mode; }
    int cursor() const { return _cursor; }

private:
    Mode _mode = Mode::select;
    int _cursor = 0;
    double _lastTouchMs = 0.0;
};
}
