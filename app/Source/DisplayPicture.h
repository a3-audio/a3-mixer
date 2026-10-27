// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <optional>
#include <string>
#include <vector>

/** The channel and return displays' picture, a port of display_panel.py:
    pure layout in panel pixels. The shared fixture holds the two to each other. */
namespace desk::display
{
inline constexpr int oledWidth = 128, oledHeight = 64;
inline constexpr int pairs = 8, analogInput = 8, cueCursor = 2, analogMode = 0, stemMode = 1;
inline constexpr int stemsPerDeck = 4, channelMeters = 3, engineDecks = 4, engineSlots = 5, coreDecks = 4;

struct Box
{
    int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
};

int litRows (double level, int count);

struct Heading
{
    Box box;
    std::string text;
};

struct Meter
{
    Box box;
    double level = 0.0;
    bool clip = false;
    double hold = 0.0;

    int pixels() const { return litRows (level, box.y1 - box.y0 + 1); }
    bool hatched() const { return clip && pixels() > 0; }
    std::optional<int> holdRow() const;
};

struct Toggle
{
    Box box;
    bool on = false;
    std::string text;
};

struct Picture
{
    std::vector<Heading> headings;
    std::vector<Meter> meters;
    Box cursor;
    std::vector<Box> dividers;
    std::optional<Toggle> toggle;
    Box active;
    std::vector<Box> marks;
};

/** Channel `channel`'s cursors, left to right: D1's stem n, D2's stem n, A (stem n plays only on channel n). */
std::array<int, channelMeters> channelRing (int channel);
/** The meter (0 D1, 1 D2, 2 A) under the cursor; a cursor off the ring is A. */
int channelSlot (int channel, int cursor);
/** The meter that plays: D1 if its bit is set, else D2 if its bit is set, else A (a foreign bit is A). */
int playingSlot (int channel, int mask);

/** Channel `channel` (0-3): D1's stem n, D2's stem n and the analog input, one meter each under
    D1 | D2 | A; levels, clips and holds in that order. */
Picture channelPicture (int channel, int cursor, const std::array<double, channelMeters>& levels, int mask, int width,
                        int height, const std::array<bool, channelMeters>& clips,
                        const std::array<double, channelMeters>& holds);
/** The engine ring's place (0-4, left to right 1 2 3 4 A) of Core's source 1-4 or 0 (analog). */
int engineSlot (int source);
/** A channel in engine mode: 1 2 3 4 A, analog last (Core's numbers 1-4 and 0), `source` under the
    active bracket, `cursor` under the arrow. `levels`, `clips` and `holds` are in that display order; `present`
    says per deck (1-4) whether it is there: an absent deck is a dash over an empty slot, no bar and no scale
    marks, and keeps its bracket and cursor (they are Core's). */
Picture enginePicture (int source, int cursor, const std::array<bool, engineDecks>& present,
                       const std::array<double, engineSlots>& levels, int width, int height,
                       const std::array<bool, engineSlots>& clips, const std::array<double, engineSlots>& holds);
/** STEM and ANALOG (in that order), the CUE field, the cursor over one of three. In engine mode STEM
    reads DELAY: the return's second source is the delay line. */
Picture returnPicture (int cursor, int mode, bool cue, const std::array<double, 2>& levels, int width, int height,
                       const std::array<bool, 2>& clips, const std::array<double, 2>& holds, bool engine = false);

/** Lit by a peak over full scale, held one second after the last one. */
class ClipHold
{
public:
    bool feed (float peak, double dt);

private:
    double left = 0.0;
};
}
