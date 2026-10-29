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
constexpr double markOfMeter = 0.1, returnHeadingOfWidth = 0.35, returnMeterOfWidth = 0.17;
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
constexpr std::array<Group, 3> channelGroups { { { "A", 0, 3 }, { "B", 4, 7 }, { "ST", analogInput, analogInput } } };

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

std::array<int, channelMeters> channelRing (int channel) { return { channel, stemsPerDeck + channel, analogInput }; }

int channelSlot (int channel, int cursor)
{
    const auto ring = channelRing (channel);
    const auto at = std::find (ring.begin(), ring.end(), cursor);
    return at == ring.end() ? channelMeters - 1 : static_cast<int> (at - ring.begin());
}

int playingSlot (int channel, int mask)
{
    const auto ring = channelRing (channel);
    if ((mask & (1 << ring[0])) != 0)
        return 0;
    if ((mask & (1 << ring[1])) != 0)
        return 1;
    return 2;
}

namespace
{
// What both channel pictures stand on: the three heading spans, the three bar columns, the dividers'
// slots and the bands.
struct ChannelLayout
{
    std::array<Span, 3> spans, columns;
    std::array<Rows, 3> bands;
    std::vector<Span> slots;
};

ChannelLayout channelLayout (int width, int height)
{
    ChannelLayout layout;
    layout.slots = channelColumns (width);
    const int stemWidth = layout.slots[0].x1 - layout.slots[0].x0 + 1;
    for (size_t g = 0; g < channelGroups.size(); ++g)
    {
        layout.spans[g] = { layout.slots[(size_t) channelGroups[g].first].x0, layout.slots[(size_t) channelGroups[g].last].x1 };
        layout.columns[g] = centred (layout.spans[g], stemWidth);
    }
    layout.bands = bands (height);
    return layout;
}

std::vector<Box> dividersOf (const ChannelLayout& layout)
{
    std::vector<Box> out;
    for (size_t g = 1; g < channelGroups.size(); ++g)
        out.push_back (divider (layout.slots[(size_t) channelGroups[g].first - 1],
                                layout.slots[(size_t) channelGroups[g].first], layout.bands[2]));
    return out;
}

std::vector<Box> meterBoxes (const ChannelLayout& layout)
{
    std::vector<Box> boxes;
    for (const auto& c : layout.columns)
        boxes.push_back ({ c.x0, layout.bands[2].top, c.x1, layout.bands[2].bottom });
    return boxes;
}
}

Picture channelPicture (int channel, int cursor, const std::array<double, channelMeters>& levels, int mask, int width,
                        int height, const std::array<bool, channelMeters>& clips,
                        const std::array<double, channelMeters>& holds)
{
    const auto layout = channelLayout (width, height);
    Picture p;
    for (size_t g = 0; g < channelGroups.size(); ++g)
        p.headings.push_back ({ { layout.spans[g].x0, layout.bands[0].top, layout.spans[g].x1, layout.bands[0].bottom },
                                channelGroups[g].name });
    p.meters = metersFor (meterBoxes (layout), levels, clips, holds);
    p.dividers = dividersOf (layout);
    p.active = bracket (p.meters[(size_t) playingSlot (channel, mask)].box);
    p.cursor = arrowBox (layout.columns[(size_t) channelSlot (channel, cursor)], layout.bands[1]);
    addMarks (p.marks, p.meters, channelMarkLength);
    return p;
}

int engineSlot (int source) { return source >= 1 && source <= engineDecks ? source - 1 : engineSlots - 1; }

Picture enginePicture (int source, int cursor, const std::array<bool, engineDecks>& present,
                       const std::array<double, engineSlots>& levels, int width, int height,
                       const std::array<bool, engineSlots>& clips, const std::array<double, engineSlots>& holds)
{
    // ENGINE_GROUPS: a deck spans two stem slots of the grid, A keeps the ninth.
    struct EngineGroup
    {
        const char* name;
        int first, last;
    };
    constexpr std::array<EngineGroup, engineSlots> groups { { { "A", 0, 1 },
                                                              { "B", 2, 3 },
                                                              { "C", 4, 5 },
                                                              { "D", 6, 7 },
                                                              { "ST", analogInput, analogInput } } };
    const auto slots = channelColumns (width);
    const auto rows = bands (height);
    const int stemWidth = slots[0].x1 - slots[0].x0 + 1;

    std::array<bool, engineSlots> there {};
    for (size_t i = 0; i < engineDecks; ++i)
        there[i] = present[i];
    there[engineSlots - 1] = true;

    auto shownLevels = levels;
    auto shownClips = clips;
    auto shownHolds = holds;
    Picture p;
    std::vector<Span> columns;
    for (size_t i = 0; i < groups.size(); ++i)
    {
        const Span span { slots[(size_t) groups[i].first].x0, slots[(size_t) groups[i].last].x1 };
        columns.push_back (centred (span, stemWidth));
        p.headings.push_back ({ { span.x0, rows[0].top, span.x1, rows[0].bottom }, groups[i].name });
        if (! there[i])
        {
            shownLevels[i] = 0.0;
            shownClips[i] = false;
            shownHolds[i] = 0.0;
        }
    }
    std::vector<Box> boxes;
    for (const auto& c : columns)
        boxes.push_back ({ c.x0, rows[2].top, c.x1, rows[2].bottom });
    p.meters = metersFor (boxes, shownLevels, shownClips, shownHolds);
    // One divider, between the decks and A: two stem slots leave no room for one between neighbouring decks.
    p.dividers.push_back (divider (slots[(size_t) analogInput - 1], slots[(size_t) analogInput], rows[2]));
    p.active = bracket (p.meters[(size_t) engineSlot (source)].box);
    p.cursor = arrowBox (columns[(size_t) engineSlot (cursor)], rows[1]);
    std::vector<Meter> shown;
    for (size_t i = 0; i < engineSlots; ++i)
        if (there[i])
            shown.push_back (p.meters[i]);
    addMarks (p.marks, shown, channelMarkLength);
    return p;
}

Picture returnPicture (bool cue, double level, int width, int height, bool clip, double hold)
{
    const auto [headingRows, arrowRowsBand, meterRows] = bands (height);
    const auto channel = channelColumns (width);
    const auto lastMeter = channel[pairs - 1], toggleSlot = channel[analogInput];
    const int heading = pyRound (width * returnHeadingOfWidth);
    const int meter = pyRound (width * returnMeterOfWidth);
    // Name and meter at the left margin, as a channel's first heading and meter do.
    const int x0 = channel[0].x0;
    // Not at x0 itself: the scale marks stand in the column left of the bar.
    const int left = centred ({ channel[0].x0, channel[1].x1 }, channel[0].x1 - channel[0].x0 + 1).x0;

    Picture p;
    p.headings.push_back ({ { x0, headingRows.top, x0 + heading - 1, headingRows.bottom }, "DELAY" });
    p.meters = metersFor (std::vector<Box> { { left, meterRows.top, left + meter - 1, meterRows.bottom } },
                          std::array<double, 1> { level }, std::array<bool, 1> { clip }, std::array<double, 1> { hold });
    p.toggle = Toggle { { toggleSlot.x0, meterRows.top, toggleSlot.x1, meterRows.bottom }, cue, "CUE" };
    p.dividers.push_back (divider (lastMeter, toggleSlot, meterRows));
    p.cursor = noBox;
    p.active = noBox;
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
