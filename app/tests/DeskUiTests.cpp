// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskControlsUi.h"
#include "DeskIndicatorsUi.h"
#include "DeskLayout.h"
#include "DeskLook.h"
#include "DeskTheme.h"
#include "DisplayPicture.h"

using namespace desk;

namespace
{
int countNear (const juce::Image& image, juce::Colour colour, int tolerance = 24)
{
    int n = 0;
    for (int y = 0; y < image.getHeight(); ++y)
        for (int x = 0; x < image.getWidth(); ++x)
        {
            const auto p = image.getPixelAt (x, y);
            if (std::abs (p.getRed() - colour.getRed()) <= tolerance && std::abs (p.getGreen() - colour.getGreen()) <= tolerance
                && std::abs (p.getBlue() - colour.getBlue()) <= tolerance)
                ++n;
        }
    return n;
}

/** How much light a picture carries: perceived brightness weighted by opacity,
    so a dimmed (transparent) control reads darker even on an empty ground. */
double lightOf (const juce::Image& image)
{
    double sum = 0.0;
    for (int y = 0; y < image.getHeight(); ++y)
        for (int x = 0; x < image.getWidth(); ++x)
        {
            const auto p = image.getPixelAt (x, y);
            sum += static_cast<double> (p.getPerceivedBrightness()) * static_cast<double> (p.getFloatAlpha());
        }
    return sum;
}

bool isLit (juce::Colour p) { return p.getPerceivedBrightness() > 0.3f; }

/** Lit runs down one pixel column: one per lit segment where segments are lines with gaps between. */
int litRunsDown (const juce::Image& image, int x)
{
    int runs = 0;
    bool inside = false;
    for (int y = 0; y < image.getHeight(); ++y)
    {
        const bool lit = isLit (image.getPixelAt (x, y));
        runs += lit && ! inside ? 1 : 0;
        inside = lit;
    }
    return runs;
}

juce::Image snapshotOf (juce::Component& c, int w, int h)
{
    c.setBounds (0, 0, w, h);
    return c.createComponentSnapshot (c.getLocalBounds(), true, 1.f);
}

juce::MouseEvent eventAt (juce::Component& c, juce::Point<float> at, juce::Point<float> downAt, bool dragged)
{
    return { juce::Desktop::getInstance().getMainMouseSource(), at, juce::ModifierKeys(), 1.f,
             juce::MouseInputSource::defaultOrientation, juce::MouseInputSource::defaultRotation,
             juce::MouseInputSource::defaultTiltX, juce::MouseInputSource::defaultTiltY, &c, &c,
             juce::Time::getCurrentTime(), downAt, juce::Time::getCurrentTime(), 1, dragged };
}
}

// A page test must paint (memory feedback_a-page-test-must-paint): every
// visual state is drawn once here.
TEST (DeskUi, AKnobDrawsItsValueInItsChannelColour)
{
    DeskLook look;   // before the knob: outlives it
    DeskKnob knob ("TRIM", theme::channel[0], false);
    knob.setLookAndFeel (&look);
    knob.known = true;
    knob.setValue (0.0, juce::dontSendNotification);
    const auto low = countNear (snapshotOf (knob, 120, 100), theme::channel[0]);
    knob.setValue (1.0, juce::dontSendNotification);
    const auto high = countNear (snapshotOf (knob, 120, 100), theme::channel[0]);
    EXPECT_GT (high, low + 50);
    knob.setLookAndFeel (nullptr);
}

TEST (DeskUi, AnUnknownValueDrawsNoArc)
{
    DeskLook look;   // before the knob: outlives it
    DeskKnob knob ("TRIM", theme::channel[1], false);
    knob.setLookAndFeel (&look);
    knob.setValue (1.0, juce::dontSendNotification);
    EXPECT_EQ (countNear (snapshotOf (knob, 120, 100), theme::channel[1]), 0);
    knob.setLookAndFeel (nullptr);
}

// A full turn takes four knob heights of drag, at every size.
TEST (DeskUi, AKnobTurnsFullyOverFourHeights)
{
    DeskKnob knob ("TRIM", theme::channel[0], false);
    knob.setBounds (0, 0, 120, 100);
    EXPECT_EQ (knob.getMouseDragSensitivity(), 400);
}

