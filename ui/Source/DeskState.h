// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <optional>
#include <vector>

namespace desk
{
/** What the desk shows for each pot (indexed as allPots()): Core's value,
    or the hand's while it moves. It owns no state of its own (D5): every
    value came from Core or from a hand here and went to Core. */
class DeskState
{
public:
    explicit DeskState (int pots);

    int size() const { return static_cast<int> (_values.size()); }
    bool known (int pot) const { return _known[(size_t) pot]; }
    float value (int pot) const { return _values[(size_t) pot]; }
    bool grabbed (int pot) const { return _grabbed[(size_t) pot]; }

    /** A hand set it here: stored; the caller sends it. */
    void setFromTouch (int pot, float value);
    /** Core relayed it: shown at once, or -- while a hand holds the pot -- kept for its release. */
    void setFromPeer (int pot, float value);
    void grab (int pot);
    void release (int pot);

private:
    void take (int pot, float value);

    std::vector<float> _values;
    std::vector<bool> _known, _grabbed;
    std::vector<std::optional<float>> _held;
};
}
