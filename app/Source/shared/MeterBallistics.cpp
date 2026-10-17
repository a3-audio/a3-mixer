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


#include "MeterBallistics.h"

#include <algorithm>
#include <cmath>

namespace a3
{

namespace
{
/** Below anything a meter shows (its floor is -60 dB), and finite, so a fall
 *  from silence is still arithmetic rather than infinity. */
constexpr float silenceDb = -200.f;

/** Where a level is drawn as nothing at all rather than as a tiny amplitude. */
constexpr float drawnAsSilenceDb = -150.f;

float
toDb (float amplitude)
{
  if (!(amplitude > 0.f))   // also NaN
    return silenceDb;
  return std::max (silenceDb, 20.f * std::log10 (amplitude));
}

float
toAmplitude (float db)
{
  return db <= drawnAsSilenceDb ? 0.f : std::pow (10.f, db / 20.f);
}
}

MeterBallistics::MeterBallistics (MeterBallisticsParameters parameters)
    : _parameters (parameters), _fromDb (silenceDb), _targetDb (silenceDb),
      _heldDb (silenceDb)
{
}

void
MeterBallistics::setParameters (MeterBallisticsParameters parameters)
{
  _parameters = parameters;
}

float
MeterBallistics::fallDb (std::int64_t elapsedMs) const
{
  return _parameters.releaseDbPerSecond
         * static_cast<float> (std::max<std::int64_t> (0, elapsedMs)) / 1000.f;
}

float
MeterBallistics::barDb (std::int64_t nowMs) const
{
  auto const elapsedMs = std::max<std::int64_t> (0, nowMs - _notedAtMs);

  if (_targetDb < _fromDb)
    return std::max (_targetDb, _fromDb - fallDb (elapsedMs));

  if (_parameters.attackMs <= 0.f
      || static_cast<float> (elapsedMs) >= _parameters.attackMs)
    return _targetDb;

  auto const progress = static_cast<float> (elapsedMs) / _parameters.attackMs;
  return _fromDb + (_targetDb - _fromDb) * progress;
}

float
MeterBallistics::holdDb (std::int64_t nowMs) const
{
  auto const holdMs = static_cast<std::int64_t> (
      std::lround (_parameters.peakHoldSeconds * 1000.f));
  auto const sinceHeldMs = nowMs - _heldAtMs;
  auto const held = sinceHeldMs <= holdMs
                        ? _heldDb
                        : _heldDb - fallDb (sinceHeldMs - holdMs);
  return std::max (held, barDb (nowMs));
}

void
MeterBallistics::note (float peak, std::int64_t nowMs)
{
  auto const peakDb = toDb (peak);

  // Both read before either changes: the hold is compared against where its
  // line stands now, and the bar starts its next move from where it is drawn.
  auto const heldNow = holdDb (nowMs);
  _fromDb = barDb (nowMs);
  _targetDb = peakDb;
  _notedAtMs = nowMs;

  // A peak as loud as the held one restarts it too, so a steady sound keeps
  // its line rather than having it fall away underneath it.
  if (peakDb >= heldNow)
    {
      _heldDb = peakDb;
      _heldAtMs = nowMs;
    }
}

float
MeterBallistics::bar (std::int64_t nowMs) const
{
  return toAmplitude (barDb (nowMs));
}

float
MeterBallistics::hold (std::int64_t nowMs) const
{
  return toAmplitude (holdDb (nowMs));
}

}