// The cap follows the finger one to one: the value moves by the travel, not by JUCE's default 250 px.
TEST (DeskUi, TheCapFollowsTheFinger)
{
    DeskLook look;
    DeskFader fader (theme::channel[0]);
    fader.setLookAndFeel (&look);
    fader.known = true;
    fader.setBounds (0, 0, 60, 400);
    fader.setValue (0.5, juce::dontSendNotification);
    const auto cap = faderCap (fader.getLocalBounds().toFloat(), 0.5f);
    const juce::Point<float> down { cap.getCentreX(), cap.getCentreY() + 7.f };   // off-centre on the cap
    const double before = fader.getPositionOfValue (fader.getValue());

    fader.mouseDown (eventAt (fader, down, down, false));
    EXPECT_DOUBLE_EQ (fader.getValue(), 0.5);   // no jump under the finger
    fader.mouseDrag (eventAt (fader, { down.x, down.y - 60.f }, down, true));
    EXPECT_NEAR (fader.getPositionOfValue (fader.getValue()), before - 60.0, 1.0);
    fader.mouseUp (eventAt (fader, { down.x, down.y - 60.f }, down, true));
    fader.setLookAndFeel (nullptr);
}

// Final review M1: the fader's rule for the knob too -- an unknown pointer is
// drawn at 0, and a drag from there would send near zero to the room.
TEST (DeskUi, AnUnknownKnobCannotBeGrabbed)
{
    DeskKnob knob ("TRIM", theme::channel[0], false);
    knob.setBounds (0, 0, 120, 100);
    EXPECT_FALSE (knob.hitTest (60, 50));
    knob.known = true;
    EXPECT_TRUE (knob.hitTest (60, 50));
}

TEST (DeskUi, AnUnknownFaderCannotBeGrabbed)
{
    DeskFader fader (theme::channel[0]);
    fader.setBounds (0, 0, 60, 400);
    const auto cap = faderCap (fader.getLocalBounds().toFloat(), 0.f);
    EXPECT_FALSE (fader.hitTest ((int) cap.getCentreX(), (int) cap.getCentreY()));
}

TEST (DeskUi, TheFaderTakesOnlyItsCap)
{
    DeskFader fader (theme::channel[0]);
    fader.known = true;
    fader.setBounds (0, 0, 60, 400);
    fader.setValue (0.5, juce::dontSendNotification);
    const auto cap = faderCap (fader.getLocalBounds().toFloat(), 0.5f);
    EXPECT_TRUE (fader.hitTest ((int) cap.getCentreX(), (int) cap.getCentreY()));
    EXPECT_FALSE (fader.hitTest (30, 395));
}

// What is drawn, what is grabbed and where JUCE puts the handle are one rectangle.
TEST (DeskUi, TheGrabAreaIsTheDrawnCap)
{
    DeskLook look;
    DeskFader fader (theme::channel[0]);
    fader.setLookAndFeel (&look);
    fader.known = true;
    fader.setBounds (0, 0, 60, 400);
    fader.setValue (0.5, juce::dontSendNotification);
    const auto cap = faderCap (fader.getLocalBounds().toFloat(), 0.5f);

    const int x = (int) cap.getCentreX();
    EXPECT_TRUE (fader.hitTest (x, (int) cap.getY() + 2));
    EXPECT_FALSE (fader.hitTest (x, (int) cap.getY() - 2));
    EXPECT_TRUE (fader.hitTest (x, (int) cap.getBottom() - 3));
    EXPECT_FALSE (fader.hitTest (x, (int) cap.getBottom() + 2));

    // The handle JUCE tracks sits at the cap's centre, at both ends too.
    for (const double v : { 0.0, 0.5, 1.0 })
    {
        fader.setValue (v, juce::dontSendNotification);
        EXPECT_NEAR (fader.getPositionOfValue (v), faderCap (fader.getLocalBounds().toFloat(), (float) v).getCentreY(), 1.0);
    }

    // And the drawing agrees: a pixel just inside the cap's lower body is cap-coloured, one just outside is not.
    fader.setValue (0.5, juce::dontSendNotification);
    const auto image = snapshotOf (fader, 60, 400);
    const auto inside = image.getPixelAt (x, (int) (cap.getY() + cap.getHeight() * 0.3f));
    const auto outside = image.getPixelAt (x, (int) cap.getY() - 4);
    // StemDeck's cap: a gradient from capTop down to capBottom.
    const auto capAt = theme::capTop.interpolatedWith (theme::capBottom, 0.3f);
    EXPECT_LE (std::abs (inside.getRed() - capAt.getRed()), 6);
    EXPECT_GT (std::abs (outside.getRed() - capAt.getRed()), 6);
    fader.setLookAndFeel (nullptr);
}

