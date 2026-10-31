// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskMeters.h"
#include <algorithm>
namespace desk
{
namespace
{
std::vector<std::string> shownNames()
{
    std::vector<std::string> names { "main_sub", "aux_L", "aux_R" };
    for (int top = 1; top <= 7; ++top)
        names.push_back ("main_top" + std::to_string (top));
    for (int ch = 1; ch <= 4; ++ch)
        for (const auto* side : { "_L", "_R" })
        {
            names.push_back ("in" + std::to_string (ch) + "_pre" + side);
            names.push_back ("analog" + std::to_string (ch) + side);
        }
    for (const auto* deck : { "a", "b" })
        for (int stem = 1; stem <= 4; ++stem)
            names.push_back (std::string ("stem_") + deck + std::to_string (stem));
    for (const auto* deck : { "deck_a", "deck_b", "deck_c", "deck_d" })
        names.push_back (deck);
    return names;
}
}

DeskMeters::DeskMeters (const DeskOsc& osc, a3::MeterBallisticsParameters parameters)
    : _names ((size_t) osc.truth().vuCount())
{
    for (const auto& name : shownNames())
        if (const auto n = osc.vuNumber (name.c_str()); n > 0)
        {
            _names[(size_t) n - 1] = name;
            _meters.emplace (name, a3::MeterBallistics (parameters));
        }
}

void DeskMeters::take (const std::vector<std::optional<float>>& peaks, std::int64_t nowMs)
{
    _taken.clear();
    for (size_t i = 0; i < peaks.size() && i < _names.size(); ++i)
    {
        if (! peaks[i] || _names[i].empty())
            continue;
        _meters.at (_names[i]).note (*peaks[i], nowMs);
        _taken[_names[i]] = *peaks[i];
    }
}

DeskMeters::Reading DeskMeters::one (const std::string& name, std::int64_t nowMs) const
{
    const auto found = _meters.find (name);
    if (found == _meters.end())
        return {};
    return { found->second.bar (nowMs), found->second.hold (nowMs) };
}

DeskMeters::Reading DeskMeters::louder (const std::string& left, const std::string& right, std::int64_t nowMs) const
{
    const auto l = one (left, nowMs), r = one (right, nowMs);
    return { std::max (l.bar, r.bar), std::max (l.hold, r.hold) };
}

DeskMeters::Reading DeskMeters::channelInput (int ch, std::int64_t now) const
{
    const auto base = "in" + std::to_string (ch) + "_pre";
    return louder (base + "_L", base + "_R", now);
}

DeskMeters::Reading DeskMeters::output (int column, std::int64_t now) const
{
    return one (column == 0 ? std::string ("main_sub") : "main_top" + std::to_string (column), now);
}

std::string DeskMeters::stemName (int pair)
{
    return std::string ("stem_") + (pair < 4 ? "a" : "b") + std::to_string (pair % 4 + 1);
}

std::string DeskMeters::analogName (int ch) { return "analog" + std::to_string (ch); }

std::string DeskMeters::deckName (int deck)
{
    return deck >= 0 && deck < 4 ? std::string ("deck_") + (char) ('a' + deck) : std::string();
}

DeskMeters::Reading DeskMeters::deck (int d, std::int64_t now) const { return one (deckName (d), now); }

DeskMeters::Reading DeskMeters::stem (int pair, std::int64_t now) const { return one (stemName (pair), now); }

DeskMeters::Reading DeskMeters::analog (int ch, std::int64_t now) const
{
    return louder (analogName (ch) + "_L", analogName (ch) + "_R", now);
}

DeskMeters::Reading DeskMeters::fxReturn (std::int64_t now) const { return louder ("aux_L", "aux_R", now); }

float DeskMeters::takenPeak (const std::string& name) const
{
    const auto found = _taken.find (name);
    return found != _taken.end() ? found->second : 0.f;
}

float DeskMeters::louderTaken (const std::string& left, const std::string& right) const
{
    return std::max (takenPeak (left), takenPeak (right));
}

float DeskMeters::stemPeak (int pair) const { return takenPeak (stemName (pair)); }
float DeskMeters::analogPeak (int ch) const { return louderTaken (analogName (ch) + "_L", analogName (ch) + "_R"); }
float DeskMeters::deckPeak (int d) const { return takenPeak (deckName (d)); }
float DeskMeters::fxReturnPeak() const { return louderTaken ("aux_L", "aux_R"); }
}
