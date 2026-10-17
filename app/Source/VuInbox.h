// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once
#include <optional>
#include <vector>
#include <juce_core/juce_core.h>
namespace desk
{
/** The meters as they arrive (~50 bundles a second on desk.vu, on the
    receiver's own thread), kept to one value per meter per frame: the loudest
    since the last take. The display thread never sees the flood (a3-mixer#6). */
class VuInbox
{
public:
    explicit VuInbox (int meters) : _peaks ((size_t) meters, 0.f), _fresh ((size_t) meters, false) {}
    void note (int number, float peak);
    std::vector<std::optional<float>> take();

private:
    juce::SpinLock _lock;
    std::vector<float> _peaks;
    std::vector<bool> _fresh;
};
}