TEST (DeskUi, AKeyShowsItsLampWhenLit)
{
    DeskKey key ("CUE", theme::lampCue);
    EXPECT_EQ (countNear (snapshotOf (key, 80, 60), theme::lampCue, 8), 0);
    key.setLit (true);
    EXPECT_GT (countNear (snapshotOf (key, 80, 60), theme::lampCue, 8), 20);
}

TEST (DeskUi, AKeySendsPressAndRelease)
{
    DeskKey key ("FX", theme::lampFx);
    key.setBounds (0, 0, 80, 60);
    std::vector<bool> seen;
    key.onPress = [&] (bool down) { seen.push_back (down); };
    key.mouseDown (eventAt (key, { 10.f, 10.f }, { 10.f, 10.f }, false));
    key.mouseUp (eventAt (key, { 10.f, 10.f }, { 10.f, 10.f }, false));
    ASSERT_EQ (seen.size(), 2u);
    EXPECT_TRUE (seen[0]);
    EXPECT_FALSE (seen[1]);
}

TEST (DeskUi, AnEncoderTurnsOnDragAndPushesOnClick)
{
    DeskEncoder encoder ("INPUT");
    encoder.setBounds (0, 0, 100, 100);
    std::vector<int> turns;
    int pushes = 0;
    encoder.onTurn = [&] (int clicks) { turns.push_back (clicks); };
    encoder.onPush = [&] { ++pushes; };

    const juce::Point<float> start { 50.f, 50.f };
    encoder.mouseDown (eventAt (encoder, start, start, false));
    encoder.mouseUp (eventAt (encoder, start, start, false));
    EXPECT_EQ (pushes, 1);
    EXPECT_TRUE (turns.empty());

    encoder.mouseDown (eventAt (encoder, start, start, false));
    encoder.mouseDrag (eventAt (encoder, { 50.f, 20.f }, start, true));   // 30 px up: one click per 25 px
    encoder.mouseUp (eventAt (encoder, { 50.f, 20.f }, start, true));
    ASSERT_EQ (turns.size(), 1u);
    EXPECT_EQ (turns[0], 1);
    EXPECT_EQ (pushes, 1);
}

// A wobble of the finger is not a push: a push loads something on the desk.
TEST (DeskUi, AShortDragIsNeitherATurnNorAPush)
{
    DeskEncoder encoder ("INPUT");
    encoder.setBounds (0, 0, 100, 100);
    int pushes = 0, turns = 0;
    encoder.onPush = [&] { ++pushes; };
    encoder.onTurn = [&] (int) { ++turns; };
    const juce::Point<float> start { 50.f, 50.f };
    encoder.mouseDown (eventAt (encoder, start, start, false));
    encoder.mouseDrag (eventAt (encoder, { 50.f, 46.f }, start, true));   // 4 px: under one click
    encoder.mouseUp (eventAt (encoder, { 50.f, 46.f }, start, true));
    EXPECT_EQ (pushes, 0);
    EXPECT_EQ (turns, 0);
}

// A control with no size yet must not turn a drag into nonsense.
TEST (DeskUi, AnEncoderWithoutSizeStaysFinite)
{
    DeskEncoder encoder ("INPUT");
    int total = 0;
    encoder.onTurn = [&] (int clicks) { total += clicks; };
    const juce::Point<float> start { 0.f, 0.f };
    encoder.mouseDown (eventAt (encoder, start, start, false));
    encoder.mouseDrag (eventAt (encoder, { 0.f, -3.f }, start, true));
    EXPECT_EQ (total, 3);
}

