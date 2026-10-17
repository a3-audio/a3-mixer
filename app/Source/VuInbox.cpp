// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <algorithm>
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
    {
        const juce::SpinLock::ScopedLockType lock (_lock);
        std::copy (_peaks.begin(), _peaks.end(), _scratchPeaks.begin());
        std::copy (_fresh.begin(), _fresh.end(), _scratchFresh.begin());
        std::fill (_fresh.begin(), _fresh.end(), false);
    }
    std::vector<std::optional<float>> out (_scratchPeaks.size());
    for (size_t i = 0; i < out.size(); ++i)
        if (_scratchFresh[i])
            out[i] = _scratchPeaks[i];
    return out;
}
}
