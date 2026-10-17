// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DisplayPicture.h"

#include <algorithm>
#include <cmath>

namespace desk::display
{
namespace
{
constexpr int innerGap = 2, groupGap = 7, edge = 1, lastSlotMeters = 2;
constexpr int arrowRows = 5, arrowWidth = 2 * arrowRows, bracketRows = 4;
constexpr double markOfMeter = 0.1, returnHeadingOfWidth = 0.34, returnMeterOfHeading = 0.5;
constexpr std::array<double, 2> markedFractions { 4.0 / 8.0, 6.0 / 8.0 };   // first yellow, first red LED
constexpr int channelMarkLength = innerGap - 1;

struct Span
{
    int x0, x1;
};
struct Rows
{
    int top, bottom;
};

int pyRound (double x) { return static_cast<int> (std::nearbyint (x)); }   // half to even, as Python's round()
int floorDiv (int a, int b) { return static_cast<int> (std::floor (static_cast<double> (a) / b)); }

// CHANNEL_GROUPS = (D1, 0..3), (D2, 4..7), (A, 8..8)
struct Group
{
    const char* name;
    int first, last;
};
constexpr std::array<Group, 3> channelGroups { { { "D1", 0, 3 }, { "D2", 4, 7 }, { "A", analogInput, analogInput } } };

std::vector<Span> channelColumns (int width)
{
    const int groups = static_cast<int> (channelGroups.size()) - 1;
    const int gaps = edge + groups * (groupGap - innerGap) + pairs * innerGap;
    const int meter = floorDiv (width - gaps, pairs + lastSlotMeters);
    std::vector<Span> columns;
    int x = edge;
    for (int index = 0; index < pairs; ++index)
    {
        if (index > 0)
            x += index == channelGroups[1].first ? groupGap : innerGap;
        columns.push_back ({ x, x + meter - 1 });
        x += meter;
    }
    columns.push_back ({ x + groupGap, width - 1 });
    return columns;
}

std::array<Rows, 3> bands (int height)
{
    const int heading = std::max (6, pyRound (height * 0.19));
    const int arrow = heading + 1;
    const int meters = arrow + arrowRows + 1;
    return { { { 0, heading - 1 }, { arrow, meters - 2 }, { meters, height - 1 } } };
}

Box arrowBox (Span slot, Rows rows)
{
    const int x0 = floorDiv (slot.x0 + slot.x1 + 1 - arrowWidth, 2);
    return { x0, rows.top, x0 + arrowWidth - 1, rows.bottom };
}

Box bracket (const Box& m) { return { m.x0 - 1, m.y0 - 1, m.x1 + 1, m.y0 + bracketRows - 2 }; }

std::optional<int> playingStem (int mask)
{
    if (mask == 0)
        return std::nullopt;
    int bit = 0;
    while ((mask & (1 << bit)) == 0)
        ++bit;
    return bit;
}

Box divider (Span left, Span right, Rows rows)
{
    const int x = floorDiv (left.x1 + right.x0, 2);
    return { x, rows.top, x, rows.bottom };
}

Span centred (Span slot, int width)
{
    const int x0 = slot.x0 + floorDiv (slot.x1 - slot.x0 + 1 - width, 2);
    return { x0, x0 + width - 1 };
}

int markLength (const Box& b) { return std::max (1, pyRound ((b.x1 - b.x0 + 1) * markOfMeter)); }

void addMarks (std::vector<Box>& out, const std::vector<Meter>& meters, std::optional<int> longest)
{
    for (const auto& meter : meters)
    {
        const auto& b = meter.box;
        const int length = longest ? std::min (markLength (b), *longest) : markLength (b);
        const int rows = b.y1 - b.y0 + 1;
        for (const auto fraction : markedFractions)
        {
            const int y = b.y1 - litRows (fraction, rows);
            out.push_back ({ b.x0 - length, y, b.x0 - 1, y });
        }
    }
}

template <size_t N>
std::vector<Meter> metersFor (const std::vector<Box>& boxes, const std::array<double, N>& levels,
                              const std::array<bool, N>& clips, const std::array<double, N>& holds)
{
    std::vector<Meter> meters;
    for (size_t i = 0; i < N; ++i)
        meters.push_back ({ boxes[i], levels[i], clips[i], holds[i] });
    return meters;
}
}

int litRows (double level, int count) { return static_cast<int> (std::floor (level * count + 0.5)); }

std::optional<int> Meter::holdRow() const
{
    const int rows = litRows (hold, box.y1 - box.y0 + 1);
    if (rows <= pixels())
        return std::nullopt;
    return box.y1 - rows + 1;
}

Picture channelPicture (int cursor, const std::array<double, 9>& levels, int mask, int width, int height,
                        const std::array<bool, 9>& clips, const std::array<double, 9>& holds)
{
    const auto slots = channelColumns (width);
    const int stemWidth = slots[0].x1 - slots[0].x0 + 1;
    std::vector<Span> columns (slots.begin(), slots.begin() + pairs);
    columns.push_back (centred (slots[analogInput], stemWidth));
    const auto [headingRows, arrowRowsBand, meterRows] = bands (height);

    Picture p;
    for (const auto& g : channelGroups)
        p.headings.push_back ({ { slots[(size_t) g.first].x0, headingRows.top, slots[(size_t) g.last].x1, headingRows.bottom }, g.name });
    std::vector<Box> boxes;
    for (const auto& c : columns)
        boxes.push_back ({ c.x0, meterRows.top, c.x1, meterRows.bottom });
    p.meters = metersFor (boxes, levels, clips, holds);
    for (size_t g = 1; g < channelGroups.size(); ++g)
        p.dividers.push_back (divider (slots[(size_t) channelGroups[g].first - 1], slots[(size_t) channelGroups[g].first], meterRows));
    const auto playing = playingStem (mask);
    p.active = bracket (p.meters[(size_t) (playing ? *playing : analogInput)].box);
    p.cursor = arrowBox (columns[(size_t) cursor], arrowRowsBand);
    addMarks (p.marks, p.meters, channelMarkLength);
    return p;
}

Picture returnPicture (int cursor, int mode, bool cue, const std::array<double, 2>& levels, int width, int height,
                       const std::array<bool, 2>& clips, const std::array<double, 2>& holds)
{
    // RETURN_OPTIONS = (STEM, ANALOG), left to right.
    constexpr std::array<int, 2> options { stemMode, analogMode };
    const auto indexOf = [&] (int option) { return option == stemMode ? 0 : 1; };
    const auto [headingRows, arrowRowsBand, meterRows] = bands (height);
    const auto channel = channelColumns (width);
    const auto lastMeter = channel[pairs - 1], toggleSlot = channel[analogInput];
    const int room = lastMeter.x1 + 1;
    const int heading = pyRound (width * returnHeadingOfWidth);
    const int meter = pyRound (heading * returnMeterOfHeading);
    const std::array<Span, 2> spans { { { 0, heading - 1 }, { room - heading, room - 1 } } };

    Picture p;
    std::vector<Box> boxes;
    for (size_t i = 0; i < spans.size(); ++i)
    {
        p.headings.push_back ({ { spans[i].x0, headingRows.top, spans[i].x1, headingRows.bottom },
                                options[i] == stemMode ? "STEM" : "ANALOG" });
        const int left = spans[i].x0 + floorDiv (spans[i].x1 - spans[i].x0 + 1 - meter, 2);
        boxes.push_back ({ left, meterRows.top, left + meter - 1, meterRows.bottom });
    }
    p.meters = metersFor (boxes, levels, clips, holds);
    p.toggle = Toggle { { toggleSlot.x0, meterRows.top, toggleSlot.x1, meterRows.bottom }, cue, "CUE" };
    p.dividers.push_back (divider (lastMeter, toggleSlot, meterRows));
    Span selected = toggleSlot;
    if (cursor != cueCursor)
    {
        const auto& b = boxes[(size_t) indexOf (cursor)];
        selected = { b.x0, b.x1 };
    }
    p.active = bracket (boxes[(size_t) indexOf (mode)]);
    p.cursor = arrowBox (selected, arrowRowsBand);
    addMarks (p.marks, p.meters, std::nullopt);
    return p;
}

bool ClipHold::feed (float peak, double dt)
{
    constexpr float clipThreshold = 1.0f;
    constexpr double clipHoldSeconds = 1.0, dust = 1e-9;
    if (std::isfinite (peak) && peak > clipThreshold)
    {
        left = clipHoldSeconds;
        return true;
    }
    left = std::max (0.0, left - dt);
    return left > dust;
}
}