TEST (DeskUi, TheLedsLightInTheirColours)
{
    LedColumn leds;
    leds.setLevels (-14.0, -14.0);   // the -18 LED's group and most of the -12 one's
    auto image = snapshotOf (leds, 30, 240);
    EXPECT_GT (countNear (image, theme::ledGreen, 16), 0);
    EXPECT_EQ (countNear (image, theme::ledRed, 16), 0);
    EXPECT_EQ (countNear (image, theme::ledOrange, 16), 0);
    leds.setLevels (0.0, 0.0);
    image = snapshotOf (leds, 30, 240);
    EXPECT_GT (countNear (image, theme::ledYellow, 16), 0);
    EXPECT_GT (countNear (image, theme::ledOrange, 16), 0);
    EXPECT_GT (countNear (image, theme::ledRed, 16), 0);
}

// Lines, not dots (maintainer, 2026-10-30): every segment a bar across the meter, many of them.
TEST (DeskUi, TheChannelMeterDrawsManyLines)
{
    LedColumn leds;
    leds.setLevels (0.0, 0.0);
    const auto image = snapshotOf (leds, 30, 320);
    EXPECT_EQ (litRunsDown (image, 15), leds::screen::channelSegments (320.f));
    EXPECT_GE (litRunsDown (image, 15), 64);
    const int y = image.getHeight() - 3;   // inside the bottom segment
    int lit = 0;
    for (int x = 0; x < image.getWidth(); ++x)
        lit += isLit (image.getPixelAt (x, y)) ? 1 : 0;
    EXPECT_GT (lit, image.getWidth() / 2);
}

TEST (DeskUi, TheChannelMeterKeepsItsPeakHold)
{
    LedColumn leds;
    leds.setLevels (-30.0, -30.0);
    const auto without = snapshotOf (leds, 30, 320);
    leds.setLevels (-30.0, -7.0);
    const auto with = snapshotOf (leds, 30, 320);
    EXPECT_EQ (countNear (without, theme::ledOrange, 16), 0);
    EXPECT_GT (countNear (with, theme::ledOrange, 16), 0);
    EXPECT_EQ (litRunsDown (with, 15), litRunsDown (without, 15) + 1);
}

TEST (DeskUi, TheOutputMatrixLightsItsRows)
{
    OutputMatrix matrix;
    const auto dark = countNear (snapshotOf (matrix, 200, 300), theme::ledGreen, 16);
    matrix.setColumn (0, -20.0, -15.0);
    EXPECT_GT (countNear (snapshotOf (matrix, 200, 300), theme::ledGreen, 16), dark);
}

TEST (DeskUi, TheOutputMetersDrawManyLines)
{
    OutputMatrix matrix;
    for (int column = 0; column < leds::matrixColumns; ++column)
        matrix.setColumn (column, 0.0, 0.0);
    const auto image = snapshotOf (matrix, 200, 600);
    const float columnWidth = 200.f / leds::matrixColumns;
    for (int column = 0; column < leds::matrixColumns; ++column)
        EXPECT_EQ (litRunsDown (image, juce::roundToInt ((static_cast<float> (column) + 0.5f) * columnWidth)),
                   leds::screen::mainSegments (600.f)) << column;
    EXPECT_GT (countNear (image, theme::ledRed, 16), 0);
}

TEST (DeskUi, TheOutputMatrixIgnoresAColumnItDoesNotHave)
{
    OutputMatrix matrix;
    const auto before = countNear (snapshotOf (matrix, 200, 300), theme::ledGreen, 16);
    matrix.setColumn (-1, -20.0, -15.0);
    matrix.setColumn (8, -20.0, -15.0);
    EXPECT_EQ (countNear (snapshotOf (matrix, 200, 300), theme::ledGreen, 16), before);
}

// StemDeck's keys: a lit key is filled with its lamp, not marked by a strip.
TEST (DeskUi, ALitKeyIsFilledWithItsLamp)
{
    DeskKey key ("CUE", theme::lampCue);
    const auto dark = countNear (snapshotOf (key, 80, 60), theme::lampCue, 16);
    key.setLit (true);
    EXPECT_LT (dark, 80 * 60 / 20);
    EXPECT_GT (countNear (snapshotOf (key, 80, 60), theme::lampCue, 16), 80 * 60 / 2);
}

