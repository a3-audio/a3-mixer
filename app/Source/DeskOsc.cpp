// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskOsc.h"

#include "DeskControls.h"

namespace desk
{
namespace
{
/** "/channel/{ch}/gain" as a regex with one number group, and the field's name. */
std::pair<std::string, std::string> regexOf (const std::string& pattern)
{
    static const std::string special = ".^$|()[]*+?\\";
    std::string out, field;
    for (size_t i = 0; i < pattern.size(); ++i)
    {
        if (pattern[i] == '{')
        {
            const auto end = pattern.find ('}', i);
            field = pattern.substr (i + 1, end - i - 1);
            out += "(\\d+)";
            i = end;
            continue;
        }
        if (special.find (pattern[i]) != std::string::npos)
            out += '\\';
        out += pattern[i];
    }
    return { out, field };
}

std::vector<std::string> heardKeys()
{
    std::vector<std::string> keys (channelPotKeys.begin(), channelPotKeys.end());
    keys.insert (keys.end(), masterPotKeys.begin(), masterPotKeys.end());
    for (const auto& [key, name] : lamps)
        keys.push_back (key);
    for (const auto* key : { "filter.led", "channel.stem", "channel.stem.cursor", "aux-return.stem",
                             "aux-return.stem.mode", "aux-return.cue.led", "beat" })
        keys.emplace_back (key);
    return keys;
}
}

DeskOsc::DeskOsc (a3::OscTruth truth) : _truth (std::move (truth))
{
    for (const auto& key : heardKeys())
    {
        const auto [regex, field] = regexOf (_truth.pattern (key).toStdString());
        _matchers.push_back ({ key, std::regex (regex),
                               field.empty() ? std::pair<int, int> { 0, -1 } : _truth.range (key, field) });
    }
    _vuPrefix = _truth.pattern ("vu").upToFirstOccurrenceOf ("{", false, false);
}

juce::StringArray DeskOsc::missing (const a3::OscTruth& truth)
{
    juce::StringArray lacking;
    for (const auto& key : keysUsed())
        if (! truth.hasAddress (key))
            lacking.addIfNotAlreadyThere (key);
    static const std::array<std::pair<const char*, const char*>, 4> listeners {
        { { "desk", "osc" }, { "desk", "vu" }, { "core", "osc" }, { "beat-analyzer", "clock" } } };
    for (const auto& [program, role] : listeners)
        if (! truth.listener (program, role))
            lacking.add (juce::String ("listener ") + program + "." + role);
    if (truth.host ("core").isEmpty())
        lacking.add ("host core");
    return lacking;
}

juce::String DeskOsc::address (const std::string& key, int number) const
{
    return _truth.pattern (key).replace ("{ch}", juce::String (number)).replace ("{n}", juce::String (number));
}

std::optional<Match> DeskOsc::match (const juce::String& address) const
{
    const auto text = address.toStdString();
    std::smatch found;
    for (const auto& m : _matchers)
    {
        if (! std::regex_match (text, found, m.regex))
            continue;
        if (m.range.second < m.range.first)
            return Match { m.key, 0 };
        const int number = std::stoi (found[1].str());
        if (number < m.range.first || number > m.range.second)
            return std::nullopt;
        return Match { m.key, number };
    }
    return std::nullopt;
}

std::optional<int> DeskOsc::vuNumberOf (const juce::String& address) const
{
    if (_vuPrefix.isEmpty() || ! address.startsWith (_vuPrefix))
        return std::nullopt;
    const auto rest = address.substring (_vuPrefix.length());
    if (rest.isEmpty() || ! rest.containsOnly ("0123456789"))
        return std::nullopt;
    const int n = rest.getIntValue();
    if (n < 1 || n > _truth.vuCount())
        return std::nullopt;
    return n;
}

Endpoint DeskOsc::onTheCoreMachine (const char* program, const char* role) const
{
    const auto listener = _truth.listener (program, role);
    if (! listener)
        return {};
    return { _truth.host (listener->host == "any" ? "core" : listener->host), listener->port };
}

Endpoint DeskOsc::core() const { return onTheCoreMachine ("core", "osc"); }
Endpoint DeskOsc::beatClock() const { return onTheCoreMachine ("beat-analyzer", "clock"); }
int DeskOsc::ownPort() const { return _truth.listener ("desk", "osc") ? _truth.listener ("desk", "osc")->port : -1; }
int DeskOsc::vuPort() const { return _truth.listener ("desk", "vu") ? _truth.listener ("desk", "vu")->port : -1; }
}
