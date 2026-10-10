import { Text } from "@mantine/core";
import type { S } from "../api/client";
import { Place } from "./Brand";

/** Top three finishers of a fleet. Hidden until there is at least one finisher. */
export function Podium({ block }: { block: S["FleetResults"] }) {
  const top = block.rows.filter((r) => r.place !== null && r.place <= 3 && r.corrected).slice(0, 3);
  if (top.length === 0) return null;
  return (
    <div className="podium" aria-label={`${block.fleet_name} podium`}>
      {top.map((r) => (
        <div key={r.boat.id} className={`podium-step p${r.place}`}>
          <Place place={r.place} />
          <div className="who">
            <div className="boat">{r.boat.name}</div>
            <Text size="xs" c="dimmed">{r.boat.skipper}{r.boat.home_club ? ` · ${r.boat.home_club}` : ""}</Text>
          </div>
          <Text className="time" size="sm" fw={600}>{r.corrected}</Text>
        </div>
      ))}
    </div>
  );
}