// StemDeck's knobs: a body in its grey with a light pointer, the value arc in the channel's colour.
TEST (DeskUi, AKnobWearsStemDecksBody)
{
    DeskLook look;
    DeskKnob knob ("TRIM", theme::channel[0], false);
    knob.setLookAndFeel (&look);
    knob.known = true;
    knob.setValue (0.8, juce::dontSendNotification);
    const auto image = snapshotOf (knob, 120, 100);
    EXPECT_GT (countNear (image, theme::channel[0], 16), 50);
    EXPECT_GT (countNear (image, theme::outline, 6), 20);   // the track, as StemDeck's
    EXPECT_GT (countNear (image, theme::text, 16), 5);      // the pointer
    knob.setLookAndFeel (nullptr);
}

TEST (DeskUi, TheOledShowsThePicture)
{
    OledView oled;
    oled.setPicture (display::channelPicture (0, 0, { 1, 1, 1 }, 1, display::oledWidth,
                                              display::oledHeight, {}, {}));
    EXPECT_GT (countNear (snapshotOf (oled, 256, 128), juce::Colours::white, 30), 500);
}

TEST (DeskUi, ATapOnTheOledNamesTheSlot)
{
    OledView oled;
    const auto picture = display::channelPicture (0, 0, { 1, 1, 1 }, 1, display::oledWidth,
                                                  display::oledHeight, {}, {});
    ASSERT_FALSE (picture.meters.empty());
    oled.setPicture (picture);
    oled.setBounds (0, 0, 256, 128);
    int slot = -1;
    oled.onSlot = [&] (int index) { slot = index; };
    const auto& box = picture.meters[0].box;
    const juce::Point<float> at { (float) (box.x0 + box.x1) * 0.5f * 2.f, 64.f };   // the view is 2x the panel
    oled.mouseUp (eventAt (oled, at, at, false));
    EXPECT_EQ (slot, 0);
}

TEST (DeskUi, TheStatusLinePaintsItsText)
{
    StatusLine line;
    const auto empty = lightOf (snapshotOf (line, 300, 24));
    line.setText ("A3 DESK", "CORE OK");
    EXPECT_GT (lightOf (snapshotOf (line, 300, 24)), empty);
}

TEST (DeskUi, TheLiveChipPaintsLitAndDark)
{
    StatusLine line;
    line.setBounds (0, 0, 600, 24);
    line.setText ("", "");
    line.setLive ({ true, false, true });
    const auto chip = line.liveChip().toNearestInt();
    ASSERT_FALSE (chip.isEmpty());
    const auto dark = snapshotOf (line, 600, 24).getClippedImage (chip);
    line.setLive ({ true, true, true });
    const auto lit = snapshotOf (line, 600, 24).getClippedImage (chip);
    EXPECT_GT (lightOf (lit), lightOf (dark));
}

TEST (DeskUi, TheLiveChipIsAShareOfTheLineAtItsRightEnd)
{
    StatusLine line;
    line.setBounds (0, 0, 600, 24);
    EXPECT_TRUE (line.liveChip().isEmpty());   // not offered: no chip
    line.setLive ({ true, false, true });
    const auto chip = line.liveChip();
    EXPECT_GT (chip.getWidth(), 0.f);
    EXPECT_LE (chip.getHeight(), 24.f);
    EXPECT_FLOAT_EQ (chip.getRight(), 600.f);
    line.setBounds (0, 0, 1200, 48);
    EXPECT_NEAR (line.liveChip().getWidth(), 2.f * chip.getWidth(), 0.01f);
}

TEST (DeskUi, ATapOnTheLiveChipIsReportedAndOneElsewhereIsNot)
{
    StatusLine line;
    line.setBounds (0, 0, 600, 24);
    line.setLive ({ true, false, true });
    int taps = 0;
    line.onLiveTapped = [&] { ++taps; };
    const auto in = line.liveChip().getCentre();
    line.mouseUp (eventAt (line, in, in, false));
    EXPECT_EQ (taps, 1);
    line.mouseUp (eventAt (line, in, in, true));   // a drag is no tap
    const juce::Point<float> out { 10.f, 12.f };
    line.mouseUp (eventAt (line, out, out, false));
    EXPECT_EQ (taps, 1);
}

