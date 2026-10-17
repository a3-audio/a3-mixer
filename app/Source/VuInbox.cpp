// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cmath>

#include "VuInbox.h"
namespace desk
{
void VuInbox::note (int number, float peak)
{
    if (number < 1 || number > (int) _peaks.size() || ! std::isfinite (peak))
        return;
    const juce::SpinLock::ScopedLockType lock (_lock);
    const auto i = (size_t) number - 1;
    if (! _fresh[i] || peak > _peaks[i])
        _peaks[i] = peak;
    _fresh[i] = true;
}

std::vector<std::optional<float>> VuInbox::take()
{
    const juce::SpinLock::ScopedLockType lock (_lock);
    std::vector<std::optional<float>> out (_peaks.size());
    for (size_t i = 0; i < _peaks.size(); ++i)
        if (_fresh[i])
        {
            out[i] = _peaks[i];
            _fresh[i] = false;
        }
    return out;
}
}
