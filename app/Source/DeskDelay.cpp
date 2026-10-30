// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskDelay.h"

#include <algorithm>
#include <cmath>
#include <sstream>

namespace desk::delay
{
namespace
{
struct RowWords
{
    const char* word;
    const char* name;
};
constexpr std::array<RowWords, rowCount> rows { { { "beat", "BEAT" },
                                                  { "feedback", "FEEDBK" },
                                                  { "color", "COLOR" },
                                                  { "spread", "SPREAD" } } };

bool isRow (int row) { return row >= 0 && row < rowCount; }

int pyRound (double x) { return static_cast<int> (std::nearbyint (x)); }   // half to even, as Python's round()

/** Python's f"{value:g}". */
std::string general (double value)
{
    std::ostringstream out;
    out << value;
    return out.str();
}

std::string beatText (double value)
{
    // The fractions a deck's loop control shows; anything else as Python prints it.
    constexpr std::array<std::pair<double, const char*>, 4> fractions { { { 0.125, "1/8" },
                                                                          { 0.25, "1/4" },
                                                                          { 0.5, "1/2" },
                                                                          { 0.75, "3/4" } } };
    for (const auto& [beats, text] : fractions)
        if (std::abs (value - beats) < 1e-9)   // Core announces these exactly: binary fractions
            return text;
    return general (value);
}

std::string colorText (double value)
{
    // Filter steps from the centre: HP left of it, LP right -- the knob's own direction.
    const int step = pyRound (value * 10.0);
    if (step == 0)
        return "0";
    return step < 0 ? "HP " + std::to_string (-step) : "LP " + std::to_string (step);
}
}

const char* rowName (int row) { return isRow (row) ? rows[(size_t) row].name : ""; }

std::optional<int> rowOfName (const std::string& name)
{
    for (int row = 0; row < rowCount; ++row)
        if (name == rows[(size_t) row].word)
            return row;
    return std::nullopt;
}

std::string valueKey (int row) { return isRow (row) ? std::string ("aux-return.delay.") + rows[(size_t) row].word : std::string(); }

std::string turnKey (int row) { return isRow (row) ? valueKey (row) + ".turn" : std::string(); }

std::optional<int> rowOfValueKey (const std::string& key)
{
    for (int row = 0; row < rowCount; ++row)
        if (key == valueKey (row))
            return row;
    return std::nullopt;
}

std::optional<int> rowOfTurnKey (const std::string& key)
{
    for (int row = 0; row < rowCount; ++row)
        if (key == turnKey (row))
            return row;
    return std::nullopt;
}

std::vector<std::string> delayKeys()
{
    std::vector<std::string> keys;
    for (int row = 0; row < rowCount; ++row)
        keys.push_back (turnKey (row));
    for (int row = 0; row < rowCount; ++row)
        keys.push_back (valueKey (row));
    return keys;
}

std::string valueText (int row, std::optional<double> value)
{
    if (! value || ! std::isfinite (*value) || ! isRow (row))
        return "--";
    switch (row)
    {
        case 0: return beatText (*value);
        case 1: return std::to_string (pyRound (*value * 100.0)) + "%";
        case 2: return colorText (*value);
        default: return std::to_string (pyRound (*value)) + "\xc2\xb0";
    }
}

std::optional<int> DelayList::turn (int clicks, double nowMs)
{
    if (clicks == 0)
        return std::nullopt;
    if (_mode == Mode::select)
    {
        _cursor = std::clamp (_cursor + clicks, 0, rowCount - 1);
        return std::nullopt;
    }
    _lastTouchMs = nowMs;
    return _cursor;
}

void DelayList::press (double nowMs)
{
    _mode = _mode == Mode::select ? Mode::edit : Mode::select;
    _lastTouchMs = nowMs;
}

void DelayList::step (double nowMs)
{
    if (_mode == Mode::edit && nowMs - _lastTouchMs >= fallbackMs)
        _mode = Mode::select;
}
}