// A disabled control must read visibly dimmer than the enabled one, and the
// dimming is one helper's work, so one test covers every control.
TEST (DeskUi, EveryControlPaintsDisabledDimmer)
{
    DeskLook look;   // before the controls: outlives them
    DeskKnob knob ("SEND", theme::channel[3], false);
    knob.setLookAndFeel (&look);
    knob.known = true;
    knob.setValue (0.8, juce::dontSendNotification);
    DeskFader fader (theme::channel[0]);
    fader.setLookAndFeel (&look);
    fader.known = true;
    fader.setValue (0.5, juce::dontSendNotification);
    DeskEncoder encoder ("INPUT");
    DeskKey key ("CUE", theme::lampCue);
    key.setLit (true);

    const auto dimmer = [] (juce::Component& c, int w, int h)
    {
        c.setEnabled (true);
        const auto on = lightOf (snapshotOf (c, w, h));
        c.setEnabled (false);
        const auto off = lightOf (snapshotOf (c, w, h));
        EXPECT_GT (on, 0.0);
        EXPECT_LT (off, on * 0.6);
    };
    dimmer (knob, 120, 100);
    dimmer (fader, 60, 400);
    dimmer (encoder, 120, 100);
    dimmer (key, 80, 60);
    knob.setLookAndFeel (nullptr);
    fader.setLookAndFeel (nullptr);
}

// Stale dims the whole surface (spec 4.1): the indicators too, by the same helper.
TEST (DeskUi, EveryIndicatorPaintsDisabledDimmer)
{
    LedColumn leds;
    leds.setLevels (0.0, 0.0);
    OutputMatrix matrix;
    for (int column = 0; column < 8; ++column)
        matrix.setColumn (column, 0.0, 0.0);
    OledView oled;
    oled.setPicture (display::channelPicture (0, 0, { 1, 1, 1 }, 1, display::oledWidth,
                                              display::oledHeight, {}, {}));

    // `floor`: the light a control paints with nothing on it. The OLED's surround is the desk's background,
    // never dimmed, and with three meters a channel's picture no longer outweighs it.
    const auto dimmer = [] (juce::Component& c, int w, int h, double floor)
    {
        c.setEnabled (true);
        const auto on = lightOf (snapshotOf (c, w, h)) - floor;
        c.setEnabled (false);
        const auto off = lightOf (snapshotOf (c, w, h)) - floor;
        EXPECT_GT (on, 0.0);
        EXPECT_LT (off, on * 0.6);
    };
    OledView blank;
    dimmer (leds, 20, 160, 0.0);
    dimmer (matrix, 80, 160, 0.0);
    dimmer (oled, 256, 128, lightOf (snapshotOf (blank, 256, 128)));
}

namespace
{
/** Light at the foot of a control's ring, where a pot's travel has its gap. */
double lightAtTheFoot (juce::Component& c)
{
    const auto shot = snapshotOf (c, 120, 100);
    return lightOf (shot.getClippedImage ({ 50, 64, 20, 12 }));
}
}

// An encoder is endless: its ring has no ends, which is what tells it from a pot at a glance.
TEST (DeskUi, AnEncoderReadsAsEndlessNotAsAPot)
{
    DeskLook look;
    DeskKnob knob ("TRIM", theme::channel[0], false);
    knob.setLookAndFeel (&look);
    knob.known = true;
    DeskEncoder encoder ("INPUT");
    EXPECT_LT (lightAtTheFoot (knob), 1.0);
    EXPECT_GT (lightAtTheFoot (encoder), 20.0);
    knob.setLookAndFeel (nullptr);
}

// The cap turns with the hand, a step per click: the turn is felt where it was made.
TEST (DeskUi, AnEncoderTurnsItsCapWithTheClicks)
{
    DeskEncoder encoder ("INPUT");
    encoder.setBounds (0, 0, 100, 100);
    const auto before = snapshotOf (encoder, 100, 100);
    const juce::Point<float> start { 50.f, 50.f };
    encoder.mouseDown (eventAt (encoder, start, start, false));
    encoder.mouseDrag (eventAt (encoder, { 50.f, 20.f }, start, true));
    encoder.mouseUp (eventAt (encoder, { 50.f, 20.f }, start, true));
    const auto after = snapshotOf (encoder, 100, 100);
    int differing = 0;
    for (int y = 0; y < before.getHeight(); ++y)
        for (int x = 0; x < before.getWidth(); ++x)
            differing += before.getPixelAt (x, y) != after.getPixelAt (x, y) ? 1 : 0;
    EXPECT_GT (differing, 10);
}
