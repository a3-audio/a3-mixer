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

/** The eight stems under D1 | D2 and the analog input under A; levels, clips
    and holds in that order. `mask` = what plays (lowest bit), 0 = A. */
Picture channelPicture (int cursor, const std::array<double, 9>& levels, int mask, int width, int height,
                        const std::array<bool, 9>& clips, const std::array<double, 9>& holds);
/** STEM and ANALOG (in that order), the CUE field, the cursor over one of three. */
Picture returnPicture (int cursor, int mode, bool cue, const std::array<double, 2>& levels, int width, int height,
                       const std::array<bool, 2>& clips, const std::array<double, 2>& holds);

/** Lit by a peak over full scale, held one second after the last one. */
class ClipHold
{
public:
    bool feed (float peak, double dt);

private:
    double left = 0.0;
};
}
