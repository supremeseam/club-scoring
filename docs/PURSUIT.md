# Pursuit starts

In a pursuit race each boat starts at a time worked out from its handicap, so that boats sailing exactly to their
rating would all reach the finish together. The slowest boat starts first, at the first gun; everyone else waits.
**The first boat across the finish line wins.** No corrected time is calculated afterwards.

## Choosing it
- **Series:** *Race format* on the series form (Fleet start or Pursuit start). Every race in the series follows it.
- **One race:** on the race screen, *Race format* can be set to *Same as series*, *Fleet start* or *Pursuit start*,
  so a single pursuit can sit inside a normal series. New single races have the same choice.

## What the race committee sees
Set the first start time and the rating type/distance as usual. A blue **Pursuit start times** panel then lists
each boat in start order with the time to start after the first gun and the clock time. Boats with no rating (or a
rating of a different kind, such as a multihull scored by ORCA in a PHRF start) are listed as *not scheduled*.

## The maths
- **Time-on-distance (PHRF, seconds per nm):** gap = (slowest rating - boat's rating) x distance, rounded to a whole
  second. Example: ratings 180 / 150 / 96 over 10 nm start at 0:00, 5:00 and 14:00.
- **Time-on-time (ORCA/TCF):** gap = expected sailing time of the slowest boat x (1 - slowest TCF / boat's TCF). This
  needs the **expected minutes for the slowest boat**, entered on the race screen.

The start times use the ratings in force on the race date and the boats entered in that fleet. They **move when a
boat or rating is added or changed** (a new slowest boat shifts everyone), so check the panel just before the
first gun. Results stay correct either way because placing is by finishing order.

## Results
Enter finish times as usual. Results show *Own elapsed* (time since the boat's own start) and *Since 1st gun*, which
is what decides the places; boats crossing at the same second tie. Points then follow the series' scoring system
(Low Point by default), with the usual discards, penalties and codes.

Each fleet is its own pursuit. To pursue across fleets, put those boats in one fleet for the race.
