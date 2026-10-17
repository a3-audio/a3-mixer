// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <string>
#include <utility>
#include <vector>

#include <juce_core/juce_core.h>

/** What the hardware desk has, as the truth's keys (never addresses): the
    tables of a3_mixer_osc.py, held to it by the shared fixture. */
namespace desk
{
inline constexpr int numChannels = 4;
/** The strip's pots by the firmware's index: SEND, TRIM, HIGH, MID, LOW, and 5 the fader. */
inline const std::array<std::string, 6> channelPotKeys { "channel.aux-send", "channel.gain", "channel.eq.high",
                                                         "channel.eq.mid", "channel.eq.low", "channel.volume" };
inline constexpr int faderSlot = 5;
/** The master section's pots by the firmware's index. */
inline const std::array<std::string, 7> masterPotKeys { "master.volume", "filter.resonance", "filter.frequency",
                                                        "master.booth", "master.phones-mix", "master.phones-volume",
                                                        "master.aux-return" };
inline const std::array<std::pair<std::string, std::string>, 2> channelKeys { { { "fx", "channel.filter" },
                                                                                { "cue", "channel.cue" } } };
inline const std::array<std::pair<std::string, std::string>, 2> lamps { { { "channel.cue.led", "cue" },
                                                                          { "channel.filter.led", "fx" } } };

struct Pot
{
    std::string key;
    int channel = 0;   // 1-4, 0 for the master section
};

/** The 24 channel pots channel by channel, then the 7 master pots. A pot's
    index here is its id in DeskState, the layout and the wire. */
const std::vector<Pot>& allPots();
int potIndex (const std::string& key, int channel);
juce::String potCaption (const std::string& key);
/** MASTER, BOOTH, PHONES: what a lock on a second operator's window holds (spec Q8). */
bool isGuarded (const std::string& key);
/** The EQ bands and the phones' blend read as a distance from their middle. */
bool fillsFromTheMiddle (const std::string& key);
/** Every key the desk sends or reads -- a3_mixer_osc.KEYS_USED. */
std::vector<std::string> keysUsed();
}
