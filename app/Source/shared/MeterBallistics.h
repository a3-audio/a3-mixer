// SPDX-FileCopyrightText: 2023 Patric Schmitz
//
// SPDX-License-Identifier: GPL-3.0-or-later

/*

  A3 Motion UI
  Copyright (C) 2023 Patric Schmitz

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.

*/


#pragma once

#include <cstdint>

namespace a3
{

/** How every meter in the system moves (decided 2026-10-07): the desk, StemDeck
 *  and Motion draw the same burst rising and falling together.
 *
 *  The sources send raw peaks -- per tick the highest sample since the last
 *  one, no fall, no hold -- and each display applies these on its own clock.
 *  Core's truth carries them as the top-level "meters" block
 *  (OscTruth::meterBallistics()); the defaults here are the decided numbers
 *  and stand in for a truth from before that block. */
struct MeterBallisticsParameters
{
  /** How long the bar takes to close a rise, in milliseconds. 0 shows a new
   *  peak at once. */
  float attackMs = 0.f;
  /** How fast the bar and, once its hold is up, the hold line fall. */
  float releaseDbPerSecond = 20.f;
  /** How long the hold line stands at the highest recent peak. Long enough
   *  to be found and read with both hands busy, short enough to answer to
   *  what is playing now. */
  float peakHoldSeconds = 1.5f;
};

/** One meter's bar and hold line, from the raw peaks noted into it.
 *
 *  Time is a parameter (milliseconds on any monotonic clock), so the
 *  ballistics are tested without waiting for them and the bar keeps falling
 *  between two arrivals: it is computed when it is read. Levels go in and come
 *  out as linear amplitude, as they travel on the wire; the fall is in dB. */
class MeterBallistics
{
public:
  explicit MeterBallistics (MeterBallisticsParameters parameters = {});

  void setParameters (MeterBallisticsParameters parameters);

  /** A raw peak arrived at `nowMs`. */
  void note (float peak, std::int64_t nowMs);

  /** The bar's level: never below the latest peak, falling toward it at the
   *  release rate, rising to a louder one within the attack time. */
  float bar (std::int64_t nowMs) const;

  /** The hold line: the highest recent peak for the hold time, then falling
   *  at the release rate; never below the bar. */
  float hold (std::int64_t nowMs) const;

private:
  float barDb (std::int64_t nowMs) const;
  float holdDb (std::int64_t nowMs) const;
  float fallDb (std::int64_t elapsedMs) const;

  MeterBallisticsParameters _parameters;

  float _fromDb;
  float _targetDb;
  std::int64_t _notedAtMs = 0;

  float _heldDb;
  std::int64_t _heldAtMs = 0;
};

}
