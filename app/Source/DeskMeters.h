// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include "DeskOsc.h"
#include "shared/MeterBallistics.h"
namespace desk
{
/** Every meter on the desk, by the truth's names (as a3_mixer_osc finds them):
    the channel LEDs (in<ch>_pre_L/R, louder side), the output matrix
    (main_sub, main_top1-7), the displays' stems, analog inputs and return. */
class DeskMeters
{
public:
    struct Reading
    {
        float bar = 0.f, hold = 0.f;   // linear, as on the wire
    };

    DeskMeters (const DeskOsc& osc, a3::MeterBallisticsParameters parameters);
    void take (const std::vector<std::optional<float>>& peaks, std::int64_t nowMs);

    Reading channelInput (int channel, std::int64_t nowMs) const;   // 1-4
    Reading output (int column, std::int64_t nowMs) const;          // 0 = SUB, 1-7 = tops
    Reading stem (int pair, std::int64_t nowMs) const;              // 0-7 = stem_a1 ... stem_b4
    Reading analog (int channel, std::int64_t nowMs) const;         // 1-4
    Reading returnStem (std::int64_t nowMs) const;
    Reading returnAnalog (std::int64_t nowMs) const;
    /** The loudest raw peak of the last take, for the clip hatch; 0 when none came. */
    float takenPeak (const std::string& name) const;

private:
    Reading one (const std::string& name, std::int64_t nowMs) const;
    Reading louder (const std::string& left, const std::string& right, std::int64_t nowMs) const;

    std::vector<std::string> _names;   // /vu/<n> -> name, index n - 1
    std::map<std::string, a3::MeterBallistics> _meters;
    std::map<std::string, float> _taken;
};
}
